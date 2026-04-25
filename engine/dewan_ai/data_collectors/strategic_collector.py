import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from .base import BaseCollector, CollectorError, CollectorResult

logger = logging.getLogger(__name__)


def _date_str(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _redact_secrets(text: str) -> str:
    if not text:
        return ""
    # Redact common query params used by EODHD/FRED.
    text = re.sub(r"(?i)(api_token=)[^&\s]+", r"\1<redacted>", text)
    text = re.sub(r"(?i)(api_key=)[^&\s]+", r"\1<redacted>", text)
    return text


def _safe_http_err(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError) and getattr(e, "response", None) is not None:
        status = e.response.status_code
        body = (e.response.text or "").strip()
        if len(body) > 500:
            body = body[:500] + " ...<truncated>"
        body = _redact_secrets(body)
        return f"HTTP {status}: {body}" if body else f"HTTP {status}"
    return f"{type(e).__name__}: {_redact_secrets(str(e))}"


def _lower_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (row or {}).items():
        try:
            out[str(k).strip().lower()] = v
        except Exception:
            continue
    return out


def _parse_event_dt(row: Dict[str, Any]) -> Optional[datetime]:
    if not isinstance(row, dict):
        return None
    d = str(row.get("date") or "").strip()
    if not d:
        return None
    t = str(row.get("time") or "").strip()
    # Common: date=YYYY-MM-DD, time=HH:MM:SS or HH:MM
    s = d
    if t and t.lower() not in ("all day", "allday", "na", "n/a"):  # best-effort
        s = f"{d}T{t}"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        try:
            dt = datetime.fromisoformat(d)
        except Exception:
            return None
    return _to_utc(dt)


class StrategicCollector(BaseCollector):
    """
    Collect strategic context (time-aligned when `as_of` is provided):
    - EODHD economic calendar (requires EODHD_API_KEY)
    - FRED macro snapshot (requires FRED_API_KEY)

    For historical evaluations, callers should pass `as_of` (UTC). The collector will:
    - For FRED: use `observation_end` so values are not taken from the future.
    - For EODHD: query a window around as_of and redact `actual` for events after as_of.
    """

    def __init__(self, timeout_s: float = 25.0):
        super().__init__(timeout_s=timeout_s)
        self.eodhd_key = (os.getenv("EODHD_API_KEY") or "").strip()
        self.fred_key = (os.getenv("FRED_API_KEY") or "").strip()
        self.eodhd_enabled = (os.getenv("DEWAN_EODHD_ENABLED") or "false").lower() == "true"
        self.fred_enabled = (os.getenv("DEWAN_FRED_ENABLED") or "true").lower() == "true"
        # Default TTL intentionally long to avoid EODHD demo limits (20 req/day).
        self.eodhd_ttl_s = int(float(os.getenv("DEWAN_EODHD_TTL_S") or 21600))
        self.fred_ttl_s = int(float(os.getenv("DEWAN_FRED_TTL_S") or 3600))
        self.strict = (os.getenv("DEWAN_AI_STRICT") or "true").strip().lower() in ("1", "true", "yes", "on")

    async def collect(self, as_of: Optional[datetime] = None) -> CollectorResult:
        out: Dict[str, Any] = {}
        out["economic_calendar"] = await self._eodhd_calendar(as_of=as_of)
        out["macro"] = await self._fred_snapshot(as_of=as_of)
        return CollectorResult(ok=True, data=out, source="strategic_collector", fetched_at=time.time())

    async def _eodhd_calendar(self, *, as_of: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Fetch economic events from EODHD API for global coverage.

        Time alignment: if `as_of` is provided, we query a small window around it.
        To avoid future leakage, any event strictly after as_of will have `actual` redacted.
        """
        if not self.eodhd_enabled:
            return {"enabled": False, "items": []}
        if not self.eodhd_key:
            raise CollectorError("EODHD_API_KEY missing")

        base_dt = _to_utc(as_of) if isinstance(as_of, datetime) else datetime.now(timezone.utc)

        days_ahead = int(float(os.getenv("DEWAN_EODHD_DAYS_AHEAD") or 7))
        days_back = int(float(os.getenv("DEWAN_EODHD_DAYS_BACK") or 1))
        if days_ahead < 0:
            days_ahead = 0
        if days_back < 0:
            days_back = 0

        d1 = _date_str(base_dt - timedelta(days=days_back))
        d2 = _date_str(base_dt + timedelta(days=days_ahead))

        # Cache key includes date range and country filter
        country_filter = (os.getenv("DEWAN_EODHD_COUNTRIES") or "US").strip()
        eod_type = (os.getenv("DEWAN_EODHD_TYPE") or "").strip()
        country_key = country_filter if country_filter and country_filter.upper() not in ("ALL", "*") else "ALL"
        key = f"eodhd:calendar:{country_key}:{eod_type}:{d1}:{d2}"
        cached = self.cache.get(key, ttl_s=self.eodhd_ttl_s)
        if cached is not None:
            return cached

        url = (os.getenv("EODHD_BASE_URL") or "https://eodhd.com/api/economic-events").strip()
        params: Dict[str, Any] = {
            "api_token": self.eodhd_key,
            "fmt": "json",
            "from": d1,
            "to": d2,
            "limit": int(float(os.getenv("DEWAN_EODHD_MAX_ITEMS") or 50)),
        }
        if country_filter and country_filter.upper() not in ("ALL", "*"):
            params["country"] = country_filter
        if eod_type:
            params["type"] = eod_type

        client = self._get_client()
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json() or []
            if isinstance(data, dict) and data.get("error"):
                raise CollectorError(f"EODHD calendar API error: {data.get('error')}")
            if not isinstance(data, list):
                raise CollectorError("EODHD calendar response not a JSON list")

            items: List[Dict[str, Any]] = []
            for row in data:
                if not isinstance(row, dict):
                    continue
                r = _lower_keys(row)
                it = {
                    "country": r.get("country"),
                    "currency": r.get("currency"),
                    "category": r.get("category"),
                    "event": r.get("event"),
                    "date": r.get("date"),
                    "time": r.get("time"),
                    "importance": r.get("importance"),
                    "actual": r.get("actual"),
                    "previous": r.get("previous"),
                    "forecast": r.get("forecast"),
                    "reference": r.get("reference"),
                }
                ev_dt = _parse_event_dt(it)
                if ev_dt is not None and ev_dt > base_dt:
                    # Avoid leaking future realized values. Forecast/previous can remain.
                    it["actual"] = None
                    it["upcoming"] = True
                items.append(it)

            out = {
                "enabled": True,
                "as_of": base_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "range": {"d1": d1, "d2": d2, "country_filter": country_filter},
                "items": items,
                "source": "eodhd",
                "total_items": len(items),
            }
            self.cache.set(key, out)
            return out
        except CollectorError:
            raise
        except httpx.HTTPStatusError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 403:
                raise CollectorError(
                    "EODHD economic-events akses ditolak (HTTP 403). Biasanya karena plan/account tidak mendukung endpoint ini. "
                    "Solusi: upgrade plan EODHD atau set DEWAN_EODHD_ENABLED=false."
                ) from e
            raise CollectorError(f"EODHD calendar fetch failed: {_safe_http_err(e)}") from e
        except Exception as e:
            raise CollectorError(f"EODHD calendar fetch failed: {_safe_http_err(e)}")

    async def _fred_snapshot(self, *, as_of: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Fetch macro data from FRED.

        Time alignment: when `as_of` is provided, use `observation_end` so the value is
        the latest observation available at/before that date.
        """
        if not self.fred_enabled:
            return {"enabled": False, "series": {}}
        if not self.fred_key:
            raise CollectorError("FRED_API_KEY missing")

        base_dt = _to_utc(as_of) if isinstance(as_of, datetime) else datetime.now(timezone.utc)
        obs_end = _date_str(base_dt)

        series_env = (os.getenv("DEWAN_FRED_SERIES") or "").strip()
        if series_env:
            series = [s.strip() for s in series_env.split(",") if s.strip()]
        else:
            # Default key US economic indicators
            series = ["DFF", "CPIAUCSL", "UNRATE", "DTWEXBGS", "GDP", "HOUST", "INDPRO", "PAYEMS"]

        key = "fred:snapshot:" + ",".join(series) + f":end={obs_end}"
        cached = self.cache.get(key, ttl_s=self.fred_ttl_s)
        if cached is not None:
            return cached

        base_root = (os.getenv("FRED_BASE_URL") or "https://api.stlouisfed.org/fred").strip().rstrip("/")
        base = f"{base_root}/series/observations"
        client = self._get_client()
        out_series: Dict[str, Any] = {}
        errors: Dict[str, str] = {}

        for sid in series:
            params: Dict[str, Any] = {
                "series_id": sid,
                "api_key": self.fred_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
                "observation_end": obs_end,
            }
            try:
                resp = await client.get(base, params=params)
                resp.raise_for_status()
                data = resp.json() or {}
                obs = (data.get("observations") or [{}])[0]
                out_series[sid] = {
                    "date": obs.get("date"),
                    "value": obs.get("value"),
                }
            except Exception as e:
                err = _safe_http_err(e)
                errors[sid] = err
                out_series[sid] = {"error": err}

        if errors and self.strict:
            raise CollectorError("FRED fetch failed for: " + ", ".join(sorted(errors.keys())))

        out = {
            "enabled": True,
            "as_of": base_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "series": out_series,
            "source": "fred",
            "series_count": len([s for s in out_series.values() if isinstance(s, dict) and "error" not in s]),
        }
        if not errors:
            self.cache.set(key, out)
        return out
