#!/usr/bin/env python3
"""
Custom Exceptions for Trading System
"""
class RateLimitError(Exception):
    """Rate limit exceeded for API calls"""
    pass

class MT5Error(Exception):
    """MetaTrader 5 operation failed"""
    pass

class ValidationError(Exception):
    """Trading plan validation failed"""
    pass

class DataFetchError(Exception):
    """Failed to fetch market data"""
    pass

class NotebookLMError(Exception):
    """NotebookLM validation failed"""
    pass

class AuthError(Exception):
    """Authentication failed for API"""
    def __init__(self, provider: str, status_code: int, message: str):
        self.provider = provider
        self.status_code = status_code
        self.message = message
        super().__init__(f"{provider} auth failed (HTTP {status_code}): {message}")
