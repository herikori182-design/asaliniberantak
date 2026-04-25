"""
Trend Following Strategy
========================

A classic trend-following strategy using multiple timeframe analysis
and ADX for trend strength confirmation.
"""

from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams


class TrendFollowingStrategy:
    """Trend Following Strategy"""

    @staticmethod
    def create(ema_fast: int = 9, ema_slow: int = 21, ema_trend: int = 200,
                adx_period: int = 14, adx_threshold: float = 25,
                allow_short: bool = True, atr_stop_mult: float = 2.0,
                atr_take_mult: float = 3.0) -> Strategy:
        """
        Create trend following strategy.

        Args:
            ema_fast: Fast EMA period for entry signals
            ema_slow: Slow EMA period for entry signals
            ema_trend: Long-term EMA for trend identification
            adx_period: ADX calculation period
            adx_threshold: Minimum ADX value for trend strength
            allow_short: Allow short positions
            atr_stop_mult: ATR stop loss multiplier
            atr_take_mult: ATR take profit multiplier

        Returns:
            Configured strategy
        """
        return Strategy(
            id="trend_following_v1",
            name="Trend Following Strategy",
            mode="INTRADAY",
            preferredTimeframe="4h",
            description="Classic trend following with ADX strength confirmation",
            indicators=[
                IndicatorSpec(id="ema_fast", type="EMA", period=ema_fast),
                IndicatorSpec(id="ema_slow", type="EMA", period=ema_slow),
                IndicatorSpec(id="ema_trend", type="EMA", period=ema_trend),
                IndicatorSpec(id="adx", type="ADX", period=adx_period),
                IndicatorSpec(id="atr", type="ATR", period=14),
            ],
            ruleSet=RuleSet(
                entryLong=[
                    RuleCond(op="crossOver", left="ema_fast", right="ema_slow"),
                    RuleCond(op="gt", left="close", right="ema_trend"),  # Uptrend
                    RuleCond(op="gt", left="adx.adx", right=adx_threshold),  # Strong trend
                ],
                entryShort=[
                    RuleCond(op="crossUnder", left="ema_fast", right="ema_slow"),
                    RuleCond(op="lt", left="close", right="ema_trend"),  # Downtrend
                    RuleCond(op="gt", left="adx.adx", right=adx_threshold),  # Strong trend
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
            "ema_fast": [7, 9, 11, 13],
            "ema_slow": [17, 21, 25, 29],
            "ema_trend": [150, 200, 250],
            "adx_period": [12, 14, 16],
            "adx_threshold": [20, 25, 30],
            "bt_atrStopMult": [1.5, 2.0, 2.5],
            "bt_atrTakeMult": [2.5, 3.0, 3.5],
        }


# Default instance
default = TrendFollowingStrategy.create()
