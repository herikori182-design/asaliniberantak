#!/usr/bin/env python3
"""
Example Trading Strategy Using the Research System
================================================

This example demonstrates how to:
1. Define a trading strategy using the DSL (Domain Specific Language)
2. Run backtests on historical data
3. Analyze results and optimize parameters
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import json
from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams, backtest_strategy
from engine.data import save_cached, get_cache_info, clear_cache
from datetime import datetime

# Example 1: Simple Moving Average Crossover Strategy
def create_ma_crossover_strategy():
    """Create a simple MA crossover strategy"""

    strategy = Strategy(
        id="ma_crossover_v1",
        name="Simple MA Crossover",
        mode="INTRADAY",
        preferredTimeframe="1h",
        description="Simple moving average crossover strategy with RSI filter",
        indicators=[
            IndicatorSpec(id="fast_ma", type="EMA", period=9),
            IndicatorSpec(id="slow_ma", type="EMA", period=21),
            IndicatorSpec(id="rsi", type="RSI", period=14),
        ],
        ruleSet=RuleSet(
            entryLong=[
                RuleCond(op="crossOver", left="fast_ma", right="slow_ma"),
                RuleCond(op="gt", left="rsi", right=50),
            ],
            entryShort=[
                RuleCond(op="crossUnder", left="fast_ma", right="slow_ma"),
                RuleCond(op="lt", left="rsi", right=50),
            ],
        ),
        backtestParams=BacktestParams(
            allowShort=True,
            atrStopMult=1.5,
            atrTakeMult=2.0,
        )
    )

    return strategy


# Example 2: RSI Divergence Strategy
def create_rsi_divergence_strategy():
    """Create an RSI divergence strategy"""

    strategy = Strategy(
        id="rsi_divergence_v1",
        name="RSI Divergence",
        mode="SCALPING",
        preferredTimeframe="15m",
        description="RSI divergence strategy with Bollinger Bands confirmation",
        indicators=[
            IndicatorSpec(id="rsi", type="RSI", period=14),
            IndicatorSpec(id="boll", type="BOLL", period=20, stdDev=2.0),
        ],
        ruleSet=RuleSet(
            entryLong=[
                RuleCond(op="lt", left="rsi", right=30),
                RuleCond(op="touchLowerBand", left="close", right="boll.lower"),
            ],
            entryShort=[
                RuleCond(op="gt", left="rsi", right=70),
                RuleCond(op="touchUpperBand", left="close", right="boll.upper"),
            ],
        ),
        backtestParams=BacktestParams(
            allowShort=True,
            atrStopMult=1.2,
            atrTakeMult=1.8,
        )
    )

    return strategy


# Example 3: Fibonacci Retracement Strategy
def create_fibonacci_strategy():
    """Create a Fibonacci retracement strategy"""

    strategy = Strategy(
        id="fib_retracement_v1",
        name="Fibonacci Retracement",
        mode="INTRADAY",
        preferredTimeframe="1h",
        description="Fibonacci retracement strategy with trend confirmation",
        indicators=[
            IndicatorSpec(id="fib", type="FIB", period=2, period2=2),
            IndicatorSpec(id="ema200", type="EMA", period=200),
        ],
        ruleSet=RuleSet(
            entryLong=[
                RuleCond(op="gt", left="close", right="ema200"),
                RuleCond(op="fibAtOrAbove", left="close", right="fib", level="0.618"),
            ],
            entryShort=[
                RuleCond(op="lt", left="close", right="ema200"),
                RuleCond(op="fibAtOrBelow", left="close", right="fib", level="0.618"),
            ],
        ),
        backtestParams=BacktestParams(
            allowShort=True,
            atrStopMult=1.5,
            atrTakeMult=2.5,
        )
    )

    return strategy


async def run_strategy_examples():
    """Run example strategies with backtests"""

    print("=" * 60)
    print("Trading Strategy Research Examples")
    print("=" * 60)
    print()

    # Check cache status
    print("Checking data cache status...")
    cache_info = get_cache_info()
    print(f"Cache directory: {cache_info['cache_dir']}")
    print(f"Total files: {cache_info['total_files']}")
    print(f"Total size: {cache_info['total_size_mb']} MB")
    print(f"Available symbols: {', '.join(cache_info['symbols'][:5])}...")
    print()

    # Test symbols
    test_pairs = ["XAUUSD", "EURUSD"]

    # Example 1: MA Crossover
    print("-" * 60)
    print("Example 1: MA Crossover Strategy")
    print("-" * 60)

    ma_strategy = create_ma_crossover_strategy()
    print(f"Strategy: {ma_strategy.name}")
    print(f"Mode: {ma_strategy.mode}")
    print(f"Timeframe: {ma_strategy.preferredTimeframe}")

    for pair in test_pairs:
        print(f"\nBacktesting {pair}...")
        try:
            result = await backtest_strategy(ma_strategy, pair)
            stats = result['stats']

            print(f"  Win Rate: {stats['winRate']:.2f}%")
            print(f"  Total Trades: {stats['totalTrades']}")
            print(f"  Net Profit: ${stats['netProfit']:.2f}")
            print(f"  Return: {stats['returnPct']:.2f}%")

            # Directional performance
            print(f"  Long WR: {stats['longWinRate']:.2f}% ({stats['longTrades']} trades)")
            print(f"  Short WR: {stats['shortWinRate']:.2f}% ({stats['shortTrades']} trades)")

        except Exception as e:
            print(f"  Error: {e}")

    print()

    # Example 2: RSI Divergence
    print("-" * 60)
    print("Example 2: RSI Divergence Strategy")
    print("-" * 60)

    rsi_strategy = create_rsi_divergence_strategy()
    print(f"Strategy: {rsi_strategy.name}")
    print(f"Mode: {rsi_strategy.mode}")
    print(f"Timeframe: {rsi_strategy.preferredTimeframe}")

    for pair in test_pairs:
        print(f"\nBacktesting {pair}...")
        try:
            result = await backtest_strategy(rsi_strategy, pair)
            stats = result['stats']

            print(f"  Win Rate: {stats['winRate']:.2f}%")
            print(f"  Total Trades: {stats['totalTrades']}")
            print(f"  Net Profit: ${stats['netProfit']:.2f}")
            print(f"  Return: {stats['returnPct']:.2f}%")

        except Exception as e:
            print(f"  Error: {e}")

    print()

    # Example 3: Fibonacci Strategy
    print("-" * 60)
    print("Example 3: Fibonacci Retracement Strategy")
    print("-" * 60)

    fib_strategy = create_fibonacci_strategy()
    print(f"Strategy: {fib_strategy.name}")
    print(f"Mode: {fib_strategy.mode}")
    print(f"Timeframe: {fib_strategy.preferredTimeframe}")

    for pair in test_pairs:
        print(f"\nBacktesting {pair}...")
        try:
            result = await backtest_strategy(fib_strategy, pair)
            stats = result['stats']

            print(f"  Win Rate: {stats['winRate']:.2f}%")
            print(f"  Total Trades: {stats['totalTrades']}")
            print(f"  Net Profit: ${stats['netProfit']:.2f}")
            print(f"  Return: {stats['returnPct']:.2f}%")

        except Exception as e:
            print(f"  Error: {e}")

    print()
    print("=" * 60)
    print("Examples completed!")
    print("=" * 60)


def save_strategy_examples():
    """Save example strategies to JSON files"""

    examples_dir = Path(__file__).parent / "strategies"
    examples_dir.mkdir(exist_ok=True)

    strategies = [
        create_ma_crossover_strategy(),
        create_rsi_divergence_strategy(),
        create_fibonacci_strategy(),
    ]

    for strategy in strategies:
        filepath = examples_dir / f"{strategy.id}.json"
        with open(filepath, 'w') as f:
            f.write(strategy.model_dump_json(indent=2))
        print(f"Saved: {filepath}")


def main():
    """Main entry point"""

    print("Trading Strategy Research System")
    print("================================")
    print()
    print("Choose an option:")
    print("1. Run strategy backtests (requires cached data)")
    print("2. Save example strategies to JSON files")
    print("3. Both")

    choice = input("\nEnter choice (1-3): ").strip()

    if choice in ["1", "3"]:
        print("\nRunning strategy examples...")
        asyncio.run(run_strategy_examples())

    if choice in ["2", "3"]:
        print("\nSaving strategy examples...")
        save_strategy_examples()

    print("\nDone!")


if __name__ == "__main__":
    main()
