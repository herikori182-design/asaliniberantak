"""
Complete Technical Indicators Library
====================================

Comprehensive library of technical indicators for trading strategy research.
Supports 12+ indicators with proper mathematical implementations.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional, Union
import logging

logger = logging.getLogger(__name__)


def sma(series: pd.Series, period: int = 14) -> np.ndarray:
    """Simple Moving Average"""
    return series.rolling(period).mean().to_numpy()


def ema(series: pd.Series, period: int = 14) -> np.ndarray:
    """Exponential Moving Average"""
    return series.ewm(span=period, adjust=False).mean().to_numpy()


def rsi(series: pd.Series, period: int = 14) -> np.ndarray:
    """Relative Strength Index"""
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    roll_up = up.ewm(span=period, adjust=False).mean()
    roll_down = down.ewm(span=period, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50).to_numpy()


def atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    """Average True Range"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [(high - low).abs(),
         (high - prev_close).abs(),
         (low - prev_close).abs()],
        axis=1
    ).max(axis=1)

    return tr.ewm(span=period, adjust=False).mean().to_numpy()


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, np.ndarray]:
    """Moving Average Convergence Divergence"""
    fast_ema = series.ewm(span=fast, adjust=False).mean()
    slow_ema = series.ewm(span=slow, adjust=False).mean()
    mac = fast_ema - slow_ema
    sig = mac.ewm(span=signal, adjust=False).mean()
    hist = mac - sig

    return {
        "macLine": mac.to_numpy(),
        "signal": sig.to_numpy(),
        "histogram": hist.to_numpy()
    }


def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> Dict[str, np.ndarray]:
    """Bollinger Bands"""
    middle = series.rolling(period).mean()
    std = series.rolling(period).std().fillna(0)

    upper = middle + std_dev * std
    lower = middle - std_dev * std
    bandwidth = (upper - lower) / middle

    return {
        "middle": middle.to_numpy(),
        "upper": upper.to_numpy(),
        "lower": lower.to_numpy(),
        "bandwidth": bandwidth.to_numpy()
    }


def stochastic_oscillator(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Dict[str, np.ndarray]:
    """Stochastic Oscillator"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # Calculate %K
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()

    k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    k_percent = k_percent.fillna(50)

    # Calculate %D (smoothed %K)
    d_percent = k_percent.rolling(d_period).mean()

    return {
        "k": k_percent.to_numpy(),
        "d": d_percent.to_numpy()
    }


def cci(df: pd.DataFrame, period: int = 20) -> np.ndarray:
    """Commodity Channel Index"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # Typical Price
    tp = (high + low + close) / 3

    # Simple Moving Average of Typical Price
    sma_tp = tp.rolling(period).mean()

    # Mean Deviation
    md = tp.rolling(period).apply(lambda x: np.fabs(x - x.mean()).mean(), raw=True)

    # CCI
    cci = (tp - sma_tp) / (0.015 * md)
    return cci.fillna(0).to_numpy()


def parabolic_sar(df: pd.DataFrame, af_start: float = 0.02, af_max: float = 0.2, af_step: float = 0.02) -> np.ndarray:
    """Parabolic Stop and Reverse (SAR)"""
    high = df["High"].values
    low = df["Low"].values

    n = len(df)
    sar = np.zeros(n)
    is_up_trend = True
    af = af_start
    ep = high[0]
    sar[0] = low[0]

    for i in range(1, n):
        if is_up_trend:
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = min(sar[i], low[i-1], low[i-2] if i >= 2 else low[i-1])

            if low[i] < sar[i]:
                # Switch to downtrend
                is_up_trend = False
                sar[i] = ep
                ep = low[i]
                af = af_start
            else:
                # Continue uptrend
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + af_step, af_max)
        else:
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = max(sar[i], high[i-1], high[i-2] if i >= 2 else high[i-1])

            if high[i] > sar[i]:
                # Switch to uptrend
                is_up_trend = True
                sar[i] = ep
                ep = high[i]
                af = af_start
            else:
                # Continue downtrend
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + af_step, af_max)

    return sar


