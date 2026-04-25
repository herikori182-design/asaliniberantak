"""
Scalping RSI Strategy
======================

A high-frequency scalping strategy using RSI with tight stops
and quick profit targets for short-term trades.
"""

from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams


class ScalpingRSIStrategy:
    """Scalping RSI Strategy"""

    @staticmethod
    def create(rsi_period: int = 7, rsi_oversold: float = 25,
                rsi_overbought: float = 75, ema_fast: int = 5,
                ema_slow: int = 13, allow_short: bool = True,
                atr_stop_mult: float = 0.8, atr_take_mult: float = 1.2) -> Strategy:
        """
        Create scalping RSI strategy.

        Args:
            rsi_period: RSI calculation period (shorter for scalping)
            rsi_oversold: Oversold threshold
            rsi_overbought: Overbought threshold
            ema_fast: Fast EMA period
            ema_slow: Slow EMA period
            allow_short: Allow short positions
            atr_stop_mult: ATR stop loss multiplier (tighter for scalping)
            atr_take_mult: ATR take profit multiplier (quicker for scalping)

        Returns:
            Configured strategy
        """
        return Strategy(
            id="scalping_rsi_v1",
            name="Scalping RSI Strategy",
            mode="SCALPING",
            preferredTimeframe="5m",
            description="High-frequency scalping using RSI extremes with quick exits",
            indicators=[
                IndicatorSpec(id="rsi", type="RSI", period=rsi_period),
                IndicatorSpec(id="ema_fast", type="EMA", period=ema_fast),
                IndicatorSpec(id="ema_slow", type="EMA", period=ema_slow),
                IndicatorSpec(id="atr", type="ATR", period=7),
            ],
            ruleSet=RuleSet(
                entryLong=[
                    RuleCond(op="lt", left="rsi", right=rsi_oversold),
                    RuleCond(op="crossOver", left="ema_fast", right="ema_slow"),
                ],
                entryShort=[
                    RuleCond(op="gt", left="rsi", right=rsi_overbought),
                    RuleCond(op="crossUnder", left="ema_fast", right="ema_slow"),
                ],
            ),
            backtestParams=BacktestParams(
                allowShort=allow_short,
                atrStopMult=atr_stop_mult,  # Tighter stops
                atrTakeMult=atr_take_mult,  # Quicker profits
                minRsi=rsi_oversold,
                maxRsi=rsi_overbought,
            )
        )

    @staticmethod
    def get_optimization_ranges() -> dict:
        """Get recommended parameter ranges for optimization"""
        return {
            "rsi_period": [5, 7, 9],
            "rsi_oversold": [20, 25, 30],
            "rsi_overbought": [70, 75, 80],
            "ema_fast": [3, 5, 7],
            "ema_slow": [11, 13, 15],
            "bt_atrStopMult": [0.5, 0.8, 1.0],
            "bt_atrTakeMult": [1.0, 1.2, 1.5],
        }


# Default instance
default = ScalpingRSIStrategy.create()
