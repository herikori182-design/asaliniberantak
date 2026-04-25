"""
Multi-Indicator Confluence Strategy
===================================

A robust strategy that requires confluence from multiple indicators
before entering trades, reducing false signals.
"""

from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams


class MultiIndicatorStrategy:
    """Multi-Indicator Confluence Strategy"""

    @staticmethod
    def create(ema_fast: int = 9, ema_slow: int = 21, rsi_period: int = 14,
                rsi_level: float = 50, macd_fast: int = 12, macd_slow: int = 26,
                allow_short: bool = True, atr_stop_mult: float = 1.5,
                atr_take_mult: float = 2.0) -> Strategy:
        """
        Create multi-indicator confluence strategy.

        Args:
            ema_fast: Fast EMA period
            ema_slow: Slow EMA period
            rsi_period: RSI calculation period
            rsi_level: RSI level for filter
            macd_fast: MACD fast EMA period
            macd_slow: MACD slow EMA period
            allow_short: Allow short positions
            atr_stop_mult: ATR stop loss multiplier
            atr_take_mult: ATR take profit multiplier

        Returns:
            Configured strategy
        """
        return Strategy(
            id="multi_indicator_v1",
            name="Multi-Indicator Confluence Strategy",
            mode="INTRADAY",
            preferredTimeframe="1h",
            description="Robust strategy requiring confluence from EMA, RSI, and MACD",
            indicators=[
                IndicatorSpec(id="ema_fast", type="EMA", period=ema_fast),
                IndicatorSpec(id="ema_slow", type="EMA", period=ema_slow),
                IndicatorSpec(id="rsi", type="RSI", period=rsi_period),
                IndicatorSpec(id="macd", type="MACD", periodFast=macd_fast,
                            periodSlow=macd_slow, period=9),
            ],
            ruleSet=RuleSet(
                entryLong=[
                    RuleCond(op="crossOver", left="ema_fast", right="ema_slow"),
                    RuleCond(op="gt", left="rsi", right=rsi_level),
                    RuleCond(op="crossOver", left="macd.macLine", right="macd.signal"),
                ],
                entryShort=[
                    RuleCond(op="crossUnder", left="ema_fast", right="ema_slow"),
                    RuleCond(op="lt", left="rsi", right=rsi_level),
                    RuleCond(op="crossUnder", left="macd.macLine", right="macd.signal"),
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
            "ema_slow": [17, 19, 21, 23, 25],
            "rsi_period": [12, 14, 16],
            "rsi_level": [45, 50, 55],
            "macd_fast": [10, 12, 14],
            "macd_slow": [22, 26, 30],
            "bt_atrStopMult": [1.2, 1.5, 1.8],
            "bt_atrTakeMult": [1.8, 2.0, 2.5],
        }


# Default instance
default = MultiIndicatorStrategy.create()