def adx(df: pd.DataFrame, period: int = 14) -> Dict[str, np.ndarray]:
    """Average Directional Index"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # Calculate True Range
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(),
         (high - prev_close).abs(),
         (low - prev_close).abs()],
        axis=1
    ).max(axis=1)

    # Calculate +DM and -DM
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Smooth TR, +DM, -DM
    atr_smooth = tr.ewm(span=period, adjust=False).mean()
    plus_dm_smooth = pd.Series(plus_dm).ewm(span=period, adjust=False).mean()
    minus_dm_smooth = pd.Series(minus_dm).ewm(span=period, adjust=False).mean()

    # Calculate +DI and -DI
    plus_di = 100 * (plus_dm_smooth / atr_smooth).fillna(0)
    minus_di = 100 * (minus_dm_smooth / atr_smooth).fillna(0)

    # Calculate DX and ADX
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(span=period, adjust=False).mean().fillna(0)

    return {
        "adx": adx.to_numpy(),
        "plus_di": plus_di.to_numpy(),
        "minus_di": minus_di.to_numpy()
    }


def envelopes(series: pd.Series, period: int = 20, deviation: float = 0.1) -> Dict[str, np.ndarray]:
    """Envelopes (Moving Average Envelope)"""
    ma = series.rolling(period).mean()
    upper = ma * (1 + deviation)
    lower = ma * (1 - deviation)

    return {
        "middle": ma.to_numpy(),
        "upper": upper.to_numpy(),
        "lower": lower.to_numpy()
    }


def fibonacci_retracement(df: pd.DataFrame, left: int = 2, right: int = 2,
                         ratios: Tuple[float, ...] = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)) -> Dict[str, np.ndarray]:
    """
    Fibonacci Retracement Levels based on pivot points
    """
    n = len(df)
    high = df["High"]
    low = df["Low"]

    # Find pivot highs and lows
    def find_pivots(series, left, right, kind):
        window = left + right + 1
        if kind == "high":
            roll = series.rolling(window, center=True).max()
            return (series == roll).fillna(False)
        else:
            roll = series.rolling(window, center=True).min()
            return (series == roll).fillna(False)

    ph = find_pivots(high, left, right, "high")
    pl = find_pivots(low, left, right, "low")

    # Initialize arrays
    start_arr = np.full(n, np.nan)
    end_arr = np.full(n, np.nan)
    dir_arr = np.zeros(n, dtype=float)

    # Create level arrays
    level_arrs = {}
    for r in ratios:
        r_key = str(float(r)).rstrip("0").rstrip(".")
        level_arrs[r_key] = np.full(n, np.nan)

    # Track swing
    prev_type = None
    prev_price = np.nan
    swing_start = np.nan
    swing_end = np.nan

    for t in range(n):
        idx = t - right
        if idx >= 0:
            # Process pivots
            if pl[idx]:
                p = float(low.iloc[idx])
                if prev_type is None:
                    prev_type, prev_price = "low", p
                elif prev_type == "low":
                    prev_price = min(prev_price, p) if np.isfinite(prev_price) else p
                else:
                    swing_start, swing_end = prev_price, p
                    prev_type, prev_price = "low", p

            if ph[idx]:
                p = float(high.iloc[idx])
                if prev_type is None:
                    prev_type, prev_price = "high", p
                elif prev_type == "high":
                    prev_price = max(prev_price, p) if np.isfinite(prev_price) else p
                else:
                    swing_start, swing_end = prev_price, p
                    prev_type, prev_price = "high", p

        # Calculate Fibonacci levels if we have a swing
        if np.isfinite(swing_start) and np.isfinite(swing_end):
            start_arr[t] = swing_start
            end_arr[t] = swing_end

            if swing_end > swing_start:
                dir_arr[t] = 1.0
            elif swing_end < swing_start:
                dir_arr[t] = -1.0
            else:
                dir_arr[t] = 0.0

            # Calculate levels
            for r in ratios:
                r_key = str(float(r)).rstrip("0").rstrip(".")
                level = swing_end - (swing_end - swing_start) * r
                level_arrs[r_key][t] = level

    # Build output
    out = {
        "start": start_arr,
        "end": end_arr,
        "dir": dir_arr,
    }
    out.update(level_arrs)

    # Convenience alias
    if "0.5" in level_arrs:
        out["mid"] = level_arrs["0.5"]

    return out


def support_resistance(high: pd.Series, low: pd.Series, lookback: int = 20) -> Tuple[np.ndarray, np.ndarray]:
    """Calculate Support and Resistance levels"""
    support = low.rolling(lookback).min().to_numpy()
    resistance = high.rolling(lookback).max().to_numpy()
    return support, resistance


def volume_profile(df: pd.DataFrame, period: int = 20) -> Dict[str, np.ndarray]:
    """Volume Profile analysis"""
    volume = df["Volume"]
    close = df["Close"]

    # Volume Moving Average
    vol_ma = volume.rolling(period).mean()

    # Volume Rate of Change
    vol_roc = volume.pct_change(period) * 100

    # Volume Weighted Average Price (VWAP)
    typical_price = (df["High"] + df["Low"] + close) / 3
    vwap = (typical_price * volume).rolling(period).sum() / volume.rolling(period).sum()

    return {
        "volume_ma": vol_ma.to_numpy(),
        "volume_roc": vol_roc.fillna(0).to_numpy(),
        "vwap": vwap.to_numpy()
    }


def momentum(series: pd.Series, period: int = 10) -> np.ndarray:
    """Momentum Indicator"""
    return (series - series.shift(period)).fillna(0).to_numpy()


def roc(series: pd.Series, period: int = 12) -> np.ndarray:
    """Rate of Change"""
    return ((series - series.shift(period)) / series.shift(period) * 100).fillna(0).to_numpy()


def williams_r(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    """Williams %R"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    highest_high = high.rolling(period).max()
    lowest_low = low.rolling(period).min()

    williams_r = -100 * (highest_high - close) / (highest_high - lowest_low)
    return williams_r.fillna(-50).to_numpy()


