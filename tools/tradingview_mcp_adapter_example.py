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


def _run_pinescript_from_your_mcp(script: str, symbol: str, timeframe: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    TODO: replace with real MCP Pine execution logic.
    Returns a simple mocked structure to demonstrate fetcher integration.
    """
    return {
        "ok": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "barsProcessed": 100,
        "signals": [{"bar": 99, "action": "BUY"}],
        "meta": {
            "engine": "mock",
            "scriptPreview": script[:80],
            "inputs": inputs,
        },
    }


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"error": "empty input"}))
        return

    req = json.loads(raw)
    tool = str(req.get("tool") or "").strip()
    arguments = req.get("arguments") or {}
    symbol = str(arguments.get("symbol") or "").strip().upper()

    if tool == "get_tick":
        if not symbol:
            print(json.dumps({"error": "symbol is required"}))
            return
        tick = _fetch_tick_from_your_mcp(symbol)
        print(json.dumps(tick, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o)))
        return

    if tool == "run_pinescript":
        script = str(arguments.get("script") or "").strip()
        timeframe = str(arguments.get("timeframe") or "15")
        inputs = arguments.get("inputs") or {}
        if not symbol or not script:
            print(json.dumps({"error": "symbol and script are required"}))
            return
        result = _run_pinescript_from_your_mcp(
            script=script,
            symbol=symbol,
            timeframe=timeframe,
            inputs=inputs if isinstance(inputs, dict) else {},
        )
        print(json.dumps(result))
        return

    print(json.dumps({"error": f"unsupported tool: {tool}"}))


if __name__ == "__main__":
    main()
