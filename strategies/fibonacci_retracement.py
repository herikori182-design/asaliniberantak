"""
Fibonacci Retracement Strategy
===============================

A swing trading strategy that uses Fibonacci retracement levels
to identify pullback entries in the direction of the main trend.
"""

from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams


class FibonacciRetracementStrategy:
    """Fibonacci Retracement Strategy"""

    @staticmethod
    def create(fib_left: int = 2, fib_right: int = 2,
                fib_level: float = 0.618, ema_period: int = 200,
                allow_short: bool = True, atr_stop_mult: float = 1.5,
                atr_take_mult: float = 2.5) -> Strategy:
        """
        Create Fibonacci retracement strategy.

        Args:
            fib_left: Left pivot window for Fibonacci calculation
            fib_right: Right pivot window for Fibonacci calculation
            fib_level: Fibonacci retracement level to trade
            ema_period: EMA period for trend filter
            allow_short: Allow short positions
            atr_stop_mult: ATR stop loss multiplier
            atr_take_mult: ATR take profit multiplier

        Returns:
            Configured strategy
        """
        return Strategy(
            id="fib_retracement_v1",
            name="Fibonacci Retracement Strategy",
            mode="INTRADAY",
            preferredTimeframe="1h",
            description="Swing trading strategy using Fibonacci pullbacks in trend direction",
            indicators=[
                IndicatorSpec(id="fib", type="FIB", period=fib_left, period2=fib_right),
                IndicatorSpec(id="ema_trend", type="EMA", period=ema_period),
                IndicatorSpec(id="atr", type="ATR", period=14),
            ],
            ruleSet=RuleSet(
                entryLong=[
                    RuleCond(op="gt", left="close", right="ema_trend"),  # Uptrend
                    RuleCond(op="fibAtOrAbove", left="close", right="fib", level=str(fib_level)),
                ],
                entryShort=[
                    RuleCond(op="lt", left="close", right="ema_trend"),  # Downtrend
                    RuleCond(op="fibAtOrBelow", left="close", right="fib", level=str(fib_level)),
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
            "fib_left": [2, 3, 4],
            "fib_right": [2, 3, 4],
            "fib_level": [0.382, 0.5, 0.618],
            "ema_period": [150, 200, 250],
            "bt_atrStopMult": [1.2, 1.5, 1.8],
            "bt_atrTakeMult": [2.0, 2.5, 3.0],
        }


# Default instance
default = FibonacciRetracementStrategy.create()
