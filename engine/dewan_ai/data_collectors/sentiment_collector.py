import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from .base import BaseCollector, CollectorError, CollectorResult

logger = logging.getLogger(__name__)


def _news_query_for_pair(pair: str) -> str:
    up = (pair or "").upper()
    if up.endswith("USDT"):
        base = up.replace("USDT", "")
        mapping = {
            "BTC": "Bitcoin OR BTC",
            "ETH": "Ethereum OR ETH",
            "XRP": "XRP OR Ripple",
            "ADA": "Cardano OR ADA",
            "SOL": "Solana OR SOL",
            "LTC": "Litecoin OR LTC",
            "ENA": "Ethena OR ENA",
            "HBAR": "Hedera OR HBAR",
        }
        return mapping.get(base, f"{base} crypto")
    if up in ("XAUUSD", "XAGUSD"):
        return "gold price" if up == "XAUUSD" else "silver price"
    if up in ("EURUSD", "EURGBP", "EURJPY", "GBPUSD", "GBPJPY", "USDJPY"):
        return f"{up} forex"
    # stocks
    stock_map = {"AAPL": "Apple stock", "MSFT": "Microsoft stock", "NVDA": "NVIDIA stock", "TSLA": "Tesla stock"}
    if up in stock_map:
        return stock_map[up]
    return up


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fmt_newsapi(dt: datetime) -> str:
    dtu = _to_utc(dt)
    return dtu.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(x: Any) -> Optional[datetime]:
    if not x:
        return None
    s = str(x).strip()
    if not s:
        return None
    # Common NewsAPI format: 2025-01-01T12:34:56Z
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        return _to_utc(dt)
    except Exception:
        return None


