"""
Research and Optimization Logic
==============================

Advanced research capabilities for strategy optimization, parameter tuning,
and performance analysis.
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import time
from concurrent.futures import ProcessPoolExecutor
import itertools
import copy
import random

from .schema import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams
from .backtest import backtest_strategy

logger = logging.getLogger(__name__)


class OptimizationMethod(Enum):
    """Optimization methods"""
    GRID_SEARCH = "grid_search"
    RANDOM_SEARCH = "random_search"
    BAYESIAN = "bayesian"
    GENETIC = "genetic"


class ObjectiveMetric(Enum):
    """Optimization objectives"""
    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"
    SHARPE_RATIO = "sharpe_ratio"
    TOTAL_RETURN = "total_return"
    MAX_DRAWDOWN = "max_drawdown"  # minimize this


@dataclass
class OptimizationResult:
    """Result of optimization run"""
    strategy: Strategy
    metrics: Dict[str, float]
    params: Dict[str, Any]
    objective_value: float
    rank: int = 0


@dataclass
class ResearchConfig:
    """Configuration for research runs"""
    symbol: str
    timeframe: str
    optimization_method: OptimizationMethod = OptimizationMethod.GRID_SEARCH
    objective: ObjectiveMetric = ObjectiveMetric.WIN_RATE
    max_iterations: int = 100
    parallel_jobs: int = 1
    validation_split: float = 0.2  # 20% for validation


class StrategyOptimizer:
    """Strategy optimization engine"""

    def __init__(self, config: ResearchConfig):
        self.config = config
        self.results: List[OptimizationResult] = []
        self.best_strategy: Optional[Strategy] = None

    async def optimize(self,
                     base_strategy: Strategy,
                     parameter_ranges: Dict[str, List[Any]],
                     constraints: Optional[Dict[str, Callable]] = None) -> List[OptimizationResult]:
        """
        Optimize strategy parameters.

        Args:
            base_strategy: Base strategy to optimize
            parameter_ranges: Dictionary of parameter names to possible values
            constraints: Optional constraint functions

        Returns:
            List of optimization results sorted by objective
        """
        logger.info(f"Starting optimization for {base_strategy.name}")
        logger.info(f"Method: {self.config.optimization_method.value}")
        logger.info(f"Objective: {self.config.objective.value}")

        # Generate parameter combinations
        if self.config.optimization_method == OptimizationMethod.GRID_SEARCH:
            param_combinations = self._generate_grid_combinations(parameter_ranges)
        elif self.config.optimization_method == OptimizationMethod.RANDOM_SEARCH:
            param_combinations = self._generate_random_combinations(parameter_ranges, self.config.max_iterations)
        else:
            raise ValueError(f"Unsupported optimization method: {self.config.optimization_method}")

        logger.info(f"Testing {len(param_combinations)} parameter combinations")

        # Run backtests
        tasks = []
        for params in param_combinations:
            modified_strategy = self._modify_strategy(base_strategy, params)
            if constraints and not self._check_constraints(modified_strategy, constraints):
                continue
            tasks.append(self._evaluate_strategy(modified_strategy, params))

        # Execute tasks
        if self.config.parallel_jobs > 1:
            results = await self._run_parallel(tasks)
        else:
            results = await asyncio.gather(*tasks)

        # Filter and sort results
        valid_results = [r for r in results if r is not None]
        valid_results.sort(key=lambda x: x.objective_value, reverse=self._is_maximization())

        # Assign ranks
        for i, result in enumerate(valid_results, 1):
            result.rank = i

        self.results = valid_results
        self.best_strategy = valid_results[0].strategy if valid_results else None

        logger.info(f"Optimization complete. Best result: {valid_results[0].objective_value:.4f}")
        return valid_results

    def _generate_grid_combinations(self, parameter_ranges: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        """Generate all combinations for grid search"""
        keys = parameter_ranges.keys()
        values = parameter_ranges.values()
        combinations = list(itertools.product(*values))

        return [dict(zip(keys, combo)) for combo in combinations]

    def _generate_random_combinations(self, parameter_ranges: Dict[str, List[Any]],
                                     n_samples: int) -> List[Dict[str, Any]]:
        """Generate random combinations for random search"""
        np.random.seed(42)
        combinations = []

        for _ in range(n_samples):
            combo = {}
            for key, values in parameter_ranges.items():
                combo[key] = np.random.choice(values)
            combinations.append(combo)

        return combinations

    def _modify_strategy(self, strategy: Strategy, params: Dict[str, Any]) -> Strategy:
        """Create modified strategy with new parameters"""
        # Create a deep copy of the strategy
        if hasattr(strategy, "model_dump"):
            strategy_dict = strategy.model_dump()  # type: ignore[attr-defined]
        else:
            from dataclasses import asdict
            strategy_dict = asdict(strategy)

        def _set_nested(obj: Dict[str, Any], path: str, value: Any) -> bool:
            cur = obj
            keys = [k for k in str(path).split(".") if k]
            if not keys:
                return False
            for k in keys[:-1]:
                if isinstance(cur, list):
                    try:
                        idx = int(k)
                        cur = cur[idx]
                    except Exception:
                        return False
                else:
                    if k not in cur:
                        return False
                    cur = cur[k]
            last = keys[-1]
            if isinstance(cur, list):
                try:
                    cur[int(last)] = value
                    return True
                except Exception:
                    return False
            cur[last] = value
            return True

        # Explicit mapping (recommended)
        param_map = strategy_dict.get("optimizationParamMap") or {}
        for p_name, p_val in params.items():
            target_path = param_map.get(p_name)
            if target_path:
                _set_nested(strategy_dict, target_path, p_val)

        # Modify indicator parameters
        for indicator in strategy_dict['indicators']:
            ind_id = indicator['id']
            for param_name, param_value in params.items():
                if param_name.startswith(f"{ind_id}_"):
                    attr_name = param_name.replace(f"{ind_id}_", "")
                    indicator[attr_name] = param_value

        # Modify backtest parameters
        for param_name, param_value in params.items():
            if param_name.startswith("bt_"):
                attr_name = param_name.replace("bt_", "")
                strategy_dict['backtestParams'][attr_name] = param_value

        return Strategy.from_dict(strategy_dict)

    async def _evaluate_strategy(self, strategy: Strategy, params: Dict[str, Any]) -> Optional[OptimizationResult]:
        """Evaluate a single strategy"""
        try:
            result = await backtest_strategy(strategy, self.config.symbol, timeframe=self.config.timeframe)

            metrics = self._calculate_metrics(result)

            objective_value = self._calculate_objective(metrics)

            return OptimizationResult(
                strategy=strategy,
                metrics=metrics,
                params=params,
                objective_value=objective_value
            )

        except Exception as e:
            logger.error(f"Error evaluating strategy: {e}")
            return None

    async def _run_parallel(self, tasks: List) -> List[Optional[OptimizationResult]]:
        """Run tasks in parallel with rate limiting"""
        semaphore = asyncio.Semaphore(self.config.parallel_jobs)

        async def run_with_semaphore(task):
            async with semaphore:
                return await task

        return await asyncio.gather(*[run_with_semaphore(task) for task in tasks])

    def _calculate_metrics(self, backtest_result: Dict) -> Dict[str, float]:
        """Calculate performance metrics from backtest result"""
        stats = backtest_result['stats']
        trades = backtest_result.get('trades', [])

        metrics = {
            'win_rate': stats.get('winRate', 0.0),
            'total_trades': stats.get('totalTrades', 0),
            'net_profit': stats.get('netProfit', 0.0),
            'return_pct': stats.get('returnPct', 0.0),
            'long_wr': stats.get('longWinRate', 0.0),
            'short_wr': stats.get('shortWinRate', 0.0),
            'long_trades': stats.get('longTrades', 0),
            'short_trades': stats.get('shortTrades', 0),
        }

        # Calculate additional metrics
        if trades:
            profits = [t['PnL'] for t in trades if t.get('PnL', 0) > 0]
            losses = [abs(t['PnL']) for t in trades if t.get('PnL', 0) < 0]

            if profits and losses:
                avg_profit = np.mean(profits)
                avg_loss = np.mean(losses)
                metrics['profit_factor'] = sum(profits) / sum(losses)
                metrics['avg_profit'] = avg_profit
                metrics['avg_loss'] = avg_loss
                metrics['reward_risk_ratio'] = avg_profit / avg_loss if avg_loss > 0 else 0
            else:
                metrics['profit_factor'] = 0.0
                metrics['reward_risk_ratio'] = 0.0

            # Calculate maximum drawdown
            equity_curve = []
            running_equity = 100000.0  # Starting capital
            for trade in trades:
                running_equity += trade.get('PnL', 0)
                equity_curve.append(running_equity)

            if equity_curve:
                peak = equity_curve[0]
                max_dd = 0.0
                for value in equity_curve:
                    if value > peak:
                        peak = value
                    dd = (peak - value) / peak
                    if dd > max_dd:
                        max_dd = dd
                metrics['max_drawdown'] = max_dd
            else:
                metrics['max_drawdown'] = 0.0

        return metrics

    def _calculate_objective(self, metrics: Dict[str, float]) -> float:
        """Calculate objective value based on optimization objective"""
        if self.config.objective == ObjectiveMetric.WIN_RATE:
            return metrics['win_rate']

        elif self.config.objective == ObjectiveMetric.TOTAL_RETURN:
            return metrics['return_pct']

        elif self.config.objective == ObjectiveMetric.PROFIT_FACTOR:
            return metrics.get('profit_factor', 0.0)

        elif self.config.objective == ObjectiveMetric.SHARPE_RATIO:
            # Simplified Sharpe ratio calculation
            if metrics.get('max_drawdown', 0) > 0:
                return metrics['return_pct'] / metrics['max_drawdown']
            return 0.0

        elif self.config.objective == ObjectiveMetric.MAX_DRAWDOWN:
            # Minimize drawdown, so return negative value
            return -metrics.get('max_drawdown', 0.0)

        return 0.0

    def _is_maximization(self) -> bool:
        """Check if objective should be maximized"""
        return self.config.objective != ObjectiveMetric.MAX_DRAWDOWN

    def _check_constraints(self, strategy: Strategy, constraints: Dict[str, Callable]) -> bool:
        """Check if strategy meets constraints"""
        for constraint_name, constraint_func in constraints.items():
            if not constraint_func(strategy):
                logger.debug(f"Strategy failed constraint: {constraint_name}")
                return False
        return True

    def get_top_strategies(self, n: int = 10) -> List[OptimizationResult]:
        """Get top N strategies from optimization results"""
        return self.results[:n]

    def save_results(self, filepath: str):
        """Save optimization results to file"""
        results_data = []

        for result in self.results:
            result_dict = {
                'rank': result.rank,
                'objective_value': result.objective_value,
                'params': result.params,
                'metrics': result.metrics,
                'strategy': result.strategy.model_dump_json()
            }
            results_data.append(result_dict)

        with open(filepath, 'w') as f:
            json.dump(results_data, f, indent=2)

        logger.info(f"Results saved to {filepath}")

    def load_results(self, filepath: str):
        """Load optimization results from file"""
        with open(filepath, 'r') as f:
            results_data = json.load(f)

        self.results = []
        for result_dict in results_data:
            strategy = Strategy.model_validate_json(result_dict['strategy'])

            result = OptimizationResult(
                strategy=strategy,
                metrics=result_dict['metrics'],
                params=result_dict['params'],
                objective_value=result_dict['objective_value'],
                rank=result_dict['rank']
            )
            self.results.append(result)

        logger.info(f"Loaded {len(self.results)} results from {filepath}")


class StrategyResearcher:
    """High-level strategy research automation"""

    def __init__(self, symbols: List[str], timeframes: List[str]):
        self.symbols = symbols
        self.timeframes = timeframes
        self.research_history: List[Dict] = []

    async def comprehensive_research(self,
                                   base_strategy: Strategy,
                                   parameter_ranges: Dict[str, List[Any]],
                                   objectives: List[ObjectiveMetric] = None) -> Dict[str, Any]:
        """
        Run comprehensive research across symbols and timeframes.

        Args:
            base_strategy: Base strategy to research
            parameter_ranges: Parameter ranges for optimization
            objectives: List of objectives to optimize for

        Returns:
            Comprehensive research results
        """
        if objectives is None:
            objectives = [
                ObjectiveMetric.WIN_RATE,
                ObjectiveMetric.PROFIT_FACTOR,
                ObjectiveMetric.TOTAL_RETURN
            ]

        logger.info("Starting comprehensive research")
        logger.info(f"Symbols: {self.symbols}")
        logger.info(f"Timeframes: {self.timeframes}")
        logger.info(f"Objectives: {[o.value for o in objectives]}")

        all_results = {}

        for symbol in self.symbols:
            all_results[symbol] = {}

            for timeframe in self.timeframes:
                logger.info(f"Researching {symbol} {timeframe}...")

                config = ResearchConfig(
                    symbol=symbol,
                    timeframe=timeframe,
                    optimization_method=OptimizationMethod.GRID_SEARCH,
                    objective=objectives[0],
                    max_iterations=50,
                    parallel_jobs=1
                )

                optimizer = StrategyOptimizer(config)
                results = await optimizer.optimize(base_strategy, parameter_ranges)

                all_results[symbol][timeframe] = {
                    'best_result': results[0] if results else None,
                    'all_results': results,
                    'optimizer': optimizer
                }

                # Save to history
                self.research_history.append({
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'timestamp': time.time(),
                    'best_metrics': results[0].metrics if results else {},
                    'best_params': results[0].params if results else {}
                })

        return all_results

    def generate_research_report(self, results: Dict) -> str:
        """Generate comprehensive research report"""
        report = []
        report.append("=" * 80)
        report.append("COMPREHENSIVE STRATEGY RESEARCH REPORT")
        report.append("=" * 80)
        report.append("")

        for symbol, tf_results in results.items():
            report.append(f"Symbol: {symbol}")
            report.append("-" * 80)

            for timeframe, data in tf_results.items():
                best = data['best_result']
                if best:
                    report.append(f"\nTimeframe: {timeframe}")
                    report.append(f"  Objective Value: {best.objective_value:.4f}")
                    report.append(f"  Parameters: {best.params}")
                    report.append(f"  Metrics:")
                    for metric, value in best.metrics.items():
                        report.append(f"    {metric}: {value:.4f}")
                else:
                    report.append(f"\nTimeframe: {timeframe}")
                    report.append("  No valid results")

            report.append("")

        report.append("=" * 80)
        return "\n".join(report)


@dataclass
class ScalpKPIGate:
    min_win_rate: float = 60.0
    min_profit_factor: float = 1.8
    min_rr: float = 1.2
    max_drawdown: float = 0.2
    min_trades_1m: int = 30
    min_trades_6m: int = 100


@dataclass
class KPIGateResult:
    passed: bool
    reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)


class ResearchLoop:
    """
    improve -> retest -> reject/mutate -> retest until KPI pass or budget exhausted.
    """

    def __init__(self, kpi_gate: Optional[ScalpKPIGate] = None, max_iterations: int = 50):
        self.kpi_gate = kpi_gate or ScalpKPIGate()
        self.max_iterations = max_iterations
        self.history: List[Dict[str, Any]] = []

    def evaluate_kpi(self, metrics: Dict[str, float]) -> KPIGateResult:
        reasons: List[str] = []
        wr = float(metrics.get("win_rate", 0.0))
        pf = float(metrics.get("profit_factor", 0.0))
        rr = float(metrics.get("reward_risk_ratio", 0.0))
        dd = float(metrics.get("max_drawdown", 1.0))
        trades = int(metrics.get("total_trades", 0))

        if wr < self.kpi_gate.min_win_rate:
            reasons.append("win_rate_too_low")
        if pf < self.kpi_gate.min_profit_factor:
            reasons.append("profit_factor_too_low")
        if rr < self.kpi_gate.min_rr:
            reasons.append("reward_risk_ratio_too_low")
        if dd > self.kpi_gate.max_drawdown:
            reasons.append("drawdown_too_high")
        if trades < self.kpi_gate.min_trades_1m:
            reasons.append("too_few_trades")
        if abs(int(metrics.get("long_trades", 0)) - int(metrics.get("short_trades", 0))) > trades * 0.8 and trades > 0:
            reasons.append("direction_imbalance")

        return KPIGateResult(passed=len(reasons) == 0, reasons=reasons, metrics=metrics)

    def _mutate_candidate_params(
        self,
        base_params: Dict[str, Any],
        parameter_ranges: Dict[str, List[Any]],
        fail_reasons: List[str],
    ) -> Dict[str, Any]:
        out = dict(base_params or {})
        keys = list(parameter_ranges.keys())
        if not keys:
            return out

        target_keys = keys
        if "too_few_trades" in fail_reasons:
            target_keys = [k for k in keys if ("period" in k.lower() or "lookback" in k.lower())] or keys
        elif "drawdown_too_high" in fail_reasons:
            target_keys = [k for k in keys if ("atrstop" in k.lower() or "take" in k.lower())] or keys

        n_mut = min(3, max(1, len(target_keys) // 3))
        for k in random.sample(target_keys, k=min(n_mut, len(target_keys))):
            vals = parameter_ranges.get(k) or []
            if not vals:
                continue
            out[k] = random.choice(vals)
        return out

    async def run(
        self,
        base_strategy: Strategy,
        symbol: str,
        timeframe: str,
        parameter_ranges: Dict[str, List[Any]],
    ) -> Dict[str, Any]:
        cfg = ResearchConfig(
            symbol=symbol,
            timeframe=timeframe,
            optimization_method=OptimizationMethod.RANDOM_SEARCH,
            objective=ObjectiveMetric.PROFIT_FACTOR,
            max_iterations=1,
            parallel_jobs=1,
        )
        optimizer = StrategyOptimizer(cfg)
        params = {k: random.choice(v) for k, v in parameter_ranges.items() if v}

        best: Optional[OptimizationResult] = None
        for i in range(1, self.max_iterations + 1):
            candidate = optimizer._modify_strategy(base_strategy, params)
            result = await optimizer._evaluate_strategy(candidate, params)
            if result is None:
                gate = KPIGateResult(False, reasons=["evaluation_error"], metrics={})
            else:
                gate = self.evaluate_kpi(result.metrics)
                if best is None or result.objective_value > best.objective_value:
                    best = result

            self.history.append(
                {
                    "iteration": i,
                    "params": copy.deepcopy(params),
                    "passed": gate.passed,
                    "reasons": gate.reasons,
                    "metrics": gate.metrics,
                }
            )
            if gate.passed:
                return {"status": "passed", "iteration": i, "best": best, "history": self.history}
            params = self._mutate_candidate_params(params, parameter_ranges, gate.reasons)

        return {"status": "budget_exhausted", "iteration": self.max_iterations, "best": best, "history": self.history}


async def run_optimization_example():
    """Example of running strategy optimization"""

    # Create base strategy
    base_strategy = Strategy(
        id="ema_crossover_opt",
        name="EMA Crossover Optimization",
        mode="INTRADAY",
        preferredTimeframe="1h",
        indicators=[
            IndicatorSpec(id="fast_ema", type="EMA", period=9),
            IndicatorSpec(id="slow_ema", type="EMA", period=21),
            IndicatorSpec(id="rsi", type="RSI", period=14),
        ],
        ruleSet=RuleSet(
            entryLong=[
                RuleCond(op="crossOver", left="fast_ema", right="slow_ema"),
                RuleCond(op="gt", left="rsi", right=50),
            ],
            entryShort=[
                RuleCond(op="crossUnder", left="fast_ema", right="slow_ema"),
                RuleCond(op="lt", left="rsi", right=50),
            ],
        ),
        backtestParams=BacktestParams(
            allowShort=True,
            atrStopMult=1.5,
            atrTakeMult=2.0,
        )
    )

    # Define parameter ranges
    parameter_ranges = {
        "fast_ema_period": [5, 7, 9, 11, 13],
        "slow_ema_period": [17, 19, 21, 23, 25],
        "rsi_period": [12, 14, 16],
        "bt_atrStopMult": [1.0, 1.5, 2.0],
        "bt_atrTakeMult": [1.5, 2.0, 2.5],
    }

    # Define constraints
    def constraint_fast_slower_than_slow(strategy: Strategy) -> bool:
        fast_period = next((ind.period for ind in strategy.indicators if ind.id == "fast_ema"), 0)
        slow_period = next((ind.period for ind in strategy.indicators if ind.id == "slow_ema"), 0)
        return fast_period < slow_period

    constraints = {
        "fast_slower_than_slow": constraint_fast_slower_than_slow
    }

    # Run optimization
    config = ResearchConfig(
        symbol="XAUUSD",
        timeframe="1h",
        optimization_method=OptimizationMethod.GRID_SEARCH,
        objective=ObjectiveMetric.WIN_RATE,
        max_iterations=50,
        parallel_jobs=1
    )

    optimizer = StrategyOptimizer(config)
    results = await optimizer.optimize(base_strategy, parameter_ranges, constraints)

    # Print results
    print("\nOptimization Results:")
    print("=" * 60)
    for i, result in enumerate(results[:5], 1):
        print(f"\n#{i} Rank: {result.rank}")
        print(f"  Objective: {result.objective_value:.4f}")
        print(f"  Parameters: {result.params}")
        print(f"  Win Rate: {result.metrics['win_rate']:.2f}%")
        print(f"  Return: {result.metrics['return_pct']:.2f}%")

    return results


if __name__ == "__main__":
    asyncio.run(run_optimization_example())
