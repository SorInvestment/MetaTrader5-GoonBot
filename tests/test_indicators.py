"""
test_indicators.py — Unit tests for the indicator calculation module.
"""
import numpy as np
import pandas as pd
import pytest

import indicators


class TestRSI:
    def test_rsi_returns_series(self, sample_candle_df):
        result = indicators._rsi(sample_candle_df["close"])
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_candle_df)

    def test_rsi_range(self, sample_candle_df):
        result = indicators._rsi(sample_candle_df["close"]).dropna()
        assert result.min() >= 0
        assert result.max() <= 100

    def test_rsi_trending_up(self, sample_candle_df):
        # RSI on the sample candle data should produce valid values
        rsi = indicators._rsi(sample_candle_df["close"], period=14)
        valid = rsi.dropna()
        assert len(valid) > 0
        # All values in valid range
        assert valid.min() >= 0
        assert valid.max() <= 100


class TestEMA:
    def test_ema_length(self, sample_candle_df):
        result = indicators._ema(sample_candle_df["close"], 50)
        assert len(result) == len(sample_candle_df)

    def test_ema_tracks_price(self, sample_candle_df):
        ema = indicators._ema(sample_candle_df["close"], 10)
        # EMA should be close to recent prices
        last_close = sample_candle_df["close"].iloc[-1]
        assert abs(ema.iloc[-1] - last_close) < last_close * 0.05


class TestMACD:
    def test_macd_returns_three_series(self, sample_candle_df):
        macd_line, signal_line, histogram = indicators._macd(sample_candle_df["close"])
        assert isinstance(macd_line, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(histogram, pd.Series)

    def test_macd_histogram_is_difference(self, sample_candle_df):
        macd_line, signal_line, histogram = indicators._macd(sample_candle_df["close"])
        diff = macd_line - signal_line
        np.testing.assert_array_almost_equal(histogram.values, diff.values)


class TestBollinger:
    def test_bollinger_band_order(self, sample_candle_df):
        upper, mid, lower = indicators._bollinger(sample_candle_df["close"])
        # Upper > Mid > Lower (where not NaN)
        valid = ~(upper.isna() | mid.isna() | lower.isna())
        assert (upper[valid] >= mid[valid]).all()
        assert (mid[valid] >= lower[valid]).all()


class TestATR:
    def test_atr_positive(self, sample_candle_df):
        result = indicators._atr(sample_candle_df).dropna()
        assert (result > 0).all()


class TestComputeIndicators:
    def test_returns_complete_dict(self, sample_candle_df):
        result = indicators.compute_indicators(sample_candle_df, "USDJPY", "H1")

        # Verify all top-level keys
        assert result["symbol"] == "USDJPY"
        assert result["timeframe"] == "H1"
        assert isinstance(result["last_close"], float)
        assert isinstance(result["rsi"], dict)
        assert isinstance(result["macd"], dict)
        assert isinstance(result["bollinger"], dict)
        assert isinstance(result["ichimoku"], dict)
        assert isinstance(result["ema"], dict)
        assert isinstance(result["atr"], float)
        assert isinstance(result["atr_pips"], float)
        assert isinstance(result["atr_percentile"], float)
        assert isinstance(result["support_resistance"], dict)

    def test_rsi_condition_values(self, sample_candle_df):
        result = indicators.compute_indicators(sample_candle_df, "USDJPY", "H1")
        assert result["rsi"]["condition"] in ("overbought", "oversold", "neutral")

    def test_macd_cross_values(self, sample_candle_df):
        result = indicators.compute_indicators(sample_candle_df, "USDJPY", "H1")
        assert result["macd"]["cross"] in ("bullish", "bearish")

    def test_bollinger_position_values(self, sample_candle_df):
        result = indicators.compute_indicators(sample_candle_df, "USDJPY", "H1")
        assert result["bollinger"]["price_position"] in ("above_upper", "below_lower", "inside")

    def test_ema_trend_values(self, sample_candle_df):
        result = indicators.compute_indicators(sample_candle_df, "USDJPY", "H1")
        assert result["ema"]["trend"] in ("strong_bullish", "strong_bearish", "mixed")

    def test_ichimoku_cloud_position_values(self, sample_candle_df):
        result = indicators.compute_indicators(sample_candle_df, "USDJPY", "H1")
        assert result["ichimoku"]["cloud_position"] in ("above_cloud", "below_cloud", "inside_cloud")

    def test_atr_percentile_range(self, sample_candle_df):
        result = indicators.compute_indicators(sample_candle_df, "USDJPY", "H1")
        assert 0 <= result["atr_percentile"] <= 100
