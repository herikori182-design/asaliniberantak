"""
MACD Strategy
=============

A momentum-based strategy using MACD crossovers with
additional filters for improved signal quality.
"""

from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams


class MACDStrategy:
    """MACD Strategy"""

    @staticmethod
    def create(fast_period: int = 12, slow_period: int = 26, signal_period: int = 9,
                ema_filter: int = 200, allow_short: bool = True,
                atr_stop_mult: float = 1.5, atr_take_mult: float = 2.0) -> Strategy:
        """
        Create MACD strategy.

        Args:
            fast_period: MACD fast EMA period
            slow_period: MACD slow EMA period
            signal_period: MACD signal line period
            ema_filter: EMA period for trend filter
            allow_short: Allow short positions
            atr_stop_mult: ATR stop loss multiplier
            atr_take_mult: ATR take profit multiplier

        Returns:
            Configured strategy
        """
        return Strategy(
            id="macd_v1",
            name="MACD Strategy",
            mode="INTRADAY",
            preferredTimeframe="1h",
            description="Momentum strategy using MACD crossovers with trend filter",
            indicators=[
                IndicatorSpec(id="macd", type="MACD", periodFast=fast_period,
                            periodSlow=slow_period, period=signal_period),
                IndicatorSpec(id="ema_filter", type="EMA", period=ema_filter),
                IndicatorSpec(id="atr", type="ATR", period=14),
            ],
            ruleSet=RuleSet(
                entryLong=[
                    RuleCond(op="crossOver", left="macd.macLine", right="macd.signal"),
                    RuleCond(op="gt", left="macd.histogram", right=0),  # Positive momentum
                    RuleCond(op="gt", left="close", right="ema_filter"),  # Uptrend
                ],
                entryShort=[
                    RuleCond(op="crossUnder", left="macd.macLine", right="macd.signal"),
                    RuleCond(op="lt", left="macd.histogram", right=0),  # Negative momentum
                    RuleCond(op="lt", left="close", right="ema_filter"),  # Downtrend
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
            "fast_period": [8, 12, 16],
            "slow_period": [20, 26, 32],
            "signal_period": [7, 9, 11],
            "ema_filter": [150, 200, 250],
            "bt_atrStopMult": [1.2, 1.5, 1.8],
            "bt_atrTakeMult": [1.8, 2.0, 2.5],
        }


# Default instance
default = MACDStrategy.create()
