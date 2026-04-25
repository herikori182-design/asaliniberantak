import asyncio
import logging
from collections import deque
from typing import Dict, Tuple, Deque, Any, List
import os
from pathlib import Path

import httpx
try:
    import websockets  # type: ignore
except ImportError:
    websockets = None
import pandas as pd
import json
import time

from engine.errors import AuthError

logger = logging.getLogger(__name__)

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    s = str(raw).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return default


class ConfigService:
    """
    Simple in-memory + env-backed key storage for InfoWay.
    Source of truth for API key used by InfoWayManager.
    """

    def __init__(self):
        # Keys are expected to be provided via ENV (`INFOWAY_API_KEY` / split keys)
        # or via Telegram commands (/renew_infoway, /renew_infoway_stock).
        # We keep defaults empty to avoid accidentally using stale/invalid tokens.
        self._infoway_key_common: str = ""
        self._infoway_key_stock: str = ""

    def load_from_env(self):
        # Best-effort: load repo-local .env for standalone scripts/tests.
        try:
            from dotenv import load_dotenv  # type: ignore

            load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
        except Exception:
            pass

        env_api = (os.getenv("INFOWAY_API_KEY") or "").strip()
        env_common = (os.getenv("INFOWAY_COMMON_API_KEY") or "").strip()
        env_stock = (os.getenv("INFOWAY_STOCK_API_KEY") or "").strip()

        # Common confusion: multiple keys set but only one is actually used.
        # We do NOT print key values here (secrets). We only clarify precedence.
        if env_common and env_api and env_common != env_api:
            logger.warning(
                "Both INFOWAY_COMMON_API_KEY and INFOWAY_API_KEY are set. "
                "Using INFOWAY_COMMON_API_KEY for common/forex. "
                "Unset INFOWAY_COMMON_API_KEY if you intended to use INFOWAY_API_KEY."
            )
        if env_stock and (env_common or env_api):
            logger.info("INFOWAY_STOCK_API_KEY is set; using it for stock endpoints.")

        common = (env_common or env_api or "").strip()
        # If a dedicated stock key isn't provided, default to the common key.
        stock = env_stock.strip()
        if common:
            self._infoway_key_common = common
        if stock:
            self._infoway_key_stock = stock
        elif common and not self._infoway_key_stock:
            self._infoway_key_stock = common
        # If only stock key is provided, also use it for common by default.
        if not self._infoway_key_common and self._infoway_key_stock:
            self._infoway_key_common = self._infoway_key_stock

    def get_infoway_key(self, business: str = "common") -> str:
        if business == "stock":
            return self._infoway_key_stock or self._infoway_key_common
        return self._infoway_key_common

    def set_infoway_key(self, key: str, business: str = "common"):
        if business == "stock":
            self._infoway_key_stock = key.strip()
        else:
            self._infoway_key_common = key.strip()


def _tf_to_infoway(tf: str) -> Tuple[int, int]:
    """
    Map TF string to (klineType, klineNum) per InfoWay REST.
    klineType: 1=1m,2=5m,3=15m,4=30m,5=1h,7=4h,8=1d
    klineNum: bar count to request.
    """
    mapping = {
        "1m": 1,
        "5m": 2,
        "15m": 3,
        "30m": 4,
        "1h": 5,
        "4h": 7,
        "1d": 8,
    }
    return mapping.get(tf, 3), 240


