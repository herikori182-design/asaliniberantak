#!/usr/bin/env python3
"""
Infoway Forex Data Fetcher
===========================
Professional-grade forex data from Infoway API

API Documentation:
- Trades: https://docs.infoway.io/rest-api/http-endpoints/get-trade
- Depth: https://docs.infoway.io/rest-api/http-endpoints/get-depth
- Candlesticks: https://docs.infoway.io/en-docs/rest-api/market-data/post-candlestick

Features:
- Real-time bid/ask from order book
- 40+ forex currency pairs
- Institutional-grade data
- Sub-millisecond latency
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
import requests
import pandas as pd
import asyncio
import aiohttp
import json
import shlex
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import time
import re
import threading
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class InfowayForexFetcher:
    """Fetch real-time forex data from Infoway API"""

    # Infoway API Configuration
    BASE_URL = "https://data.infoway.io"
    API_KEY = os.getenv("INFOWAY_COMMON_API_KEY") or os.getenv("INFOWAY_API_KEY") or ""
    # Symbol mapping (standard forex pairs -> InfoWay code)
    SYMBOL_MAP = {
        # Forex pairs
        "EURUSD": "EURUSD",
        "GBPUSD": "GBPUSD",
        "USDJPY": "USDJPY",
        "USDCHF": "USDCHF",
        "USDCAD": "USDCAD",
        "AUDUSD": "AUDUSD",
        "NZDUSD": "NZDUSD",
        "EURGBP": "EURGBP",
        "EURJPY": "EURJPY",
        "GBPJPY": "GBPJPY",
        "EURCHF": "EURCHF",
        "EURAUD": "EURAUD",
        "EURNZD": "EURNZD",
        "GBPCHF": "GBPCHF",
        "GBPAUD": "GBPAUD",
        "AUDJPY": "AUDJPY",
        "CADJPY": "CADJPY",
        "CHFJPY": "CHFJPY",
        "NZDJPY": "NZDJPY",
        "AUDCAD": "AUDCAD",
        "AUDCHF": "AUDCHF",
        "CADCHF": "CADCHF",
        "EURNZD": "EURNZD",
        "EURCAD": "EURCAD",
        "GBPAUD": "GBPAUD",
        "GBPNZD": "GBPNZD",
        "GBPCAD": "GBPCAD",

        # Metals
        "XAUUSD": "XAUUSD",
        "XAGUSD": "XAGUSD",
        "XPTUSD": "XPTUSD",  # Platinum
        "XPDUSD": "XPDUSD",  # Palladium

        # Cross pairs
        "NZDCAD": "NZDCAD",
        "NZDCHF": "NZDCHF",
    }

    # Kline/Timeframe mapping for Infoway API
    KLINE_TYPE_MAP = {
        '1m': 1,
        '5m': 2,
        '15m': 3,
        '30m': 4,
        '1h': 5,
        '4h': 7,
        '1d': 8,
    }
    def __init__(self, api_key: str = None):
        self.api_key = api_key or self.API_KEY
        self.tick_source = str(os.getenv("TICK_COLLECTOR_SOURCE") or "infoway").strip().lower()
        self.tradingview_mcp_transport = str(os.getenv("TRADINGVIEW_MCP_TRANSPORT") or "http").strip().lower()
        self.tradingview_mcp_url = str(os.getenv("TRADINGVIEW_MCP_URL") or "").strip()
        self.tradingview_mcp_tool = str(os.getenv("TRADINGVIEW_MCP_TOOL") or "get_tick").strip()
        self.tradingview_mcp_command = str(os.getenv("TRADINGVIEW_MCP_COMMAND") or "").strip()
        self._trust_env_proxy = str(os.getenv("INFOWAY_TRUST_ENV_PROXY") or "false").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self._session = requests.Session()
        self._session.trust_env = self._trust_env_proxy
        self.session = None
        self._headers = {
            # NOTE: Docs use `apiKey` header. While HTTP headers are case-insensitive,
            # some gateways/WAFs are buggy, so we follow docs exactly.
            'apiKey': self.api_key,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'trading-research-system/infoway-forex-fetcher'
        }
        self._fx_code_re = re.compile(r"^[A-Z]{6}$")

        # Global (per-instance) throttling to avoid free-plan rate limits.
        # Default: 1 request/second (Free). Override via INFOWAY_MAX_RPS (e.g. 10 for Pro).
        try:
            max_rps = float(os.getenv("INFOWAY_MAX_RPS") or os.getenv("INFOWAY_RPS") or 1.0)
        except Exception:
            max_rps = 1.0
        if not (max_rps > 0):
            max_rps = 1.0
        self._min_interval_s = 1.0 / max_rps
        self._last_req_mono = 0.0
        self._rate_lock = threading.Lock()
        if not self._trust_env_proxy:
            proxy_envs = [k for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY") if (os.getenv(k) or "").strip()]
            if proxy_envs:
                print(
                    "[INFO] InfowayForexFetcher bypassing env proxy vars by default "
                    f"({', '.join(proxy_envs)}). Set INFOWAY_TRUST_ENV_PROXY=true to enable."
                )

    def _request(self, method: str, url: str, *, timeout: int = 10, **kwargs):
        """Throttled requests wrapper (safe for multi-thread callers)."""
        with self._rate_lock:
            if self._min_interval_s > 0 and self._last_req_mono:
                elapsed = time.monotonic() - self._last_req_mono
                wait = self._min_interval_s - elapsed
                if wait > 0:
                    time.sleep(wait)
            resp = self._session.request(method, url, headers=self._headers, timeout=timeout, **kwargs)
            self._last_req_mono = time.monotonic()
            return resp
    def _get_infoway_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Infoway format"""
        s = str(symbol or "").strip().upper()
        if not s:
            return ""

        # InfoWay v2/common endpoints expect bare FX codes (EURUSD, XAUUSD), not *.FX.
        if s.endswith(".FX"):
            s = s[:-3]
        # Preserve explicit stock symbol form.
        if s.endswith(".US"):
            return s

        mapped = self.SYMBOL_MAP.get(s)
        if mapped:
            return mapped

        # Default heuristic for FX/metals pairs: 6 letters in bare format.
        if self._fx_code_re.fullmatch(s):
            return s

        return s

    def get_tick(self, symbol: str) -> Optional[Dict]:
        """
        Get current tick data with bid/ask from order book

        Returns dict with: bid, ask, spread, last_price, timestamp, volume
        """
        if self.tick_source == "tradingview_mcp":
            return self._get_tick_from_tradingview_mcp(symbol)

        try:
            infoway_symbol = self._get_infoway_symbol(symbol)
            if not infoway_symbol:
                return None

            # Get order book depth for bid/ask
            depth_url = f"{self.BASE_URL}/common/batch_depth/{infoway_symbol}"

            response = self._request("GET", depth_url, timeout=10)

            if response.status_code != 200:
                print(f"Infoway depth error for {symbol}: HTTP {response.status_code}")
                return None

            data = response.json()

            if data.get('ret') != 200 or not data.get('data'):
                return None

            depth_data = data['data'][0]

            # Extract bid/ask from order book
            # a = ask prices and volumes, b = bid prices and volumes
            ask_prices = depth_data.get('a', [[]])[0]
            bid_prices = depth_data.get('b', [[]])[0]

            if not ask_prices or not bid_prices:
                return None

            best_bid = float(bid_prices[0])  # Highest bid
            best_ask = float(ask_prices[0])  # Lowest ask

            # Get latest trade for last price
            trade_url = f"{self.BASE_URL}/common/batch_trade/{infoway_symbol}"
            trade_response = self._request("GET", trade_url, timeout=10)

            last_price = best_bid  # Default to bid if no trade data
            volume = 0

            if trade_response.status_code == 200:
                trade_data = trade_response.json()
                if trade_data.get('data'):
                    latest_trade = trade_data['data'][0]
                    last_price = float(latest_trade.get('p', best_bid))
                    volume = float(latest_trade.get('v', 0))
                    timestamp_ms = latest_trade.get('t', int(time.time() * 1000))
                else:
                    timestamp_ms = depth_data.get('t', int(time.time() * 1000))
            else:
                timestamp_ms = depth_data.get('t', int(time.time() * 1000))

            spread = best_ask - best_bid

            return {
                'symbol': symbol,
                'bid': best_bid,
                'ask': best_ask,
                'spread': spread,
                'last': last_price,
                'mid': (best_bid + best_ask) / 2,
                'volume': volume,
                'timestamp': datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
                'source': 'infoway'
            }

        except Exception as e:
            print(f"Infoway tick error for {symbol}: {e}")
            return None

    def _coerce_tick_payload(self, symbol: str, payload: Dict[str, Any]) -> Optional[Dict]:
        """Normalize TradingView MCP tick payload to shared output schema."""
        if not isinstance(payload, dict):
            return None
        try:
            bid = payload.get("bid")
            ask = payload.get("ask")
            last = payload.get("last") or payload.get("price") or payload.get("close")
            mid = payload.get("mid")
            spread = payload.get("spread")
            volume = payload.get("volume", 0)
            ts = payload.get("timestamp") or payload.get("time")

            bid_f = float(bid) if bid is not None else None
            ask_f = float(ask) if ask is not None else None
            last_f = float(last) if last is not None else None
            mid_f = float(mid) if mid is not None else None

            # Derive missing pricing fields from available values.
            if bid_f is None and ask_f is not None and spread is not None:
                bid_f = float(ask_f) - float(spread)
            if ask_f is None and bid_f is not None and spread is not None:
                ask_f = float(bid_f) + float(spread)
            if mid_f is None:
                if bid_f is not None and ask_f is not None:
                    mid_f = (bid_f + ask_f) / 2
                elif last_f is not None:
                    mid_f = last_f
            if bid_f is None and mid_f is not None:
                bid_f = mid_f
            if ask_f is None and mid_f is not None:
                ask_f = mid_f
            if last_f is None and mid_f is not None:
                last_f = mid_f

            if bid_f is None or ask_f is None or mid_f is None:
                return None

            spread_f = float(spread) if spread is not None else (ask_f - bid_f)
            if ts is None:
                timestamp = datetime.now(timezone.utc)
            elif isinstance(ts, (int, float)):
                ts_float = float(ts)
                if ts_float > 100_000_000_000:
                    ts_float = ts_float / 1000
                timestamp = datetime.fromtimestamp(ts_float, tz=timezone.utc)
            elif isinstance(ts, str):
                try:
                    timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    timestamp = datetime.now(timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)

            return {
                "symbol": str(payload.get("symbol") or symbol).upper(),
                "bid": bid_f,
                "ask": ask_f,
                "spread": spread_f,
                "last": last_f,
                "mid": mid_f,
                "volume": float(volume or 0),
                "timestamp": timestamp,
                "source": "tradingview_mcp",
            }
        except Exception:
            return None

    def _extract_mcp_result(self, body: Dict[str, Any]) -> Optional[Dict]:
        """Extract structured tool result from common MCP HTTP bridge response shapes."""
        if not isinstance(body, dict):
            return None
        result = body.get("result")
        if isinstance(result, dict):
            if isinstance(result.get("content"), list):
                for item in result["content"]:
                    if not isinstance(item, dict):
                        continue
                    text = item.get("text")
                    if not isinstance(text, str):
                        continue
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            return parsed
                    except Exception:
                        continue
            return result

        content = body.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if not isinstance(text, str):
                    continue
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    continue
        return body if isinstance(body, dict) else None

    def _get_tick_from_tradingview_mcp(self, symbol: str) -> Optional[Dict]:
        """
        Get tick data from TradingView MCP bridge.

        Expected env:
        - TICK_COLLECTOR_SOURCE=tradingview_mcp
        - TRADINGVIEW_MCP_TRANSPORT=http|command
        - TRADINGVIEW_MCP_URL=<HTTP endpoint that accepts MCP tool call payload> (http mode)
        - TRADINGVIEW_MCP_TOOL=<tool name, default: get_tick>
        - TRADINGVIEW_MCP_COMMAND=<adapter command> (command mode)
        """
        if self.tradingview_mcp_transport == "command":
            return self._get_tick_from_tradingview_mcp_command(symbol)
        return self._get_tick_from_tradingview_mcp_http(symbol)

    def _get_tick_from_tradingview_mcp_http(self, symbol: str) -> Optional[Dict]:
        """HTTP transport: send MCP tool call payload to bridge URL."""
        if not self.tradingview_mcp_url:
            print("TradingView MCP URL not configured (TRADINGVIEW_MCP_URL).")
            return None
        try:
            payload = {
                "tool": self.tradingview_mcp_tool,
                "arguments": {"symbol": symbol},
            }
            response = self._request("POST", self.tradingview_mcp_url, timeout=10, json=payload)
            if response.status_code != 200:
                print(f"TradingView MCP tick error for {symbol}: HTTP {response.status_code}")
                return None
            body = response.json()
            parsed = self._extract_mcp_result(body)
            return self._coerce_tick_payload(symbol, parsed or {})
        except Exception as e:
            print(f"TradingView MCP tick error for {symbol}: {e}")
            return None

    def _get_tick_from_tradingview_mcp_command(self, symbol: str) -> Optional[Dict]:
        """
        Command transport: execute adapter command and pass request JSON via stdin.

        Adapter contract:
        - stdin: {"tool":"get_tick","arguments":{"symbol":"XAUUSD"}}
        - stdout: any JSON shape compatible with `_extract_mcp_result`.
        """
        if not self.tradingview_mcp_command:
            print("TradingView MCP command not configured (TRADINGVIEW_MCP_COMMAND).")
            return None
        try:
            args = shlex.split(self.tradingview_mcp_command)
            if not args:
                return None
            payload = {
                "tool": self.tradingview_mcp_tool,
                "arguments": {"symbol": symbol},
            }
            proc = subprocess.run(
                args,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip()
                print(f"TradingView MCP command tick error for {symbol}: rc={proc.returncode} {stderr}")
                return None
            stdout = (proc.stdout or "").strip()
            if not stdout:
                return None

            # Some adapters may log around the JSON. Try exact parse first, then line-wise.
            try:
                body = json.loads(stdout)
            except Exception:
                body = None
                for line in reversed(stdout.splitlines()):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        body = json.loads(line)
                        break
                    except Exception:
                        continue
                if body is None:
                    return None

            parsed = self._extract_mcp_result(body if isinstance(body, dict) else {"result": body})
            return self._coerce_tick_payload(symbol, parsed or {})
        except Exception as e:
            print(f"TradingView MCP command tick error for {symbol}: {e}")
            return None

    def get_ohlcv(self, symbol: str, timeframe: str = '15m', limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Get OHLCV candlestick data

        Args:
            symbol: Currency pair
            timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d
            limit: Number of candles (max 500)
        """
        try:
            infoway_symbol = self._get_infoway_symbol(symbol)
            if not infoway_symbol:
                return None
            kline_type = self.KLINE_TYPE_MAP.get(timeframe, 3)

            url = f"{self.BASE_URL}/common/v2/batch_kline"

            payload = {
                "klineType": kline_type,
                "klineNum": min(limit, 500),
                "codes": infoway_symbol
            }

            response = self._request("POST", url, timeout=10, json=payload)

            if response.status_code != 200:
                print(f"Infoway OHLCV error for {symbol}: {response.status_code}")
                return None

            data = response.json()

            if data.get('ret') != 200 or not data.get('data'):
                return None

            candle_data = data['data'][0]
            resp_list = candle_data.get('respList', [])

            if not resp_list:
                return None

            # Convert to DataFrame
            records = []
            for candle in resp_list:
                # Support both short keys (t/o/h/l/c/v) and long keys (time/open/high/low/close/volume).
                ts = candle.get('time') if isinstance(candle, dict) else None
                if ts is None and isinstance(candle, dict):
                    ts = candle.get('t')
                if ts is None:
                    continue
                try:
                    ts_i = int(float(ts))
                except Exception:
                    continue
                # Some sources return ms.
                if ts_i > 100_000_000_000:
                    ts_i = int(ts_i // 1000)

                def _num(*keys, default=0.0) -> float:
                    for k in keys:
                        try:
                            v = candle.get(k) if isinstance(candle, dict) else None
                        except Exception:
                            v = None
                        if v is None:
                            continue
                        try:
                            return float(v)
                        except Exception:
                            continue
                    return float(default)

                records.append({
                    'time': ts_i,
                    'open': _num('open', 'o'),
                    'high': _num('high', 'h'),
                    'low': _num('low', 'l'),
                    'close': _num('close', 'c'),
                    'volume': _num('volume', 'v'),
                })

            df = pd.DataFrame(records)

            # Convert timestamp
            df['datetime'] = pd.to_datetime(df['time'], unit='s')

            return df

        except Exception as e:
            print(f"Infoway OHLCV error for {symbol}: {e}")
            return None
    def get_ohlcv_batch(self, symbols: List[str], timeframe: str = '15m', limit: int = 100) -> Dict[str, pd.DataFrame]:
        """Batch OHLCV fetch (avoids 429 by using multi-code request)."""
        out: Dict[str, pd.DataFrame] = {}
        try:
            if not symbols:
                return out

            kline_type = self.KLINE_TYPE_MAP.get(timeframe, 3)
            codes = ','.join([self._get_infoway_symbol(s) for s in symbols if self._get_infoway_symbol(s)])
            if not codes:
                return out
            url = f"{self.BASE_URL}/common/v2/batch_kline"
            payload = {
                "klineType": int(kline_type),
                "klineNum": int(min(limit, 500)),
                "codes": codes,
            }

            response = self._request("POST", url, timeout=15, json=payload)
            if response.status_code != 200:
                return out

            data = response.json() or {}
            if data.get('ret') != 200 or not data.get('data'):
                return out

            for block in data.get('data') or []:
                if not isinstance(block, dict):
                    continue
                sym = str(block.get('s') or '').replace('.FX', '').strip().upper()
                resp_list = block.get('respList') or []
                if not sym or not isinstance(resp_list, list) or not resp_list:
                    continue

                records = []
                for candle in resp_list:
                    try:
                        ts = candle.get('time') if isinstance(candle, dict) else None
                        if ts is None and isinstance(candle, dict):
                            ts = candle.get('t')
                        if ts is None:
                            continue
                        ts_i = int(float(ts))
                        if ts_i > 100_000_000_000:
                            ts_i = int(ts_i // 1000)

                        def _num(*keys, default=0.0) -> float:
                            for k in keys:
                                try:
                                    v = candle.get(k) if isinstance(candle, dict) else None
                                except Exception:
                                    v = None
                                if v is None:
                                    continue
                                try:
                                    return float(v)
                                except Exception:
                                    continue
                            return float(default)

                        records.append({
                            'time': ts_i,
                            'open': _num('open', 'o'),
                            'high': _num('high', 'h'),
                            'low': _num('low', 'l'),
                            'close': _num('close', 'c'),
                            'volume': _num('volume', 'v', default=0.0),
                        })
                    except Exception:
                        continue

                if not records:
                    continue

                df = pd.DataFrame(records)
                df['datetime'] = pd.to_datetime(df['time'], unit='s')
                out[sym] = df

        except Exception:
            return out

        return out


    def get_multiple_ticks(self, symbols: List[str]) -> List[Dict]:
        """Get tick data for multiple symbols"""
        if self.tick_source == "tradingview_mcp":
            results = []
            for symbol in symbols:
                tick = self.get_tick(symbol)
                if tick:
                    results.append(tick)
            return results

        results = []

        # Batch request with multiple symbols
        infoway_symbols = [self._get_infoway_symbol(s) for s in symbols]
        infoway_symbols = [s for s in infoway_symbols if s]
        symbols_str = ','.join(infoway_symbols)
        if not symbols_str:
            return results

        try:
            # Get depth for all symbols
            depth_url = f"{self.BASE_URL}/common/batch_depth/{symbols_str}"
            response = self._request("GET", depth_url, timeout=15)

            if response.status_code != 200:
                # Avoid spamming fallback calls (can trigger rate limits / WAF). Let caller fall back to Yahoo/MT5.
                print(f"Infoway batch depth error: HTTP {response.status_code}")
                return results

            data = response.json()

            if data.get('ret') != 200 or not data.get('data'):
                return []

            for depth_data in data['data']:
                symbol_raw = depth_data.get('s', '')
                # Map back to standard symbol (strip any suffixes like .FX)
                standard_symbol = str(symbol_raw).replace('.FX', '').strip().upper()
                if not standard_symbol:
                    continue

                ask_prices = depth_data.get('a', [[]])[0]
                bid_prices = depth_data.get('b', [[]])[0]

                if not ask_prices or not bid_prices:
                    continue

                best_bid = float(bid_prices[0])
                best_ask = float(ask_prices[0])
                timestamp_ms = depth_data.get('t', int(time.time() * 1000))

                results.append({
                    'symbol': standard_symbol,
                    'bid': best_bid,
                    'ask': best_ask,
                    'spread': best_ask - best_bid,
                    'timestamp': datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
                    'source': 'infoway'
                })

        except Exception as e:
            print(f"Infoway batch tick error: {e}")

        return results

    def get_symbol_list(self) -> List[str]:
        """Get list of available forex symbols"""
        try:
            url = f"{self.BASE_URL}/common/basic/symbols"
            params = {'type': 'FOREX'}

            response = self._request("GET", url, timeout=10, params=params)

            if response.status_code != 200:
                return []

            data = response.json()

            if data.get('ret') != 200 or not data.get('data'):
                return []

            symbols = []
            for item in data['data']:
                symbol = item.get('symbol', '')
                if not symbol:
                    continue
                std_symbol = str(symbol).replace('.FX', '').strip().upper()
                if std_symbol:
                    symbols.append(std_symbol)

            return symbols

        except Exception as e:
            print(f"Infoway symbol list error: {e}")
            return list(self.SYMBOL_MAP.keys())

    def close(self):
        """Close session"""
        try:
            self._session.close()
        except Exception:
            pass
        if self.session:
            self.session.close()


class ForexScreenerInfoway:
    """Forex screener using Infoway API"""

    def __init__(self, api_key: str = None):
        self.fetcher = InfowayForexFetcher(api_key)

    def screen_symbols(self, symbols: List[str]) -> List[Dict]:
        """Screen multiple symbols with technical analysis"""
        results = []

        for symbol in symbols:
            tick = self.fetcher.get_tick(symbol)
            if not tick:
                continue

            # Get OHLCV for technical analysis
            ohlcv = self.fetcher.get_ohlcv(symbol, timeframe='15m', limit=50)

            analysis = {
                'symbol': symbol,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'price': tick['mid'],
                'bid': tick['bid'],
                'ask': tick['ask'],
                'spread': tick['spread'],
                'source': 'infoway'
            }

            # Basic technical indicators if OHLCV available
            if ohlcv is not None and len(ohlcv) > 0:
                analysis['rsi'] = self._calculate_rsi(ohlcv)
                analysis['ema_trend'] = self._get_ema_trend(ohlcv)
                analysis['volume'] = ohlcv.iloc[-1]['volume']

            results.append(analysis)

        return results

    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate RSI indicator"""
        try:
            closes = df['close']
            delta = closes.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
        except:
            return 50.0

    def _get_ema_trend(self, df: pd.DataFrame, period: int = 20) -> str:
        """Get EMA trend direction"""
        try:
            closes = df['close']
            ema = closes.ewm(span=period).mean().iloc[-1]
            current = closes.iloc[-1]

            if current > ema:
                return "BULLISH"
            else:
                return "BEARISH"
        except:
            return "NEUTRAL"


# Test function
def main():
    """Test Infoway forex fetcher"""
    print("=" * 60)
    print("Infoway Forex Data Fetcher Test")
    print("=" * 60)
    print()

    # Test symbols
    symbols = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "XAGUSD"]

    print(f"Testing {len(symbols)} symbols...")
    print()

    fetcher = InfowayForexFetcher()

    # Test individual ticks
    for symbol in symbols:
        print(f"Fetching {symbol}...")
        tick = fetcher.get_tick(symbol)

        if tick:
            print(f"  [OK] Price: {tick['mid']:.5f}")
            print(f"    Bid: {tick['bid']:.5f} | Ask: {tick['ask']:.5f}")
            print(f"    Spread: {tick['spread']:.5f}")
            print(f"    Last: {tick['last']:.5f}")
        else:
            print(f"  [X] Failed to fetch data")
        print()

    # Test OHLCV
    print("Testing OHLCV data for EURUSD...")
    ohlcv = fetcher.get_ohlcv("EURUSD", timeframe="15m", limit=10)

    if ohlcv is not None:
        print(f"  [OK] Fetched {len(ohlcv)} candles")
        print(f"  Latest: O={ohlcv.iloc[-1]['open']:.5f} "
              f"H={ohlcv.iloc[-1]['high']:.5f} "
              f"L={ohlcv.iloc[-1]['low']:.5f} "
              f"C={ohlcv.iloc[-1]['close']:.5f}")
    else:
        print("  [X] Failed to fetch OHLCV")

    # Test screener
    print()
    print("=" * 60)
    print("Screening Test")
    print("=" * 60)
    print()

    screener = ForexScreenerInfoway()
    results = screener.screen_symbols(["EURUSD", "GBPUSD", "XAUUSD"])

    for r in results:
        print(f"{r['symbol']}: {r['price']:.5f} | "
              f"RSI: {r.get('rsi', 0):.1f} | "
              f"Trend: {r.get('ema_trend', 'N/A')} | "
              f"Spread: {r['spread']:.5f}")

    fetcher.close()


if __name__ == "__main__":
    main()
