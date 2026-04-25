"""
Default Strategy Pool
=====================

Collection of pre-configured, ready-to-use trading strategies.
All strategies have been tested and are ready for backtesting and optimization.
"""

from .ma_crossover import MACrossoverStrategy
from .rsi_divergence import RSIDivergenceStrategy
from .fibonacci_retracement import FibonacciRetracementStrategy
from .bollinger_bands import BollingerBandsStrategy
from .macd_strategy import MACDStrategy
from .multi_indicator import MultiIndicatorStrategy
from .scalping_rsi import ScalpingRSIStrategy
from .trend_following import TrendFollowingStrategy

__all__ = [
    "MACrossoverStrategy",
    "RSIDivergenceStrategy",
    "FibonacciRetracementStrategy",
    "BollingerBandsStrategy",
    "MACDStrategy",
    "MultiIndicatorStrategy",
    "ScalpingRSIStrategy",
    "TrendFollowingStrategy",
]


def get_all_strategies() -> dict:
    """Get all available strategies"""
    return {
        "ma_crossover": MACrossoverStrategy,
        "rsi_divergence": RSIDivergenceStrategy,
        "fibonacci_retracement": FibonacciRetracementStrategy,
        "bollinger_bands": BollingerBandsStrategy,
        "macd": MACDStrategy,
        "multi_indicator": MultiIndicatorStrategy,
        "scalping_rsi": ScalpingRSIStrategy,
        "trend_following": TrendFollowingStrategy,
    }


def get_strategy(name: str):
    """Get a specific strategy by name"""
    strategies = get_all_strategies()
    strategy_class = strategies.get(name.lower())

    if strategy_class is None:
        available = ", ".join(strategies.keys())
        raise ValueError(f"Unknown strategy: {name}. Available: {available}")

    return strategy_class()


def list_strategies() -> list:
    """List all available strategy names"""
    return list(get_all_strategies().keys())
