"""
conftest.py — Shared pytest fixtures for the MT5 trading bot tests.
Provides mock MT5 data, sample DataFrames, and indicator dicts.
"""
import sys
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# Mock the MetaTrader5 module before any bot code imports it
mock_mt5 = MagicMock()
mock_mt5.TIMEFRAME_M1 = 1
mock_mt5.TIMEFRAME_M5 = 5
mock_mt5.TIMEFRAME_M15 = 15
mock_mt5.TIMEFRAME_M30 = 30
mock_mt5.TIMEFRAME_H1 = 16385
mock_mt5.TIMEFRAME_H4 = 16388
mock_mt5.TIMEFRAME_D1 = 16408
mock_mt5.TIMEFRAME_W1 = 32769
mock_mt5.ORDER_TYPE_BUY = 0
mock_mt5.ORDER_TYPE_SELL = 1
mock_mt5.TRADE_ACTION_DEAL = 1
mock_mt5.TRADE_ACTION_SLTP = 6
mock_mt5.TRADE_RETCODE_DONE = 10009
mock_mt5.ORDER_FILLING_IOC = 1
mock_mt5.ORDER_TIME_GTC = 0
sys.modules["MetaTrader5"] = mock_mt5


@pytest.fixture
def sample_candle_df():
    """Generate a realistic 250-bar USDJPY H1 DataFrame."""
    np.random.seed(42)
    n = 250
    base_price = 150.0

    # Generate a random walk for close prices
    returns = np.random.normal(0.0001, 0.003, n)
    close = base_price * np.cumprod(1 + returns)

    # Generate OHLC from close
    high = close * (1 + np.abs(np.random.normal(0, 0.002, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.002, n)))
    open_ = close + np.random.normal(0, 0.1, n)

    # Ensure high >= max(open, close) and low <= min(open, close)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="h"),
        "open": np.round(open_, 3),
        "high": np.round(high, 3),
        "low": np.round(low, 3),
        "close": np.round(close, 3),
        "tick_volume": np.random.randint(500, 5000, n),
    })
    return df


@pytest.fixture
def bullish_indicator_dict():
    """An indicator dict designed to score high on bullish checks."""
    return {
        "symbol": "USDJPY",
        "timeframe": "H1",
        "last_close": 150.500,
        "rsi": {"value": 55.0, "condition": "neutral", "divergence": "none"},
        "macd": {"macd": 0.05, "signal": 0.02, "histogram": 0.03, "cross": "bullish"},
        "bollinger": {"upper": 151.0, "mid": 150.0, "lower": 149.0, "price_position": "inside"},
        "ichimoku": {
            "tenkan": 150.4, "kijun": 150.2,
            "senkou_a": 149.8, "senkou_b": 149.5,
            "cloud_position": "above_cloud", "tk_cross": "bullish",
        },
        "ema": {"ema_50": 150.3, "ema_100": 150.1, "ema_200": 149.8, "trend": "strong_bullish"},
        "atr": 0.350,
        "atr_pips": 350.0,
        "atr_percentile": 50.0,
        "support_resistance": {"recent_high": 151.0, "recent_low": 149.0},
    }


@pytest.fixture
def bearish_indicator_dict():
    """An indicator dict designed to score high on bearish checks."""
    return {
        "symbol": "USDJPY",
        "timeframe": "H1",
        "last_close": 149.000,
        "rsi": {"value": 40.0, "condition": "neutral", "divergence": "none"},
        "macd": {"macd": -0.05, "signal": -0.02, "histogram": -0.03, "cross": "bearish"},
        "bollinger": {"upper": 151.0, "mid": 150.0, "lower": 149.0, "price_position": "inside"},
        "ichimoku": {
            "tenkan": 149.2, "kijun": 149.5,
            "senkou_a": 150.2, "senkou_b": 150.5,
            "cloud_position": "below_cloud", "tk_cross": "bearish",
        },
        "ema": {"ema_50": 149.3, "ema_100": 149.6, "ema_200": 150.0, "trend": "strong_bearish"},
        "atr": 0.350,
        "atr_pips": 350.0,
        "atr_percentile": 50.0,
        "support_resistance": {"recent_high": 151.0, "recent_low": 148.5},
    }


@pytest.fixture
def bullish_trend_dict():
    """Trend TF (H4) indicator dict for bullish trend."""
    return {
        "symbol": "USDJPY",
        "timeframe": "H4",
        "last_close": 150.500,
        "rsi": {"value": 58.0, "condition": "neutral", "divergence": "none"},
        "macd": {"macd": 0.1, "signal": 0.05, "histogram": 0.05, "cross": "bullish"},
        "bollinger": {"upper": 152.0, "mid": 150.5, "lower": 149.0, "price_position": "inside"},
        "ichimoku": {
            "tenkan": 150.3, "kijun": 150.0,
            "senkou_a": 149.5, "senkou_b": 149.0,
            "cloud_position": "above_cloud", "tk_cross": "bullish",
        },
        "ema": {"ema_50": 150.2, "ema_100": 149.8, "ema_200": 149.5, "trend": "strong_bullish"},
        "atr": 0.500,
        "atr_pips": 500.0,
        "atr_percentile": 55.0,
        "support_resistance": {"recent_high": 152.0, "recent_low": 148.0},
    }


@pytest.fixture
def bearish_trend_dict():
    """Trend TF (H4) indicator dict for bearish trend."""
    return {
        "symbol": "USDJPY",
        "timeframe": "H4",
        "last_close": 149.000,
        "rsi": {"value": 42.0, "condition": "neutral", "divergence": "none"},
        "macd": {"macd": -0.1, "signal": -0.05, "histogram": -0.05, "cross": "bearish"},
        "bollinger": {"upper": 152.0, "mid": 150.5, "lower": 149.0, "price_position": "inside"},
        "ichimoku": {
            "tenkan": 149.3, "kijun": 149.6,
            "senkou_a": 150.5, "senkou_b": 151.0,
            "cloud_position": "below_cloud", "tk_cross": "bearish",
        },
        "ema": {"ema_50": 149.5, "ema_100": 150.0, "ema_200": 150.5, "trend": "strong_bearish"},
        "atr": 0.500,
        "atr_pips": 500.0,
        "atr_percentile": 55.0,
        "support_resistance": {"recent_high": 152.0, "recent_low": 148.0},
    }
