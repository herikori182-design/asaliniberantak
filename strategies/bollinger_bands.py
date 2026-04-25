"""
Bollinger Bands Strategy
========================

A volatility-based strategy that uses Bollinger Bands for
mean-reversion entries with trend confirmation.
"""

from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams


class BollingerBandsStrategy:
    """Bollinger Bands Strategy"""

    @staticmethod
    def create(boll_period: int = 20, boll_std: float = 2.0,
                ema_period: int = 50, allow_short: bool = True,
                atr_stop_mult: float = 1.2, atr_take_mult: float = 2.0) -> Strategy:
        """
        Create Bollinger Bands strategy.

        Args:
            boll_period: Bollinger Bands period
            boll_std: Bollinger Bands standard deviation
            ema_period: EMA period for trend filter
            allow_short: Allow short positions
            atr_stop_mult: ATR stop loss multiplier
            atr_take_mult: ATR take profit multiplier

        Returns:
            Configured strategy
        """
        return Strategy(
            id="bollinger_bands_v1",
            name="Bollinger Bands Strategy",
            mode="INTRADAY",
            preferredTimeframe="30m",
            description="Volatility-based mean reversion with trend confirmation",
            indicators=[
                IndicatorSpec(id="boll", type="BOLL", period=boll_period, stdDev=boll_std),
                IndicatorSpec(id="ema_trend", type="EMA", period=ema_period),
                IndicatorSpec(id="rsi", type="RSI", period=14),
            ],
            ruleSet=RuleSet(
                entryLong=[
                    RuleCond(op="gt", left="close", right="ema_trend"),  # Uptrend
                    RuleCond(op="touchLowerBand", left="close", right="boll.lower"),
                    RuleCond(op="lt", left="rsi", right=70),  # Not overbought
                ],
                entryShort=[
                    RuleCond(op="lt", left="close", right="ema_trend"),  # Downtrend
                    RuleCond(op="touchUpperBand", left="close", right="boll.upper"),
                    RuleCond(op="gt", left="rsi", right=30),  # Not oversold
                ],
            ),
            backtestParams=BacktestParams(
                allowShort=allow_short,
                atrStopMult=atr_stop_mult,
                atrTakeMult=atr_take_mult,
            )
        )

    @staticmethod
    def get_optimization_ranges() -> dict:
        """Get recommended parameter ranges for optimization"""
        return {
            "boll_period": [15, 20, 25],
            "boll_std": [1.5, 2.0, 2.5],
            "ema_period": [40, 50, 60],
            "bt_atrStopMult": [1.0, 1.2, 1.5],
            "bt_atrTakeMult": [1.5, 2.0, 2.5],
        }


# Default instance
default = BollingerBandsStrategy.create()
