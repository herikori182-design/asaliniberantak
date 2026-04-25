#!/usr/bin/env python3
"""
Research and Optimization Example
================================

This example demonstrates how to use the research and optimization
capabilities to find the best strategy parameters.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
from engine.research import (
    StrategyOptimizer, ResearchConfig, OptimizationMethod, ObjectiveMetric
)
from strategies import MACrossoverStrategy


async def run_basic_optimization():
    """Run basic strategy optimization"""

    print("=" * 60)
    print("Basic Strategy Optimization")
    print("=" * 60)
    print()

    # Get base strategy
    base_strategy = MACrossoverStrategy.create()

    # Define parameter ranges for optimization
    parameter_ranges = {
        "fast_ema_period": [7, 9, 11],
        "slow_ema_period": [19, 21, 23],
        "bt_atrStopMult": [1.0, 1.5, 2.0],
        "bt_atrTakeMult": [1.5, 2.0, 2.5],
    }

    # Create optimization config
    config = ResearchConfig(
        symbol="XAUUSD",
        timeframe="1h",
        optimization_method=OptimizationMethod.GRID_SEARCH,
        objective=ObjectiveMetric.WIN_RATE,
        max_iterations=27,  # 3 * 3 * 3 = 27 combinations
        parallel_jobs=1
    )

    # Run optimization
    optimizer = StrategyOptimizer(config)

    print("Starting optimization...")
    print(f"Method: {config.optimization_method.value}")
    print(f"Objective: {config.objective.value}")
    print(f"Max iterations: {config.max_iterations}")
    print(f"Parameter combinations to test: {len(optimizer._generate_grid_combinations(parameter_ranges))}")
    print()

    results = await optimizer.optimize(base_strategy, parameter_ranges)

    # Display results
    print("\nOptimization Results:")
    print("=" * 60)

    if results:
        print(f"\nTop 5 Results:")
        print(f"{'Rank':<6} {'Win Rate':<12} {'Return':<10} {'Trades':<8} {'Parameters':<30}")
        print("-" * 70)

        for i, result in enumerate(results[:5], 1):
            params_str = str(result.params)[:28]
            print(f"{i:<6} {result.metrics['win_rate']:>10.2f}% "
                  f"{result.metrics['return_pct']:>9.2f}% "
                  f"{result.metrics['total_trades']:>8} "
                  f"{params_str:<30}")

        # Best strategy
        best = results[0]
        print(f"\n🏆 Best Strategy:")
        print(f"   Win Rate: {best.metrics['win_rate']:.2f}%")
        print(f"   Return: {best.metrics['return_pct']:.2f}%")
        print(f"   Parameters: {best.params}")

        # Save results
        optimizer.save_results("optimization_results.json")
        print("\n✓ Results saved to optimization_results.json")

    else:
        print("No valid results found")


async def run_multi_objective_optimization():
    """Run optimization with multiple objectives"""

    print("=" * 60)
    print("Multi-Objective Optimization")
    print("=" * 60)
    print()

    # Get base strategy
    base_strategy = MACrossoverStrategy.create()

    # Define parameter ranges (smaller for faster demo)
    parameter_ranges = {
        "fast_ema_period": [9, 11],
        "slow_ema_period": [19, 21],
        "bt_atrStopMult": [1.5, 2.0],
        "bt_atrTakeMult": [2.0, 2.5],
    }

    # Test different objectives
    objectives = [
        ObjectiveMetric.WIN_RATE,
        ObjectiveMetric.TOTAL_RETURN,
        ObjectiveMetric.PROFIT_FACTOR,
    ]

    all_results = {}

    for objective in objectives:
        print(f"\nOptimizing for: {objective.value}")
        print("-" * 60)

        config = ResearchConfig(
            symbol="XAUUSD",
            timeframe="1h",
            optimization_method=OptimizationMethod.GRID_SEARCH,
            objective=objective,
            max_iterations=16,
            parallel_jobs=1
        )

        optimizer = StrategyOptimizer(config)
        results = await optimizer.optimize(base_strategy, parameter_ranges)

        if results:
            best = results[0]
            print(f"Best {objective.value}: {best.objective_value:.4f}")
            print(f"Parameters: {best.params}")

            all_results[objective.value] = {
                'objective_value': best.objective_value,
                'params': best.params,
                'metrics': best.metrics
            }

    # Summary
    print("\n" + "=" * 60)
    print("Multi-Objective Summary")
    print("=" * 60)

    for obj_name, result in all_results.items():
        print(f"\n{obj_name}:")
        print(f"  Value: {result['objective_value']:.4f}")
        print(f"  Params: {result['params']}")
        print(f"  Win Rate: {result['metrics']['win_rate']:.2f}%")
        print(f"  Return: {result['metrics']['return_pct']:.2f}%")


async def run_comprehensive_research():
    """Run comprehensive research across multiple symbols"""

    print("=" * 60)
    print("Comprehensive Multi-Symbol Research")
    print("=" * 60)
    print()

    from engine.research import StrategyResearcher

    # Get base strategy
    base_strategy = MACrossoverStrategy.create()

    # Define research scope
    symbols = ["XAUUSD", "EURUSD"]
    timeframes = ["1h", "4h"]

    # Define parameter ranges (small for demo)
    parameter_ranges = {
        "fast_ema_period": [9, 11],
        "slow_ema_period": [19, 21],
    }

    # Create researcher
    researcher = StrategyResearcher(symbols, timeframes)

    # Run comprehensive research
    print("Running comprehensive research...")
    print(f"Symbols: {symbols}")
    print(f"Timeframes: {timeframes}")
    print()

    results = await researcher.comprehensive_research(
        base_strategy,
        parameter_ranges,
        objectives=[ObjectiveMetric.WIN_RATE]
    )

    # Generate report
    report = researcher.generate_research_report(results)
    print(report)

    # Save report
    with open("research_report.txt", "w") as f:
        f.write(report)

    print("✓ Research report saved to research_report.txt")


def show_optimization_methods():
    """Show available optimization methods"""

    print("=" * 60)
    print("Available Optimization Methods")
    print("=" * 60)
    print()

    methods = [
        ("Grid Search", "Tests all parameter combinations systematically"),
        ("Random Search", "Tests random parameter combinations"),
        ("Bayesian Optimization", "Uses probabilistic model to guide search"),
        ("Genetic Algorithm", "Uses evolutionary approach to find optimum"),
    ]

    for name, description in methods:
        print(f"{name}:")
        print(f"  {description}")
        print()


def show_objective_metrics():
    """Show available optimization objectives"""

    print("=" * 60)
    print("Available Objective Metrics")
    print("=" * 60)
    print()

    metrics = [
        ("Win Rate", "Percentage of profitable trades"),
        ("Profit Factor", "Ratio of gross profit to gross loss"),
        ("Sharpe Ratio", "Risk-adjusted return measure"),
        ("Total Return", "Overall percentage return"),
        ("Max Drawdown", "Maximum peak-to-trough decline (minimize)"),
    ]

    for name, description in metrics:
        print(f"{name}:")
        print(f"  {description}")
        print()


def main():
    """Main entry point"""

    print("Research and Optimization Examples")
    print("==================================")
    print()
    print("Choose an example:")
    print("1. Basic strategy optimization")
    print("2. Multi-objective optimization")
    print("3. Comprehensive multi-symbol research")
    print("4. Show optimization methods")
    print("5. Show objective metrics")
    print("6. Run all examples")

    choice = input("\nEnter choice (1-6): ").strip()

    if choice == "1":
        asyncio.run(run_basic_optimization())
    elif choice == "2":
        asyncio.run(run_multi_objective_optimization())
    elif choice == "3":
        asyncio.run(run_comprehensive_research())
    elif choice == "4":
        show_optimization_methods()
    elif choice == "5":
        show_objective_metrics()
    elif choice == "6":
        asyncio.run(run_basic_optimization())
        asyncio.run(run_multi_objective_optimization())
        asyncio.run(run_comprehensive_research())
        show_optimization_methods()
        show_objective_metrics()
    else:
        print("Invalid choice")

    print("\nDone!")


if __name__ == "__main__":
    main()
