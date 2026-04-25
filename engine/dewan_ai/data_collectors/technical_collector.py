import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from .base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        v = os.getenv(name)
        if v is None or str(v).strip() == "":
            return float(default)
        return float(v)
    except Exception:
        return float(default)


class TechnicalCollector(BaseCollector):
    """
    Extra technical data (external):
    - Binance order book depth (no key) for crypto symbols like BTCUSDT.

    NOTE: Orderbook depth is inherently live-only. For historical evaluation (as_of far
    from now), this collector must return disabled to avoid future-data leakage.
    """

    def __init__(self, timeout_s: float = 15.0):
        super().__init__(timeout_s=timeout_s)
        self.depth_enabled = _env_bool("DEWAN_BINANCE_DEPTH_ENABLED", True)
        # If your network uses SSL interception and causes CERTIFICATE_VERIFY_FAILED,
        # you can set DEWAN_BINANCE_SSL_VERIFY=false (NOT recommended for public networks).
        self.ssl_verify = _env_bool("BINANCE_SSL_VERIFY", True)
        self.ssl_verify = _env_bool("DEWAN_BINANCE_SSL_VERIFY", self.ssl_verify)
        self.connect_timeout_s = _env_float("BINANCE_CONNECT_TIMEOUT_S", 4.0)
        self.depth_ttl_s = 10  # very short; still cache to avoid spam
        self.live_window_s = _env_float("DEWAN_BINANCE_DEPTH_LIVE_WINDOW_S", 600.0)

    def _is_historical(self, as_of: Optional[datetime]) -> bool:
        if as_of is None:
            return False
        try:
            window = float(self.live_window_s)
        except Exception:
            window = 600.0
        try:
            return abs(time.time() - float(as_of.timestamp())) > max(0.0, window)
        except Exception:
            return True

    async def collect(self, pair: str, as_of: Optional[datetime] = None) -> CollectorResult:
        data = {"orderbook": await self._binance_depth(pair, as_of=as_of)}
        return CollectorResult(ok=True, data=data, source="technical_collector", fetched_at=time.time())

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(self.timeout_s, connect=self.connect_timeout_s)
            self._client = httpx.AsyncClient(timeout=timeout, verify=self.ssl_verify)
        return self._client

    async def _binance_depth(self, pair: str, *, as_of: Optional[datetime] = None) -> Dict[str, Any]:
        if not self.depth_enabled:
            return {"enabled": False, "source": "binance", "reason": "disabled_by_env"}
        if self._is_historical(as_of):
            return {
                "enabled": False,
                "symbol": (pair or "").upper(),
                "source": "binance",
                "ssl_verify": bool(self.ssl_verify),
                "reason": "historical_not_supported",
            }
        up = (pair or "").upper()
        if not up.endswith("USDT"):
            return {"enabled": False}
        key = f"binance:depth:{up}"
        cached = self.cache.get(key, ttl_s=self.depth_ttl_s)
        if cached is not None:
            return cached
        base_url = (os.getenv("BINANCE_BASE_URL") or "https://api.binance.com").strip().rstrip("/")
        url = f"{base_url}/api/v3/depth"
        params = {"symbol": up, "limit": 100}
        client = self._get_client()
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json() or {}
            bids = data.get("bids") or []
            asks = data.get("asks") or []

            def _top(arr):
                out = []
                for p, q in arr[:10]:
                    try:
                        out.append({"price": float(p), "qty": float(q)})
                    except Exception:
                        continue
                return out

            top_bids = _top(bids)
            top_asks = _top(asks)
            best_bid = top_bids[0]["price"] if top_bids else None
            best_ask = top_asks[0]["price"] if top_asks else None
            spread = (best_ask - best_bid) if (best_ask is not None and best_bid is not None) else None
            bid_qty = sum(x["qty"] for x in top_bids) if top_bids else 0.0
            ask_qty = sum(x["qty"] for x in top_asks) if top_asks else 0.0
            imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty) if (bid_qty + ask_qty) > 0 else 0.0
            out = {
                "enabled": True,
                "symbol": up,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "top10": {"bids": top_bids, "asks": top_asks},
                "top10_qty": {"bids": bid_qty, "asks": ask_qty, "imbalance": imbalance},
                "source": "binance",
                "ssl_verify": bool(self.ssl_verify),
            }
            self.cache.set(key, out)
            return out
        except Exception as e:
            # Best-effort: do not fail the whole Dewan flow if Binance is blocked.
            # Use any cached value (even stale) if available.
            cached_any = self.cache.get_any(key)
            if isinstance(cached_any, dict) and cached_any:
                out = dict(cached_any)
                out["stale"] = True
                out["ssl_verify"] = bool(self.ssl_verify)
                out["error"] = f"binance_depth_failed:{type(e).__name__}:{e}"
                return out
            return {
                "enabled": False,
                "symbol": up,
                "source": "binance",
                "ssl_verify": bool(self.ssl_verify),
                "error": f"binance_depth_failed:{type(e).__name__}:{e}",
            }