# Indicator Registry
INDICATOR_REGISTRY = {
    "SMA": sma,
    "EMA": ema,
    "RSI": rsi,
    "ATR": atr,
    "MACD": macd,
    "BOLL": bollinger_bands,
    "STOCH": stochastic_oscillator,
    "CCI": cci,
    "PSAR": parabolic_sar,
    "ADX": adx,
    "ENV": envelopes,
    "FIB": fibonacci_retracement,
    "MOM": momentum,
    "ROC": roc,
    "WILLIAMS_R": williams_r,
}


def compute_indicator(indicator_type: str, data: Union[pd.Series, pd.DataFrame], **params) -> Union[np.ndarray, Dict[str, np.ndarray]]:
    """
    Compute an indicator by type.

    Args:
        indicator_type: Type of indicator (e.g., "SMA", "RSI", "MACD")
        data: Price data (Series for single indicators, DataFrame for multi-price indicators)
        **params: Indicator parameters (period, std_dev, etc.)

    Returns:
        Computed indicator values (array or dict of arrays)
    """
    indicator_func = INDICATOR_REGISTRY.get(indicator_type.upper())

    if indicator_func is None:
        raise ValueError(f"Unknown indicator type: {indicator_type}")

    try:
        return indicator_func(data, **params)
    except Exception as e:
        logger.error(f"Error computing {indicator_type}: {e}")
        raise


def get_available_indicators() -> list:
    """Get list of available indicator types"""
    return sorted(INDICATOR_REGISTRY.keys())


def validate_indicator_params(indicator_type: str, params: dict) -> bool:
    """
    Validate indicator parameters.

    Args:
        indicator_type: Type of indicator
        params: Parameters to validate

    Returns:
        True if valid, False otherwise
    """
    indicator_type = indicator_type.upper()

    # Common parameter validations
    if "period" in params:
        if not isinstance(params["period"], int) or params["period"] < 1:
            return False

    # Indicator-specific validations
    if indicator_type == "BOLL":
        if "std_dev" in params:
            if not isinstance(params["std_dev"], (int, float)) or params["std_dev"] <= 0:
                return False

    elif indicator_type == "MACD":
        if "fast" in params and params["fast"] >= params.get("slow", 26):
            return False

    return True
