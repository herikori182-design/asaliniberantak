"""
Moving Average Crossover Strategy
================================

A classic trend-following strategy that uses moving average crossovers
to identify entry and exit points.
"""

from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams


class MACrossoverStrategy:
    """Moving Average Crossover Strategy"""

    @staticmethod
    def create(fast_period: int = 9, slow_period: int = 21,
                allow_short: bool = True, atr_stop_mult: float = 1.5,
                atr_take_mult: float = 2.0) -> Strategy:
        """
        Create MA crossover strategy.

        Args:
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            allow_short: Allow short positions
            atr_stop_mult: ATR stop loss multiplier
            atr_take_mult: ATR take profit multiplier

        Returns:
            Configured strategy
        """
        return Strategy(
            id="ma_crossover_v1",
            name="MA Crossover Strategy",
            mode="INTRADAY",
            preferredTimeframe="1h",
            description="Classic moving average crossover strategy with trend filter",
            indicators=[
                IndicatorSpec(id="fast_ema", type="EMA", period=fast_period),
                IndicatorSpec(id="slow_ema", type="EMA", period=slow_period),
                IndicatorSpec(id="ema200", type="EMA", period=200),  # Trend filter
            ],
            ruleSet=RuleSet(
                entryLong=[
                    RuleCond(op="crossOver", left="fast_ema", right="slow_ema"),
                    RuleCond(op="gt", left="close", right="ema200"),  # Uptrend filter
                ],
                entryShort=[
                    RuleCond(op="crossUnder", left="fast_ema", right="slow_ema"),
                    RuleCond(op="lt", left="close", right="ema200"),  # Downtrend filter
                ],
            ),
            backtestParams=BacktestParams(
                allowShort=allow_short,
                atrStopMult=atr_stop_mult,
                atrTakeMult=atr_take_mult,
                trendFilter=True,
            )
        )

    @staticmethod
    def get_optimization_ranges() -> dict:
        """Get recommended parameter ranges for optimization"""
        return {
            "fast_ema_period": [5, 7, 9, 11, 13],
            "slow_ema_period": [17, 19, 21, 23, 25],
            "bt_atrStopMult": [1.0, 1.5, 2.0, 2.5],
            "bt_atrTakeMult": [1.5, 2.0, 2.5, 3.0],
        }


# Default instance
default = MACrossoverStrategy.create()
