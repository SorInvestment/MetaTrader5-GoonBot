"""
test_candle_patterns.py — Unit tests for candlestick pattern detection.
"""
import pandas as pd
import pytest

import candle_patterns as cp


def _make_df(candles):
    """Build a DataFrame from a list of (open, high, low, close) tuples."""
    return pd.DataFrame(candles, columns=["open", "high", "low", "close"])


class TestPinBar:
    def test_bullish_pin_bar(self):
        # Long lower wick, small body at top
        df = _make_df([(150.0, 150.1, 149.0, 150.05)])
        assert cp.is_pin_bar(df) == "bullish"

    def test_bearish_pin_bar(self):
        # Long upper wick, small body at bottom
        df = _make_df([(149.95, 151.0, 149.9, 150.0)])
        assert cp.is_pin_bar(df) == "bearish"

    def test_no_pin_bar(self):
        # Normal candle, no extreme wick
        df = _make_df([(150.0, 150.5, 149.5, 150.3)])
        assert cp.is_pin_bar(df) is None


class TestEngulfing:
    def test_bullish_engulfing(self):
        df = _make_df([
            (150.5, 150.6, 150.0, 150.1),  # prev: bearish, small
            (150.0, 151.0, 149.9, 150.8),   # curr: bullish, engulfs prev
        ])
        assert cp.is_engulfing(df) == "bullish"

    def test_bearish_engulfing(self):
        df = _make_df([
            (150.0, 150.6, 149.9, 150.5),  # prev: bullish, small
            (150.6, 150.7, 149.8, 149.9),   # curr: bearish, engulfs prev
        ])
        assert cp.is_engulfing(df) == "bearish"

    def test_no_engulfing(self):
        df = _make_df([
            (150.0, 150.5, 149.5, 150.3),
            (150.2, 150.4, 150.0, 150.1),  # does not engulf
        ])
        assert cp.is_engulfing(df) is None


class TestInsideBar:
    def test_inside_bar(self):
        df = _make_df([
            (150.0, 151.0, 149.0, 150.5),
            (150.2, 150.8, 149.2, 150.4),  # inside previous range
        ])
        assert cp.is_inside_bar(df) is True

    def test_not_inside_bar(self):
        df = _make_df([
            (150.0, 150.5, 149.5, 150.3),
            (150.2, 151.0, 149.0, 150.1),  # exceeds previous range
        ])
        assert cp.is_inside_bar(df) is False


class TestHasConfirmingPattern:
    def test_bullish_pin_confirms_buy(self):
        patterns = {"pin_bar": "bullish", "engulfing": None, "inside_bar": False}
        assert cp.has_confirming_pattern(patterns, "BUY") is True

    def test_bearish_engulfing_confirms_sell(self):
        patterns = {"pin_bar": None, "engulfing": "bearish", "inside_bar": False}
        assert cp.has_confirming_pattern(patterns, "SELL") is True

    def test_inside_bar_confirms_any(self):
        patterns = {"pin_bar": None, "engulfing": None, "inside_bar": True}
        assert cp.has_confirming_pattern(patterns, "BUY") is True
        assert cp.has_confirming_pattern(patterns, "SELL") is True

    def test_no_pattern_rejects(self):
        patterns = {"pin_bar": None, "engulfing": None, "inside_bar": False}
        assert cp.has_confirming_pattern(patterns, "BUY") is False
