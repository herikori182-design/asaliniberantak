#!/usr/bin/env python3
"""
Integration-style checks for TradingView MCP transports in InfowayForexFetcher.

Run:
    python tests/test_tradingview_mcp_transport.py
"""

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.infoway_forex_fetcher import InfowayForexFetcher


class _TickHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (BaseHTTPRequestHandler naming)
        _ = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
        payload = {
            "result": {
                "symbol": "XAUUSD",
                "bid": 2345.10,
                "ask": 2345.30,
                "last": 2345.20,
                "volume": 12.0,
                "timestamp": 1710000000,
            }
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return


class TestTradingViewMCPTransport(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old_env)

    def test_command_transport_with_example_adapter(self):
        os.environ["TICK_COLLECTOR_SOURCE"] = "tradingview_mcp"
        os.environ["TRADINGVIEW_MCP_TRANSPORT"] = "command"
        os.environ["TRADINGVIEW_MCP_TOOL"] = "get_tick"
        os.environ["TRADINGVIEW_MCP_COMMAND"] = "python tools/tradingview_mcp_adapter_example.py"

        f = InfowayForexFetcher()
        tick = f.get_tick("XAUUSD")
        f.close()

        self.assertIsNotNone(tick)
        self.assertEqual(tick["symbol"], "XAUUSD")
        self.assertIn("bid", tick)
        self.assertIn("ask", tick)
        self.assertEqual(tick["source"], "tradingview_mcp")

    def test_command_transport_with_wrapped_content(self):
        os.environ["TICK_COLLECTOR_SOURCE"] = "tradingview_mcp"
        os.environ["TRADINGVIEW_MCP_TRANSPORT"] = "command"
        os.environ["TRADINGVIEW_MCP_TOOL"] = "get_tick"

        script = Path("tests/_tmp_mcp_wrapper.py")
        script.write_text(
            "\n".join(
                [
                    "import json",
                    "print(json.dumps({'result': {'content': [{'type':'text','text': json.dumps({'symbol':'EURUSD','bid':1.1,'ask':1.2,'last':1.15,'timestamp':1710000000})}]}}))",
                ]
            ),
            encoding="utf-8",
        )
        try:
            os.environ["TRADINGVIEW_MCP_COMMAND"] = f"python {script}"
            f = InfowayForexFetcher()
            tick = f.get_tick("EURUSD")
            f.close()
            self.assertIsNotNone(tick)
            self.assertEqual(tick["symbol"], "EURUSD")
            self.assertAlmostEqual(tick["mid"], 1.15, places=8)
        finally:
            if script.exists():
                script.unlink()

    def test_http_transport(self):
        os.environ["TICK_COLLECTOR_SOURCE"] = "tradingview_mcp"
        os.environ["TRADINGVIEW_MCP_TRANSPORT"] = "http"
        os.environ["TRADINGVIEW_MCP_TOOL"] = "get_tick"

        server = HTTPServer(("127.0.0.1", 0), _TickHandler)
        host, port = server.server_address
        os.environ["TRADINGVIEW_MCP_URL"] = f"http://{host}:{port}/mcp/tools/call"
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            f = InfowayForexFetcher()
            tick = f.get_tick("XAUUSD")
            f.close()
            self.assertIsNotNone(tick)
            self.assertEqual(tick["symbol"], "XAUUSD")
            self.assertAlmostEqual(tick["spread"], 0.2, places=8)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