class InfoWayManager:
    """
    Manages InfoWay REST/WS and buffers.
    """

    def __init__(self, cfg: ConfigService):
        self.cfg = cfg
        self.buffers: Dict[Tuple[str, str], Deque[Dict[str, Any]]] = {}
        self.lock = asyncio.Lock()
        try:
            timeout_s = float(os.getenv("INFOWAY_TIMEOUT_S") or 30.0)
        except Exception:
            timeout_s = 30.0
        connect_s = min(10.0, max(1.0, timeout_s))
        # By default, bypass global proxy env vars for InfoWay requests.
        # This avoids accidental proxy poisoning (e.g. HTTP_PROXY=127.0.0.1:9).
        # Set INFOWAY_TRUST_ENV_PROXY=true if you explicitly want to use env proxies.
        trust_env_proxy = _env_bool("INFOWAY_TRUST_ENV_PROXY", False)
        self.session = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=connect_s),
            trust_env=trust_env_proxy,
        )
        if not trust_env_proxy:
            proxy_envs = [k for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY") if (os.getenv(k) or "").strip()]
            if proxy_envs:
                logger.info(
                    "InfoWay REST ignoring env proxy vars by default (%s). "
                    "Set INFOWAY_TRUST_ENV_PROXY=true to use them.",
                    ", ".join(proxy_envs),
                )
        self._req_lock = asyncio.Lock()
        self._backoff_until = 0.0
        self._last_req = 0.0
        self._rest_last_fetch: Dict[Tuple[str, str], float] = {}  # (symbol,tf) -> monotonic
        self.ws_tasks: Dict[str, asyncio.Task] = {}  # key: business ("common","stock")
        self.ws_clients: Dict[str, httpx.AsyncClient] = {}
        self.ws_symbols: Dict[str, set] = {"common": set(), "stock": set()}
        self.ws_tfs: Dict[str, set] = {"common": set(), "stock": set()}
        # meta info for health
        self.ws_meta: Dict[str, Dict[str, Any]] = {
            "common": {
                "connected": False,
                "last_msg": None,
                "last_hb": None,
                "last_error": None,
                "retry": 0,
                "last_rest_status": None,
                "last_rest_error": None,
                "last_rest_ts": None,
            },
            "stock": {
                "connected": False,
                "last_msg": None,
                "last_hb": None,
                "last_error": None,
                "retry": 0,
                "last_rest_status": None,
                "last_rest_error": None,
                "last_rest_ts": None,
            },
        }

    async def close(self):
        # Close WS tasks first to avoid "Task was destroyed but it is pending" on shutdown.
        tasks = list(self.ws_tasks.values())
        for t in tasks:
            try:
                if t and not t.done():
                    t.cancel()
            except Exception:
                pass
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                pass
        try:
            self.ws_tasks.clear()
        except Exception:
            pass

        for c in list(self.ws_clients.values()):
            try:
                await c.aclose()
            except Exception:
                pass
        try:
            self.ws_clients.clear()
        except Exception:
            pass

        try:
            await self.session.aclose()
        except Exception:
            pass

    async def reload_key(self):
        # Restart WS connections with new key
        await self.close()
        self.ws_tasks = {}
        self.ws_clients = {}
        self.ws_symbols = {"common": set(), "stock": set()}
        self.ws_tfs = {"common": set(), "stock": set()}
        return True

    async def ensure_ws(self, business: str, symbols: List[str], tfs: List[str]):
        if websockets is None:
            logger.warning("websockets package not installed; WS disabled. Using REST only.")
            return
        business = "stock" if business == "stock" else "common"
        if business == "common":
            import os
            allow_common_ws = (os.getenv("INFOWAY_WS_COMMON") or "true").strip().lower() in ("1", "true", "yes", "on")
            if not allow_common_ws:
                logger.info("WS common skipped; using REST for forex/common. (set INFOWAY_WS_COMMON=true to enable)")
                return
        # Default behavior: skip stock WS to avoid plan/connection limits; can be enabled explicitly.
        if business == "stock":
            import os
            allow_stock_ws = (os.getenv("INFOWAY_WS_STOCK") or "false").strip().lower() in ("1", "true", "yes", "on")
            if not allow_stock_ws:
                logger.info("WS stock skipped; using REST for stocks. (set INFOWAY_WS_STOCK=true to enable)")
                return
        self.ws_symbols[business].update(symbols)
        self.ws_tfs[business].update(tfs)
        if business in self.ws_tasks and not self.ws_tasks[business].done():
            return
        task = asyncio.create_task(self._ws_loop(business))
        self.ws_tasks[business] = task

    async def _ws_loop(self, business: str):
        key = self.cfg.get_infoway_key(business)
        if not key:
            logger.warning("INFOWAY_API_KEY not set; WS %s not started", business)
            return
        url = f"wss://data.infoway.io/ws?business={business}&apikey={key}"
        try:
            self.ws_meta[business]["retry"] = self.ws_meta[business].get("retry", 0) + 1
            async with websockets.connect(url, ping_interval=None) as ws:
                logger.info("InfoWay WS %s connected", business)
                self.ws_meta[business]["connected"] = True
                self.ws_meta[business]["last_msg"] = time.time()
                self.ws_meta[business]["last_hb"] = time.time()
                self.ws_meta[business]["last_error"] = None
                # subscribe existing symbols/tfs
                await self._ws_subscribe(ws, business)
                last_hb = time.monotonic()
                async for msg in ws:
                    if msg:
                        await self._handle_ws_message(msg)
                        self.ws_meta[business]["last_msg"] = time.time()
                    now = time.monotonic()
                    if now - last_hb > 25:
                        await ws.send(json.dumps({"code": 10010}))
                        last_hb = now
                        self.ws_meta[business]["last_hb"] = time.time()
        except asyncio.CancelledError:
            logger.info("InfoWay WS %s cancelled", business)
            return
        except Exception as e:
            logger.error("InfoWay WS %s error: %s", business, e)
            try:
                self.ws_meta[business]["last_error"] = str(e)
            except Exception:
                pass
        finally:
            self.ws_meta[business]["connected"] = False
            logger.info("InfoWay WS %s closed", business)

    async def _ws_subscribe(self, ws, business: str):
        arr = []
        # Free plan: max 10 streams per connection
        max_streams = 10
        count = 0
        for sym in self.ws_symbols[business]:
            for tf in self.ws_tfs[business]:
                if count >= max_streams:
                    break
                kline_type, _ = _tf_to_infoway(tf)
                arr.append({"type": kline_type, "codes": sym})
                count += 1
            if count >= max_streams:
                break
        if not arr:
            return
        payload = {"code": 10006, "data": {"arr": arr}, "trace": "sub-" + business}
        try:
            await ws.send(json.dumps(payload))
            logger.info("InfoWay WS %s subscribe %d streams (capped)", business, len(arr))
        except Exception as e:
            logger.error("Subscribe error %s: %s", business, e)

    def _kline_type_to_tf(self, kline_type: int) -> str:
        inv = {
            1: "1m",
            2: "5m",
            3: "15m",
            4: "30m",
            5: "1h",
            7: "4h",
            8: "1d",
        }
        return inv.get(kline_type, "15m")

    async def _handle_ws_message(self, data: str):
        try:
            obj = json.loads(data)
        except Exception:
            return
        if not isinstance(obj, dict):
            return
        code = obj.get("code")
        if code != 10008:
            return
        rows = obj.get("data") or []
        if not isinstance(rows, list):
            return
        async with self.lock:
            for r in rows:
                if not isinstance(r, dict):
                    continue
                sym = r.get("code") or r.get("symbol")
                kt = r.get("klineType") or r.get("kline_type")
                tf = self._kline_type_to_tf(kt) if kt is not None else None
                if not sym or not tf:
                    continue
                key = (sym, tf)
                buf = self.buffers.setdefault(key, deque(maxlen=1000))
                try:
                    row = {
                        "OpenTime": pd.to_datetime(r.get("time")),
                        "Open": float(r.get("open", 0.0)),
                        "High": float(r.get("high", 0.0)),
                        "Low": float(r.get("low", 0.0)),
                        "Close": float(r.get("close", 0.0)),
                        "Volume": float(r.get("volume", 0.0)),
                    }
                    buf.append(row)
                except Exception:
                    continue

    def health(self) -> Dict[str, Any]:
        return {
            "buffers": {f"{k[0]}_{k[1]}": len(v) for k, v in self.buffers.items()},
            "ws_running": {k: (t and not t.done()) for k, t in self.ws_tasks.items()},
            "ws_symbols": {k: list(v) for k, v in self.ws_symbols.items()},
            "ws_tfs": {k: list(v) for k, v in self.ws_tfs.items()},
            "ws_meta": self.ws_meta,
        }
    async def fetch_rest(
        self,
        symbol: str,
        tf: str,
        *,
        kline_num: int | None = None,
        timestamp: int | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV (best-effort) via InfoWay REST.

        Uses the v2 endpoint:
          https://data.infoway.io/{business}/v2/batch_kline   (POST JSON)

        Notes:
        - `timestamp` (seconds) can be used as an "as of" cursor for historical paging.
        - Returned rows are normalized to keys: OpenTime, Open, High, Low, Close, Volume.
        """
        is_stock = symbol.endswith(".US")
        business = "stock" if is_stock else "common"
        key = self.cfg.get_infoway_key(business)
        if not key:
            logger.warning("INFOWAY_API_KEY not set; cannot fetch %s %s", symbol, tf)
            try:
                self.ws_meta[business]["last_rest_error"] = "missing_api_key"
                self.ws_meta[business]["last_rest_status"] = None
                self.ws_meta[business]["last_rest_ts"] = time.time()
            except Exception:
                pass
            return []

        kline_type, default_kline_num = _tf_to_infoway(tf)
        try:
            kline_num_i = int(kline_num) if kline_num is not None else int(default_kline_num)
        except Exception:
            kline_num_i = int(default_kline_num)
        if kline_num_i <= 0:
            kline_num_i = int(default_kline_num)

        base = f"https://data.infoway.io/{business}/v2/batch_kline"

        payload: Dict[str, Any] = {
            "klineType": int(kline_type),
            "klineNum": int(kline_num_i),
            "codes": str(symbol),
        }
        if timestamp is not None:
            try:
                payload["timestamp"] = int(timestamp)
            except Exception:
                pass

        try:
            async with self._req_lock:
                now = time.monotonic()
                if now < self._backoff_until:
                    logger.warning("InfoWay backoff active; skip %s %s", symbol, tf)
                    return []
                delay = max(0.0, 1.0 - (now - self._last_req))
                if delay > 0:
                    await asyncio.sleep(delay)

                headers = {
                    # Docs use `apiKey`; keep exact casing for compatibility with some gateways/WAFs.
                    "apiKey": key,
                    "User-Agent": "marketbot/1.0",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
                resp = await self.session.post(base, headers=headers, json=payload)
                self._last_req = time.monotonic()
                resp.raise_for_status()
                data = resp.json() or {}

            try:
                self.ws_meta[business]["last_rest_error"] = None
                self.ws_meta[business]["last_rest_status"] = resp.status_code
                self.ws_meta[business]["last_rest_ts"] = time.time()
            except Exception:
                pass

            arr = data.get("data") or []
            if not isinstance(arr, list):
                arr = []

            out: List[Dict[str, Any]] = []
            for block in arr:
                if not isinstance(block, dict):
                    continue
                # v2 returns: {"s": "TSLA.US", "respList": [...]}
                bsym = block.get("s") or block.get("code") or block.get("symbol")
                if bsym and str(bsym).strip() and str(bsym).strip() != str(symbol).strip():
                    continue
                resp_list = block.get("respList") or block.get("data") or []
                if not isinstance(resp_list, list):
                    continue
                for row in resp_list:
                    if not isinstance(row, dict):
                        continue
                    try:
                        ts = row.get("time") or row.get("t")
                        if ts is None:
                            continue
                        opentime = pd.to_datetime(float(ts), unit="s")
                        out.append(
                            {
                                "OpenTime": opentime,
                                "Open": float(row.get("open") or row.get("o") or 0.0),
                                "High": float(row.get("high") or row.get("h") or 0.0),
                                "Low": float(row.get("low") or row.get("l") or 0.0),
                                "Close": float(row.get("close") or row.get("c") or 0.0),
                                "Volume": float(row.get("volume") or row.get("v") or 0.0),
                            }
                        )
                    except Exception:
                        continue
            return out

        except httpx.HTTPStatusError as e:
            try:
                status = getattr(getattr(e, "response", None), "status_code", None)
                body = ""
                try:
                    body = (e.response.text or "").strip() if getattr(e, "response", None) is not None else ""
                except Exception:
                    body = ""
                if body and len(body) > 200:
                    body = body[:200] + " ...<truncated>"
                self.ws_meta[business]["last_rest_status"] = status
                self.ws_meta[business]["last_rest_error"] = f"HTTP {status}: {body}" if body else f"HTTP {status}"
                self.ws_meta[business]["last_rest_ts"] = time.time()
            except Exception:
                pass
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code in (401, 403):
                # Fail-fast: invalid/expired token. Caller should stop loops and ask user to renew.
                raise AuthError(
                    provider=f"infoway:{business}",
                    status_code=int(status_code or 401),
                    message=str((self.ws_meta.get(business) or {}).get("last_rest_error") or "").strip(),
                ) from e
            if status_code == 429:
                self._backoff_until = time.monotonic() + 60
                logger.warning("InfoWay 429 for %s %s; backoff 60s", symbol, tf)
            else:
                try:
                    msg = e.response.text
                except Exception:
                    msg = ""
                logger.error("InfoWay REST error %s %s: %s %s", symbol, tf, e, msg)
            return []
        except Exception as e:
            try:
                self.ws_meta[business]["last_rest_status"] = None
                self.ws_meta[business]["last_rest_error"] = f"{type(e).__name__}: {e}"
                self.ws_meta[business]["last_rest_ts"] = time.time()
            except Exception:
                pass
            logger.error("InfoWay REST error %s %s: %s: %s", symbol, tf, type(e).__name__, e)
            return []

    async def get_ohlcv_history(self, symbol: str, tf: str, days: int = 365) -> pd.DataFrame:
        """
        Fetch historical OHLCV for the last `days` days (best-effort) using InfoWay v2 paging.

        This is intended for offline caching (engine/data.py), not for live screening.
        """
        try:
            days_i = int(days)
        except Exception:
            days_i = 365
        if days_i <= 0:
            return pd.DataFrame()

        # Cursor paging uses epoch seconds.
        end_ts = int(time.time())
        cutoff_ts = end_ts - int(days_i) * 24 * 60 * 60

        # Batch size per REST call. In practice, many InfoWay plans return empty for klineNum > 500
        # (HTTP 200 but no candles), so we probe & fall back automatically.
        import os

        try:
            requested_batch_size = int(float(os.getenv("INFOWAY_HIST_KLINE_NUM") or 500))
        except Exception:
            requested_batch_size = 500
        # Per docs, klineNum is max 500 (per symbol). Clamp to avoid triggering WAF/restrict.
        requested_batch_size = max(50, min(requested_batch_size, 500))

        candidate_batch_sizes: List[int] = []
        for n in [requested_batch_size, 400, 240, 200, 120, 60]:
            if n >= 50 and n not in candidate_batch_sizes:
                candidate_batch_sizes.append(n)

        batch_size: int | None = None
        first_chunk: List[Dict[str, Any]] = []
        for cand in candidate_batch_sizes:
            chunk = await self.fetch_rest(symbol, tf, kline_num=cand, timestamp=end_ts)
            if chunk:
                batch_size = cand
                first_chunk = chunk
                break
        if batch_size is None:
            return pd.DataFrame()

        max_pages_env = os.getenv("INFOWAY_HIST_MAX_PAGES")
        if max_pages_env is not None and str(max_pages_env).strip() != "":
            try:
                max_pages = int(float(max_pages_env))
            except Exception:
                max_pages = 250
            if max_pages < 1:
                max_pages = 1
        else:
            tf_minutes = {
                "1m": 1,
                "5m": 5,
                "15m": 15,
                "30m": 30,
                "1h": 60,
                "4h": 240,
                "1d": 1440,
            }.get(tf)
            if tf_minutes:
                est_bars = int((days_i * 1440) / tf_minutes) + 50
                pages_needed = int((est_bars + batch_size - 1) // batch_size)
                max_pages = min(max(pages_needed + 2, 10), 2000)
            else:
                max_pages = 250

        seen_ts: set[int] = set()
        rows: List[Dict[str, Any]] = []

        cursor_ts = end_ts
        last_min_ts: int | None = None

        for page in range(max_pages):
            chunk = (
                first_chunk
                if page == 0
                else await self.fetch_rest(symbol, tf, kline_num=batch_size, timestamp=cursor_ts)
            )
            if not chunk:
                break

            # Dedup and collect
            min_ts: int | None = None
            for r in chunk:
                try:
                    ot = r.get("OpenTime")
                    if ot is None:
                        continue
                    ts_i = int(pd.Timestamp(ot).value // 1_000_000_000)
                except Exception:
                    continue
                if ts_i in seen_ts:
                    continue
                seen_ts.add(ts_i)
                rows.append(r)
                if min_ts is None or ts_i < min_ts:
                    min_ts = ts_i

            if min_ts is None:
                break

            # Stop once we covered the time window.
            if min_ts <= cutoff_ts:
                break

            # Defensive: ensure cursor always moves backward.
            if last_min_ts is not None and min_ts >= last_min_ts:
                break
            last_min_ts = min_ts

            cursor_ts = max(0, int(min_ts) - 1)
            if cursor_ts <= cutoff_ts:
                break

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if df.empty or "OpenTime" not in df.columns:
            return pd.DataFrame()

        df = df.sort_values("OpenTime").drop_duplicates(subset=["OpenTime"], keep="last")
        df = df.set_index("OpenTime")

        # Trim strictly to last `days` calendar days.
        cutoff_dt = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=days_i)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)
        df = df[df.index >= cutoff_dt]
        return df

    async def get_ohlcv(self, symbol: str, tf: str, min_bars: int = 120) -> pd.DataFrame:
        """Return recent klines.

        - Prefer WS buffers when WS is connected.
        - If WS is disabled/unavailable, periodically refresh buffers via REST (so data doesn't go stale).

        Override refresh interval with `INFOWAY_REST_REFRESH_S`.
        """
        key = (symbol, tf)

        def _refresh_s(tf_in: str) -> float:
            import os

            raw = (os.getenv("INFOWAY_REST_REFRESH_S") or "").strip()
            if raw:
                try:
                    v = float(raw)
                    if v > 0:
                        return v
                except Exception:
                    pass

            tf_s = (tf_in or "").strip().lower()
            if tf_s == "1m":
                return 15.0
            if tf_s == "5m":
                return 30.0
            if tf_s == "15m":
                return 60.0
            if tf_s == "30m":
                return 120.0
            if tf_s == "1h":
                return 300.0
            if tf_s == "4h":
                return 900.0
            if tf_s == "1d":
                return 3600.0
            return 60.0

        async with self.lock:
            buf = self.buffers.setdefault(key, deque(maxlen=1000))
            should_fetch = len(buf) < min_bars

            if not should_fetch:
                # If WS isn't connected (or disabled), periodically refresh buffer via REST.
                sym_up = str(symbol or "").upper()
                business = "stock" if sym_up.endswith(".US") else "common"
                ws_connected = bool((self.ws_meta.get(business) or {}).get("connected"))
                if not ws_connected:
                    now = time.monotonic()
                    last = float(self._rest_last_fetch.get(key, 0.0) or 0.0)
                    if last <= 0.0 or (now - last) >= _refresh_s(tf):
                        should_fetch = True

            if should_fetch:
                rows = await self.fetch_rest(symbol, tf)
                # Always bump last_fetch (even if empty) to avoid hot loops on transient failures.
                self._rest_last_fetch[key] = time.monotonic()
                if rows:
                    buf.clear()
                    for r in rows:
                        buf.append(r)

            if not buf:
                return pd.DataFrame()
            df = pd.DataFrame(list(buf))
            df = df.sort_values("OpenTime").set_index("OpenTime")
            return df


# Convenience mapper for stocks
def map_stock_symbol(symbol: str) -> str:
    if symbol.endswith(".US"):
        return symbol
    return f"{symbol}.US"
