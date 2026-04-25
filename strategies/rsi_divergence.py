"""
RSI Divergence Strategy
========================

A mean-reversion strategy that uses RSI overbought/oversold conditions
with Bollinger Bands for confirmation.
"""

from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams


class RSIDivergenceStrategy:
    """RSI Divergence Strategy"""

    @staticmethod
    def create(rsi_period: int = 14, rsi_oversold: float = 30,
                rsi_overbought: float = 70, boll_period: int = 20,
                boll_std: float = 2.0, allow_short: bool = True,
                atr_stop_mult: float = 1.2, atr_take_mult: float = 1.8) -> Strategy:
        """
        Create RSI divergence strategy.

        Args:
            rsi_period: RSI calculation period
            rsi_oversold: Oversold threshold
            rsi_overbought: Overbought threshold
            boll_period: Bollinger Bands period
            boll_std: Bollinger Bands standard deviation
            allow_short: Allow short positions
            atr_stop_mult: ATR stop loss multiplier
            atr_take_mult: ATR take profit multiplier

        Returns:
            Configured strategy
        """
        return Strategy(
            id="rsi_divergence_v1",
            name="RSI Divergence Strategy",
            mode="SCALPING",
            preferredTimeframe="15m",
            description="Mean-reversion strategy using RSI extremes with Bollinger Bands confirmation",
            indicators=[
                IndicatorSpec(id="rsi", type="RSI", period=rsi_period),
                IndicatorSpec(id="boll", type="BOLL", period=boll_period, stdDev=boll_std),
                IndicatorSpec(id="ema50", type="EMA", period=50),  # Trend filter
            ],
            ruleSet=RuleSet(
                entryLong=[
                    RuleCond(op="lt", left="rsi", right=rsi_oversold),
                    RuleCond(op="touchLowerBand", left="close", right="boll.lower"),
                    RuleCond(op="gt", left="close", right="ema50"),  # Uptrend filter
                ],
                entryShort=[
                    RuleCond(op="gt", left="rsi", right=rsi_overbought),
                    RuleCond(op="touchUpperBand", left="close", right="boll.upper"),
                    RuleCond(op="lt", left="close", right="ema50"),  # Downtrend filter
                ],
            ),
            backtestParams=BacktestParams(
                allowShort=allow_short,
                atrStopMult=atr_stop_mult,
                atrTakeMult=atr_take_mult,
                minRsi=rsi_oversold,
                maxRsi=rsi_overbought,
            )
        )

    @staticmethod
    def get_optimization_ranges() -> dict:
        """Get recommended parameter ranges for optimization"""
        return {
            "rsi_period": [12, 14, 16],
            "rsi_oversold": [25, 30, 35],
            "rsi_overbought": [65, 70, 75],
            "boll_period": [15, 20, 25],
            "bt_atrStopMult": [1.0, 1.2, 1.5],
            "bt_atrTakeMult": [1.5, 1.8, 2.0],
        }


# Default instance
default = RSIDivergenceStrategy.create()
