"""
Trading Research Engine
========================

Core engine for trading strategy research, backtesting, and analysis.
"""

from .backtest import backtest_strategy
from .schema import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams
from .infoway import InfoWayManager, ConfigService
from .data import load_cached, TIMEFRAMES, DEFAULT_DAYS

__version__ = "1.0.0"

__all__ = [
    "backtest_strategy",
    "Strategy",
    "IndicatorSpec",
    "RuleCond",
    "RuleSet",
    "BacktestParams",
    "InfoWayManager",
    "ConfigService",
    "load_cached",
    "TIMEFRAMES",
    "DEFAULT_DAYS",
]
