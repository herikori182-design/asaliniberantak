#!/usr/bin/env python3
import unittest
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.data import render_timeframe_from_m5
from engine.backtest import _build_entry_masks
from engine.schema import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams
from engine.research import ResearchConfig, StrategyOptimizer, ResearchLoop, OptimizationMethod, ObjectiveMetric


class TestResearchFoundation(unittest.TestCase):
    def test_render_timeframe_from_m5(self):
        idx = pd.date_range("2025-01-01 00:00:00", periods=6, freq="5min")
        df = pd.DataFrame(
            {
                "Open": [1, 2, 3, 4, 5, 6],
                "High": [2, 3, 4, 5, 6, 7],
                "Low": [0, 1, 2, 3, 4, 5],
                "Close": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
                "Volume": [10, 10, 10, 10, 10, 10],
            },
            index=idx,
        )
        out = render_timeframe_from_m5(df, "15m")
        self.assertEqual(len(out), 2)
        self.assertEqual(float(out.iloc[0]["Open"]), 1.0)
        self.assertEqual(float(out.iloc[0]["Close"]), 3.5)
        self.assertEqual(float(out.iloc[0]["Volume"]), 30.0)

    def test_confirm_no_lookahead(self):
        idx_a = pd.date_range("2025-01-01 00:05:00", periods=2, freq="5min")
        idx_c = pd.to_datetime(["2025-01-01 00:00:00", "2025-01-01 00:15:00"])
        df_a = pd.DataFrame({"Open": [1, 1], "High": [1, 1], "Low": [1, 1], "Close": [1, 1], "Volume": [1, 1]}, index=idx_a)
        df_c = pd.DataFrame({"Open": [1, 1], "High": [1, 1], "Low": [1, 1], "Close": [1, 1], "Volume": [1, 1]}, index=idx_c)
        ind_a = {"sig": [1.0, 1.0]}
        ind_c = {"sig": [1.0, 1.0]}
        rs = RuleSet(entryLong=[RuleCond(op="gt", left="sig", right=0)])
        crs = RuleSet(confirmLong=[RuleCond(op="gt", left="sig", right=0)])
        lm, _ = _build_entry_masks(df_a, df_c, ind_a, ind_c, rs, crs, confirm_tf_ms=15 * 60 * 1000, confirm_window_bars=5)
        # at 00:05 and 00:10, latest closed confirm bar should still be 00:00 only; still true.
        self.assertEqual(lm, [True, True])

    def test_optimizer_param_mapping(self):
        s = Strategy(
            id="x",
            name="x",
            mode="INTRADAY",
            preferredTimeframe="5m",
            indicators=[IndicatorSpec(id="fib", type="FIB", period=2, period2=2)],
            ruleSet=RuleSet(entryLong=[RuleCond(op="gt", left="close", right=0)]),
            backtestParams=BacktestParams(),
            optimizationParamMap={"fib_left": "indicators.0.period", "fib_right": "indicators.0.period2"},
        )
        cfg = ResearchConfig(
            symbol="XAUUSD",
            timeframe="5m",
            optimization_method=OptimizationMethod.RANDOM_SEARCH,
            objective=ObjectiveMetric.WIN_RATE,
            max_iterations=1,
        )
        opt = StrategyOptimizer(cfg)
        s2 = opt._modify_strategy(s, {"fib_left": 4, "fib_right": 7})
        self.assertEqual(s2.indicators[0].period, 4)
        self.assertEqual(s2.indicators[0].period2, 7)

    def test_research_loop_kpi_reasons(self):
        loop = ResearchLoop(max_iterations=1)
        res = loop.evaluate_kpi(
            {
                "win_rate": 40,
                "profit_factor": 1.1,
                "reward_risk_ratio": 0.9,
                "max_drawdown": 0.4,
                "total_trades": 5,
                "long_trades": 5,
                "short_trades": 0,
            }
        )
        self.assertFalse(res.passed)
        self.assertIn("win_rate_too_low", res.reasons)
        self.assertIn("too_few_trades", res.reasons)


if __name__ == "__main__":
    unittest.main(verbosity=2)
