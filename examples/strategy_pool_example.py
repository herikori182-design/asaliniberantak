#!/usr/bin/env python3
"""
Default Strategy Pool Usage Example
==================================

This example demonstrates how to use the default strategy pool
for quick backtesting and optimization.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
from strategies import get_all_strategies, get_strategy, list_strategies
from engine import backtest_strategy


async def test_all_default_strategies():
    """Test all default strategies on a single symbol"""

    print("=" * 60)
    print("Testing Default Strategy Pool")
    print("=" * 60)
    print()

    # Get all available strategies
    strategies = get_all_strategies()
    print(f"Available strategies: {len(strategies)}")
    for name in list_strategies():
        print(f"  - {name}")
    print()

    # Test symbol
    test_symbol = "XAUUSD"

    # Test each strategy
    results = {}

    for strategy_name, strategy_class in strategies.items():
        print(f"Testing {strategy_name}...")

        try:
            # Get strategy instance
            strategy = strategy_class()

            # Run backtest
            result = await backtest_strategy(strategy, test_symbol)
            stats = result['stats']

            # Store results
            results[strategy_name] = {
                'strategy_name': strategy.name,
                'win_rate': stats['winRate'],
                'total_trades': stats['totalTrades'],
                'return_pct': stats['returnPct'],
                'net_profit': stats['netProfit'],
                'long_wr': stats['longWinRate'],
                'short_wr': stats['shortWinRate'],
            }

            print(f"  ✓ Win Rate: {stats['winRate']:.2f}%")
            print(f"  ✓ Trades: {stats['totalTrades']}")
            print(f"  ✓ Return: {stats['returnPct']:.2f}%")
            print()

        except Exception as e:
            print(f"  ✗ Error: {e}")
            print()

    # Summary
    print("=" * 60)
    print("Summary Results")
    print("=" * 60)
    print()

    # Sort by win rate
    sorted_results = sorted(results.items(), key=lambda x: x[1]['win_rate'], reverse=True)

    print(f"{'Strategy':<25} {'Win Rate':<12} {'Trades':<8} {'Return':<10}")
    print("-" * 60)

    for strategy_name, metrics in sorted_results:
        print(f"{metrics['strategy_name']:<25} {metrics['win_rate']:>10.2f}% {metrics['total_trades']:>8} {metrics['return_pct']:>9.2f}%")

    print()


async def test_single_strategy():
    """Test a single strategy from the pool"""

    print("=" * 60)
    print("Testing Single Strategy from Pool")
    print("=" * 60)
    print()

    # Get a specific strategy
    try:
        strategy = get_strategy("ma_crossover")

        print(f"Strategy: {strategy.name}")
        print(f"Mode: {strategy.mode}")
        print(f"Timeframe: {strategy.preferredTimeframe}")
        print(f"Description: {strategy.description}")
        print()

        # Test on multiple symbols
        test_symbols = ["XAUUSD", "EURUSD", "GBPUSD"]

        for symbol in test_symbols:
            print(f"Backtesting {symbol}...")

            try:
                result = await backtest_strategy(strategy, symbol)
                stats = result['stats']

                print(f"  Win Rate: {stats['winRate']:.2f}%")
                print(f"  Trades: {stats['totalTrades']}")
                print(f"  Return: {stats['returnPct']:.2f}%")
                print()

            except Exception as e:
                print(f"  Error: {e}")
                print()

    except ValueError as e:
        print(f"Error: {e}")


async def test_custom_strategy_params():
    """Test strategy with custom parameters"""

    print("=" * 60)
    print("Testing Strategy with Custom Parameters")
    print("=" * 60)
    print()

    # Get strategy class and create with custom params
    from strategies import MACrossoverStrategy

    # Create strategy with custom parameters
    strategy = MACrossoverStrategy.create(
        fast_period=7,
        slow_period=25,
        allow_short=True,
        atr_stop_mult=2.0,
        atr_take_mult=3.0
    )

    print(f"Custom MA Crossover Strategy")
    print(f"  Fast EMA: 7")
    print(f"  Slow EMA: 25")
    print(f"  Stop Loss: 2.0x ATR")
    print(f"  Take Profit: 3.0x ATR")
    print()

    # Test the strategy
    result = await backtest_strategy(strategy, "XAUUSD")
    stats = result['stats']

    print(f"Results:")
    print(f"  Win Rate: {stats['winRate']:.2f}%")
    print(f"  Total Trades: {stats['totalTrades']}")
    print(f"  Net Profit: ${stats['netProfit']:.2f}")
    print(f"  Return: {stats['returnPct']:.2f}%")


async def test_optimization_ranges():
    """Show optimization ranges for strategies"""

    print("=" * 60)
    print("Strategy Optimization Ranges")
    print("=" * 60)
    print()

    from strategies import MACrossoverStrategy, RSIDivergenceStrategy

    # Get optimization ranges for different strategies
    strategies_to_check = [
        ("MA Crossover", MACrossoverStrategy),
        ("RSI Divergence", RSIDivergenceStrategy),
    ]

    for name, strategy_class in strategies_to_check:
        print(f"{name}:")
        ranges = strategy_class.get_optimization_ranges()

        for param, values in ranges.items():
            print(f"  {param}: {values}")

        print()


def main():
    """Main entry point"""

    print("Default Strategy Pool Examples")
    print("===============================")
    print()
    print("Choose an example:")
    print("1. Test all default strategies")
    print("2. Test single strategy from pool")
    print("3. Test strategy with custom parameters")
    print("4. Show optimization ranges")
    print("5. Run all examples")

    choice = input("\nEnter choice (1-5): ").strip()

    if choice == "1":
        asyncio.run(test_all_default_strategies())
    elif choice == "2":
        asyncio.run(test_single_strategy())
    elif choice == "3":
        asyncio.run(test_custom_strategy_params())
    elif choice == "4":
        asyncio.run(test_optimization_ranges())
    elif choice == "5":
        asyncio.run(test_all_default_strategies())
        asyncio.run(test_single_strategy())
        asyncio.run(test_custom_strategy_params())
        asyncio.run(test_optimization_ranges())
    else:
        print("Invalid choice")

    print("\nDone!")


if __name__ == "__main__":
    main()
