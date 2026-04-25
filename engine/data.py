import logging
import os
import time
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sys

# Add parent directory to path for backtesting import
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

logger = logging.getLogger(__name__)

# Timeframe configuration
TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
DEFAULT_DAYS = 365  # Default backtest period

# Cache directory
CACHE_DIR = Path(os.getenv("CACHE_DIR") or (REPO_ROOT / "data" / "cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _tf_to_ms(tf: str) -> int:
    """Convert timeframe string to milliseconds."""
    mapping = {
        "1m": 60 * 1000,
        "5m": 5 * 60 * 1000,
        "15m": 15 * 60 * 1000,
        "30m": 30 * 60 * 1000,
        "1h": 60 * 60 * 1000,
        "4h": 4 * 60 * 60 * 1000,
        "1d": 24 * 60 * 60 * 1000,
    }
    return mapping.get(tf, 15 * 60 * 1000)


def _get_cache_path(symbol: str, tf: str, days: int = DEFAULT_DAYS) -> Path:
    """Get cache file path for symbol/timeframe."""
    safe_symbol = symbol.replace("/", "_").replace("\\", "_")
    filename = f"{safe_symbol}_{tf}_{days}d.csv"
    return CACHE_DIR / filename


def load_cached(symbol: str, tf: str, days: int = DEFAULT_DAYS) -> pd.DataFrame:
    """
    Load cached OHLCV data for backtesting.

    Args:
        symbol: Trading pair symbol (e.g., "XAUUSD", "EURUSD")
        tf: Timeframe (e.g., "15m", "1h", "4h")
        days: Number of days of historical data

    Returns:
        DataFrame with OHLCV data, indexed by datetime
    """
    cache_path = _get_cache_path(symbol, tf, days)

    if cache_path.exists():
        try:
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            logger.debug(f"Loaded cached data for {symbol} {tf}: {len(df)} bars")
            return df
        except Exception as e:
            logger.warning(f"Failed to load cache for {symbol} {tf}: {e}")

    # Return empty DataFrame if no cache available
    logger.warning(f"No cached data available for {symbol} {tf}")
    return pd.DataFrame()


def save_cached(symbol: str, tf: str, df: pd.DataFrame, days: int = DEFAULT_DAYS) -> bool:
    """
    Save OHLCV data to cache.

    Args:
        symbol: Trading pair symbol
        tf: Timeframe
        df: DataFrame with OHLCV data
        days: Number of days (used for filename)

    Returns:
        True if successful, False otherwise
    """
    if df.empty:
        logger.warning(f"Cannot save empty DataFrame for {symbol} {tf}")
        return False

    try:
        cache_path = _get_cache_path(symbol, tf, days)
        df.to_csv(cache_path)
        logger.info(f"Cached {len(df)} bars for {symbol} {tf}")
        return True
    except Exception as e:
        logger.error(f"Failed to cache data for {symbol} {tf}: {e}")
        return False


def validate_ohlcv_data(df: pd.DataFrame) -> bool:
    """
    Validate OHLCV DataFrame structure and data quality.

    Args:
        df: DataFrame to validate

    Returns:
        True if valid, False otherwise
    """
    required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    if not all(col in df.columns for col in required_columns):
        logger.error(f"Missing required columns: {required_columns}")
        return False

    # Check for null values
    if df[required_columns].isnull().any().any():
        logger.warning("OHLCV data contains null values")

    # Check for negative values in price/volume
    price_cols = ['Open', 'High', 'Low', 'Close']
    if (df[price_cols] < 0).any().any():
        logger.error("OHLCV data contains negative prices")
        return False

    if (df['Volume'] < 0).any().any():
        logger.error("OHLCV data contains negative volume")
        return False

    # Check High >= Low
    if (df['High'] < df['Low']).any():
        logger.error("OHLCV data has High < Low")
        return False

    # Check Close within High/Low range
    if ((df['Close'] > df['High']) | (df['Close'] < df['Low'])).any():
        logger.error("OHLCV data has Close outside High/Low range")
        return False

    return True


def resample_ohlcv(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    """
    Resample OHLCV data to a different timeframe.

    Args:
        df: Source DataFrame with OHLCV data
        target_tf: Target timeframe (e.g., "1h", "4h", "1d")

    Returns:
        Resampled DataFrame
    """
    if df.empty:
        return df

    # Map timeframe to pandas offset alias
    tf_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }

    offset = tf_map.get(target_tf, "15min")

    try:
        resampled = df.resample(offset).agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()

        logger.debug(f"Resampled {len(df)} bars to {len(resampled)} {target_tf} bars")
        return resampled

    except Exception as e:
        logger.error(f"Failed to resample to {target_tf}: {e}")
        return df


def get_available_symbols() -> List[str]:
    """
    Get list of symbols with cached data.

    Returns:
        List of symbol names
    """
    symbols = set()

    try:
        for file_path in CACHE_DIR.glob("*.csv"):
            # Extract symbol from filename: SYMBOL_TF_DAYSd.csv
            parts = file_path.stem.split('_')
            if len(parts) >= 2:
                symbol = parts[0]
                symbols.add(symbol)

    except Exception as e:
        logger.error(f"Failed to scan cache directory: {e}")

    return sorted(list(symbols))


def clear_cache(symbol: Optional[str] = None, tf: Optional[str] = None) -> int:
    """
    Clear cached data files.

    Args:
        symbol: Optional symbol filter (clear all if None)
        tf: Optional timeframe filter

    Returns:
        Number of files deleted
    """
    deleted = 0

    try:
        for file_path in CACHE_DIR.glob("*.csv"):
            # Check filters
            if symbol and symbol.lower() not in file_path.stem.lower():
                continue
            if tf and tf.lower() not in file_path.stem.lower():
                continue

            file_path.unlink()
            deleted += 1
            logger.info(f"Deleted cache file: {file_path.name}")

    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")

    return deleted


def get_cache_info() -> Dict[str, any]:
    """
    Get information about cached data.

    Returns:
        Dictionary with cache statistics
    """
    info = {
        "cache_dir": str(CACHE_DIR),
        "total_files": 0,
        "total_size_mb": 0.0,
        "symbols": [],
        "timeframes": [],
    }

    try:
        for file_path in CACHE_DIR.glob("*.csv"):
            info["total_files"] += 1
            info["total_size_mb"] += file_path.stat().st_size / (1024 * 1024)

            # Extract symbol and timeframe
            parts = file_path.stem.split('_')
            if len(parts) >= 2:
                symbol = parts[0]
                tf = parts[1] if len(parts) > 1 else "unknown"

                if symbol not in info["symbols"]:
                    info["symbols"].append(symbol)
                if tf not in info["timeframes"]:
                    info["timeframes"].append(tf)

        info["symbols"] = sorted(info["symbols"])
        info["timeframes"] = sorted(info["timeframes"])
        info["total_size_mb"] = round(info["total_size_mb"], 2)

    except Exception as e:
        logger.error(f"Failed to get cache info: {e}")

    return info
