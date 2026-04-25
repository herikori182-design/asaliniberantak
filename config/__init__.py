"""
Configuration Module for Trading Research System
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    """Central configuration class"""

    # Project paths
    PROJECT_ROOT = PROJECT_ROOT
    DATA_DIR = PROJECT_ROOT / "data"
    CACHE_DIR = Path(os.getenv("CACHE_DIR", DATA_DIR / "cache"))
    LOGS_DIR = PROJECT_ROOT / "logs"

    # Infoway API Configuration
    INFOWAY_API_KEY = os.getenv("INFOWAY_API_KEY", "")
    INFOWAY_COMMON_API_KEY = os.getenv("INFOWAY_COMMON_API_KEY", "")
    INFOWAY_STOCK_API_KEY = os.getenv("INFOWAY_STOCK_API_KEY", "")
    INFOWAY_TRUST_ENV_PROXY = os.getenv("INFOWAY_TRUST_ENV_PROXY", "false").lower() in ("true", "1", "yes")
    INFOWAY_WS_COMMON = os.getenv("INFOWAY_WS_COMMON", "true").lower() in ("true", "1", "yes")
    INFOWAY_WS_STOCK = os.getenv("INFOWAY_WS_STOCK", "false").lower() in ("true", "1", "yes")
    INFOWAY_MAX_RPS = float(os.getenv("INFOWAY_MAX_RPS", "1"))
    INFOWAY_TIMEOUT_S = float(os.getenv("INFOWAY_TIMEOUT_S", "30"))

    # Binance Configuration
    BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL", "https://data-api.binance.vision")
    BINANCE_SSL_VERIFY = os.getenv("BINANCE_SSL_VERIFY", "true").lower() in ("true", "1", "yes")
    BINANCE_LIVE_ENABLED = os.getenv("BINANCE_LIVE_ENABLED", "true").lower() in ("true", "1", "yes")

    # Backtesting Configuration
    DEFAULT_BACKTEST_DAYS = int(os.getenv("DEFAULT_BACKTEST_DAYS", "365"))
    BACKTEST_INITIAL_CAPITAL = float(os.getenv("BACKTEST_INITIAL_CAPITAL", "100000"))
    BACKTEST_COMMISSION = float(os.getenv("BACKTEST_COMMISSION", "0.0"))

    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "")

    # AI Provider Configuration
    AI_PROVIDER = os.getenv("AI_PROVIDER", "glm")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    @classmethod
    def get_infoway_key(cls, business: str = "common") -> str:
        """Get the appropriate Infoway API key for the business type"""
        if business == "stock":
            return cls.INFOWAY_STOCK_API_KEY or cls.INFOWAY_COMMON_API_KEY or cls.INFOWAY_API_KEY
        return cls.INFOWAY_COMMON_API_KEY or cls.INFOWAY_API_KEY

    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure all required directories exist"""
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        errors = []

        if not cls.INFOWAY_API_KEY and not cls.INFOWAY_COMMON_API_KEY:
            errors.append("INFOWAY_API_KEY or INFOWAY_COMMON_API_KEY must be set")

        if cls.INFOWAY_MAX_RPS <= 0:
            errors.append("INFOWAY_MAX_RPS must be greater than 0")

        if cls.DEFAULT_BACKTEST_DAYS <= 0:
            errors.append("DEFAULT_BACKTEST_DAYS must be greater than 0")

        if errors:
            print("Configuration validation failed:")
            for error in errors:
                print(f"  - {error}")
            return False

        return True


# Convenience functions
def get_config() -> Config:
    """Get the configuration instance"""
    return Config


def load_config() -> Config:
    """Load and validate configuration"""
    config = Config()
    config.ensure_directories()

    if not config.validate():
        raise ValueError("Invalid configuration. Please check your .env file.")

    return config
