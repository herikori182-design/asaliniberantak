#!/usr/bin/env python3
"""
Example adapter for `TRADINGVIEW_MCP_TRANSPORT=command`.

This file is intentionally a template:
- Read request JSON from stdin.
- Return JSON to stdout with the project's tick schema.

Replace `_fetch_tick_from_your_mcp` with your TradingView MCP call logic.
"""

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict


def _fetch_tick_from_your_mcp(symbol: str) -> Dict[str, Any]:
    """
    TODO: implement your actual TradingView MCP request here.
    This mock response keeps the adapter executable for integration testing.
    """
    mid = 1.0
    spread = 0.0002
    return {
        "symbol": symbol,
        "bid": mid - (spread / 2),
        "ask": mid + (spread / 2),
        "mid": mid,
        "last": mid,
        "spread": spread,
        "volume": 0,
        "timestamp": int(time.time()),
        "source": "tradingview_mcp",
    }


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"error": "empty input"}))
        return

    req = json.loads(raw)
    arguments = req.get("arguments") or {}
    symbol = str(arguments.get("symbol") or "").strip().upper()
    if not symbol:
        print(json.dumps({"error": "symbol is required"}))
        return

    tick = _fetch_tick_from_your_mcp(symbol)
    # Return plain JSON payload (supported by fetcher parser).
    # You can also return wrapped MCP shape if needed.
    print(json.dumps(tick, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o)))


if __name__ == "__main__":
    main()
