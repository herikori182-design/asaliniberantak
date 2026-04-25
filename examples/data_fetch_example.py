#!/usr/bin/env python3
"""
Example: Fetch and Cache Market Data
====================================

This example demonstrates how to:
1. Fetch market data from Infoway API
2. Cache data for backtesting
3. Manage data cache
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import pandas as pd
from tools.infoway_forex_fetcher import InfowayForexFetcher, ForexScreenerInfoway
from engine.data import save_cached, get_cache_info, clear_cache, validate_ohlcv_data
from datetime import datetime, timedelta

# Symbols to fetch
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "XAGUSD"]
# Timeframes to fetch
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
# Days of historical data
DAYS = 365


async def fetch_market_data():
    """Fetch and cache market data for all symbols and timeframes"""

    print("=" * 60)
    print("Market Data Fetching Example")
    print("=" * 60)
    print()

    # Initialize fetcher
    print("Initializing Infoway Forex Fetcher...")
    fetcher = InfowayForexFetcher()

    if not fetcher.api_key:
        print("ERROR: INFOWAY_API_KEY not set in environment variables")
        print("Please set your API key in .env file")
        return

    print(f"API Key configured: {'*' * (len(fetcher.api_key) - 4)}{fetcher.api_key[-4:]}")
    print()

    # Clear existing cache (optional)
    print("Current cache status:")
    cache_info = get_cache_info()
    print(f"  Files: {cache_info['total_files']}")
    print(f"  Size: {cache_info['total_size_mb']} MB")
    print(f"  Symbols: {', '.join(cache_info['symbols'][:5])}")
    print()

    if cache_info['total_files'] > 0:
        clear_choice = input("Clear existing cache? (y/n): ").strip().lower()
        if clear_choice == 'y':
            deleted = clear_cache()
            print(f"Deleted {deleted} cache files")
            print()

    # Fetch data for each symbol and timeframe
    print("Fetching market data...")
    print()

    total_fetched = 0
    failed_fetches = []

    for symbol in SYMBOLS:
        print(f"Fetching {symbol}...")

        for tf in TIMEFRAMES:
            try:
                # Fetch OHLCV data
                df = fetcher.get_ohlcv(symbol, timeframe=tf, limit=500)

                if df is not None and not df.empty:
                    # Validate data quality
                    if validate_ohlcv_data(df):
                        # Prepare DataFrame for caching
                        df_cache = df.copy()
                        df_cache.index = pd.to_datetime(df_cache['time'], unit='s')
                        df_cache = df_cache[['open', 'high', 'low', 'close', 'volume']]
                        df_cache.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

                        # Save to cache
                        if save_cached(symbol, tf, df_cache, days=DAYS):
                            print(f"  ✓ {tf}: {len(df)} bars")
                            total_fetched += len(df)
                        else:
                            print(f"  ✗ {tf}: Failed to cache")
                            failed_fetches.append(f"{symbol}_{tf}")
                    else:
                        print(f"  ✗ {tf}: Data validation failed")
                        failed_fetches.append(f"{symbol}_{tf}")
                else:
                    print(f"  ✗ {tf}: No data returned")
                    failed_fetches.append(f"{symbol}_{tf}")

            except Exception as e:
                print(f"  ✗ {tf}: Error - {e}")
                failed_fetches.append(f"{symbol}_{tf}")

        print()

    # Summary
    print("=" * 60)
    print("Fetch Summary")
    print("=" * 60)
    print(f"Total bars fetched: {total_fetched}")
    print(f"Failed fetches: {len(failed_fetches)}")

    if failed_fetches:
        print("\nFailed:")
        for item in failed_fetches:
            print(f"  - {item}")

    print()

    # Final cache status
    print("Final cache status:")
    cache_info = get_cache_info()
    print(f"  Files: {cache_info['total_files']}")
    print(f"  Size: {cache_info['total_size_mb']} MB")
    print(f"  Symbols: {', '.join(cache_info['symbols'])}")
    print(f"  Timeframes: {', '.join(cache_info['timeframes'])}")
    print()

    # Clean up
    fetcher.close()
    print("Done!")


async def run_screener_example():
    """Run forex screener example"""

    print("=" * 60)
    print("Forex Screener Example")
    print("=" * 60)
    print()

    screener = ForexScreenerInfoway()

    print("Screening symbols...")
    print()

    try:
        results = screener.screen_symbols(SYMBOLS)

        if results:
            print(f"Screened {len(results)} symbols:")
            print()

            print(f"{'Symbol':<10} {'Price':<12} {'Spread':<10} {'RSI':<8} {'Trend':<10}")
            print("-" * 50)

            for r in results:
                price = f"{r['price']:.5f}"
                spread = f"{r['spread']:.5f}"
                rsi = f"{r.get('rsi', 0):.1f}"
                trend = r.get('ema_trend', 'N/A')

                print(f"{r['symbol']:<10} {price:<12} {spread:<10} {rsi:<8} {trend:<10}")

        else:
            print("No results returned")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        screener.fetcher.close()

    print()


async def run_tick_example():
    """Run real-time tick data example"""

    print("=" * 60)
    print("Real-Time Tick Data Example")
    print("=" * 60)
    print()

    fetcher = InfowayForexFetcher()

    print("Fetching tick data...")
    print()

    for symbol in SYMBOLS:
        try:
            tick = fetcher.get_tick(symbol)

            if tick:
                print(f"{symbol}:")
                print(f"  Bid: {tick['bid']:.5f}")
                print(f"  Ask: {tick['ask']:.5f}")
                print(f"  Mid: {tick['mid']:.5f}")
                print(f"  Spread: {tick['spread']:.5f}")
                print(f"  Last: {tick['last']:.5f}")
                print(f"  Volume: {tick['volume']:.2f}")
                print(f"  Timestamp: {tick['timestamp']}")
                print()
            else:
                print(f"{symbol}: No data available")
                print()

        except Exception as e:
            print(f"{symbol}: Error - {e}")
            print()

    fetcher.close()
    print("Done!")


def main():
    """Main entry point"""

    print("Market Data Fetching Examples")
    print("==============================")
    print()
    print("Choose an option:")
    print("1. Fetch and cache market data")
    print("2. Run forex screener")
    print("3. Get real-time tick data")
    print("4. All examples")

    choice = input("\nEnter choice (1-4): ").strip()

    if choice == "1":
        asyncio.run(fetch_market_data())
    elif choice == "2":
        asyncio.run(run_screener_example())
    elif choice == "3":
        asyncio.run(run_tick_example())
    elif choice == "4":
        asyncio.run(fetch_market_data())
        asyncio.run(run_screener_example())
        asyncio.run(run_tick_example())
    else:
        print("Invalid choice")

    print("\nDone!")


if __name__ == "__main__":
    main()