class SentimentCollector(BaseCollector):
    """
    Collect sentiment context (time-aligned when `as_of` is provided):
    - Fear & Greed Index (Alternative.me) - no key
    - NewsAPI headlines (requires NEWS_API_KEY)

    For historical evaluations, callers should pass `as_of` (UTC). The collector will:
    - For news: only fetch items published <= as_of (using NewsAPI `to=` parameter).
    - For fear&greed: pick the latest index value with timestamp <= as_of.
    """

    def __init__(self, timeout_s: float = 20.0):
        super().__init__(timeout_s=timeout_s)
        self.news_key = (os.getenv("NEWS_API_KEY") or "").strip()
        self.news_enabled = (os.getenv("DEWAN_NEWS_ENABLED") or "true").strip().lower() == "true"
        # Default cache TTL = 1 day to reduce NewsAPI calls; override via DEWAN_NEWS_TTL_S.
        self.news_ttl_s = int(float(os.getenv("DEWAN_NEWS_TTL_S") or 86400))
        self.news_window_h = int(float(os.getenv("DEWAN_NEWS_WINDOW_H") or 24))
        self.news_required = (os.getenv("DEWAN_NEWS_REQUIRED") or "false").strip().lower() == "true"
        self._news_blocked = False
        self._news_block_reason = ""
        self.fng_enabled = (os.getenv("DEWAN_FNG_ENABLED") or "true").strip().lower() == "true"
        # Fear&Greed is low-weight background context; default non-fatal when endpoint fails.
        self.fng_required = (os.getenv("DEWAN_FNG_REQUIRED") or "false").strip().lower() == "true"
        # If fetch fails, optionally use last cached value even if TTL expired.
        self.fng_allow_stale = (os.getenv("DEWAN_FNG_ALLOW_STALE") or "true").strip().lower() == "true"
        self.fng_ttl_s = int(float(os.getenv("DEWAN_FNG_TTL_S") or 300))
        # For historical runs, we can cache the long lookback response longer.
        self.fng_hist_ttl_s = int(float(os.getenv("DEWAN_FNG_HIST_TTL_S") or 86400))
        self.fng_lookback_days = int(float(os.getenv("DEWAN_FNG_LOOKBACK_DAYS") or 400))

    async def collect(self, pair: str, as_of: Optional[datetime] = None) -> CollectorResult:
        out: Dict[str, Any] = {}
        out["fear_greed"] = await self._fear_greed(as_of=as_of)
        out["news"] = await self._news(pair, as_of=as_of)
        return CollectorResult(ok=True, data=out, source="sentiment_collector", fetched_at=time.time())

    async def _fear_greed(self, *, as_of: Optional[datetime] = None) -> Dict[str, Any]:
        if not self.fng_enabled:
            return {"enabled": False, "source": "alternative.me"}

        to_dt = _to_utc(as_of) if isinstance(as_of, datetime) else datetime.now(timezone.utc)
        # Use a longer lookback cache when evaluating historical timestamps.
        ttl = self.fng_ttl_s
        if isinstance(as_of, datetime) and abs((datetime.now(timezone.utc) - to_dt).total_seconds()) > 3600:
            ttl = max(ttl, self.fng_hist_ttl_s)

        limit = max(1, int(self.fng_lookback_days))
        if limit > 2000:
            limit = 2000
        key = f"alternative.me:fng:limit={limit}"

        cached = self.cache.get(key, ttl_s=ttl)
        if cached is not None:
            try:
                return self._pick_fng_row(cached, to_dt=to_dt)
            except Exception:
                pass

        url = "https://api.alternative.me/fng/"
        params = {"limit": limit, "format": "json"}
        client = self._get_client()
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json() or {}
            rows = data.get("data") or []
            # Cache the raw list for reuse across many triggers/dates.
            self.cache.set(key, rows)
            return self._pick_fng_row(rows, to_dt=to_dt)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            if self.fng_allow_stale:
                entry = self.cache.get_entry(key)
                if entry is not None and entry.get("data") is not None:
                    try:
                        out = self._pick_fng_row(entry.get("data"), to_dt=to_dt)
                        out["stale"] = True
                        out["error"] = err
                        try:
                            age_s = max(0.0, time.time() - float(entry.get("_ts") or 0.0))
                        except Exception:
                            age_s = None
                        if age_s is not None:
                            out["stale_age_s"] = age_s
                        return out
                    except Exception:
                        pass
            if self.fng_required:
                raise CollectorError(f"Fear&Greed fetch failed: {err}")
            return {"enabled": False, "error": err, "source": "alternative.me"}

    def _pick_fng_row(self, rows: Any, *, to_dt: datetime) -> Dict[str, Any]:
        if not isinstance(rows, list) or not rows:
            return {"enabled": False, "source": "alternative.me", "error": "empty"}

        # Alternative.me returns newest-first; pick the newest row with ts <= to_dt.
        target_ts = int(_to_utc(to_dt).timestamp())

        picked: Optional[Dict[str, Any]] = None
        picked_ts: Optional[int] = None

        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                ts = int(float(row.get("timestamp") or 0))
            except Exception:
                ts = 0
            if ts <= 0:
                continue
            if ts <= target_ts and (picked_ts is None or ts > picked_ts):
                picked = row
                picked_ts = ts

        if picked is None:
            # If no row is older than to_dt (very old backtest), fall back to the oldest known.
            oldest = None
            oldest_ts = None
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    ts = int(float(row.get("timestamp") or 0))
                except Exception:
                    ts = 0
                if ts <= 0:
                    continue
                if oldest_ts is None or ts < oldest_ts:
                    oldest, oldest_ts = row, ts
            picked = oldest if isinstance(oldest, dict) else rows[-1]
            picked_ts = oldest_ts

        try:
            value = int(float((picked or {}).get("value") or 0))
        except Exception:
            value = 0

        return {
            "enabled": True,
            "value": value,
            "classification": str((picked or {}).get("value_classification") or ""),
            "timestamp": str((picked or {}).get("timestamp") or ""),
            "as_of": _fmt_newsapi(to_dt),
            "source": "alternative.me",
        }

    async def _news(self, pair: str, *, as_of: Optional[datetime] = None) -> Dict[str, Any]:
        if not self.news_enabled:
            return {"enabled": False, "items": []}
        if self._news_blocked:
            return {"enabled": False, "items": [], "source": "newsapi", "reason": self._news_block_reason, "as_of": _fmt_newsapi(to_dt)}
        if not self.news_key:
            if self.news_required:
                raise CollectorError("NEWS_API_KEY missing")
            return {"enabled": False, "items": [], "source": "newsapi", "reason": "missing_api_key", "as_of": _fmt_newsapi(to_dt)}

        query = _news_query_for_pair(pair)
        url = "https://newsapi.org/v2/everything"
        lang = (os.getenv("DEWAN_NEWS_LANG") or "en").strip() or "en"
        sort_by = (os.getenv("DEWAN_NEWS_SORT") or "publishedAt").strip() or "publishedAt"
        page_size = int(float(os.getenv("DEWAN_NEWS_PAGE_SIZE") or 10))
        # Limit search to title/description by default to reduce irrelevant matches (e.g., "BTC" as an unrelated acronym).
        search_in = (os.getenv("DEWAN_NEWS_SEARCH_IN") or "title,description").strip() or "title,description"

        to_dt = _to_utc(as_of) if isinstance(as_of, datetime) else datetime.now(timezone.utc)
        win_h = max(1, int(self.news_window_h))
        from_dt = to_dt - timedelta(hours=win_h)

        key = (
            f"newsapi:everything:q={query}:lang={lang}:sort={sort_by}:pageSize={page_size}:searchIn={search_in}"
            f":from={_fmt_newsapi(from_dt)}:to={_fmt_newsapi(to_dt)}"
        )
        cached = self.cache.get(key, ttl_s=self.news_ttl_s)
        if cached is not None:
            return cached

        params = {
            "q": query,
            "language": lang,
            "sortBy": sort_by,
            "pageSize": page_size,
            "searchIn": search_in,
            # Time alignment (avoid future leak for historical sims)
            "from": _fmt_newsapi(from_dt),
            "to": _fmt_newsapi(to_dt),
        }
        headers = {"X-Api-Key": self.news_key}
        client = self._get_client()
        try:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json() or {}
            items: List[Dict[str, Any]] = []
            for a in (data.get("articles") or [])[: params["pageSize"]]:
                if not isinstance(a, dict):
                    continue
                pub = a.get("publishedAt")
                pub_dt = _parse_dt(pub)
                if pub_dt is not None and pub_dt > to_dt:
                    continue
                items.append(
                    {
                        "source": (a.get("source") or {}).get("name"),
                        "title": a.get("title"),
                        "description": a.get("description"),
                        "url": a.get("url"),
                        "publishedAt": pub,
                    }
                )
            out = {"enabled": True, "query": query, "items": items, "source": "newsapi", "as_of": _fmt_newsapi(to_dt)}
            self.cache.set(key, out)
            return out
        except httpx.HTTPStatusError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            body = ""
            try:
                body = (e.response.text or "").strip() if getattr(e, "response", None) is not None else ""
            except Exception:
                body = ""
            if body and len(body) > 200:
                body = body[:200] + " ...<truncated>"
            err = f"HTTP {status}: {body}" if status else f"HTTPStatusError: {body}"
            if status in (401, 403, 426):
                self._news_blocked = True
                self._news_block_reason = f"http_{status}"
            if self.news_required:
                raise CollectorError(f"NewsAPI fetch failed: {err}")
            return {"enabled": False, "items": [], "query": query, "source": "newsapi", "as_of": _fmt_newsapi(to_dt), "error": err}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            if self.news_required:
                raise CollectorError(f"NewsAPI fetch failed: {err}")
            return {"enabled": False, "items": [], "query": query, "source": "newsapi", "as_of": _fmt_newsapi(to_dt), "error": err}

