"""
test_signals.py — Unit tests for the signal scoring engine.
"""
import pytest
from unittest.mock import patch

import config
import signals


class TestScoreBull:
    def test_perfect_bull_score(self, bullish_indicator_dict, bullish_trend_dict):
        score, passed, failed = signals._score_bull(bullish_indicator_dict, bullish_trend_dict)
        assert score == 7.0
        assert len(failed) == 0
        assert len(passed) == 7

    def test_zero_bull_score(self, bearish_indicator_dict, bearish_trend_dict):
        score, passed, failed = signals._score_bull(bearish_indicator_dict, bearish_trend_dict)
        assert score < 3.0

    def test_macd_histogram_only_gives_half_point(self, bullish_indicator_dict, bullish_trend_dict):
        # MACD cross is bearish but histogram is positive
        bullish_indicator_dict["macd"]["cross"] = "bearish"
        bullish_indicator_dict["macd"]["histogram"] = 0.01
        score, passed, failed = signals._score_bull(bullish_indicator_dict, bullish_trend_dict)
        assert score == 6.5
        assert "macd_hist_positive_only" in passed


class TestScoreBear:
    def test_perfect_bear_score(self, bearish_indicator_dict, bearish_trend_dict):
        score, passed, failed = signals._score_bear(bearish_indicator_dict, bearish_trend_dict)
        assert score == 7.0
        assert len(failed) == 0
        assert len(passed) == 7

    def test_zero_bear_score(self, bullish_indicator_dict, bullish_trend_dict):
        score, passed, failed = signals._score_bear(bullish_indicator_dict, bullish_trend_dict)
        assert score < 3.0


class TestConfirmM15:
    def test_m15_bullish_confirmation(self, bullish_indicator_dict):
        confirmed, checks = signals._confirm_m15(bullish_indicator_dict, "BUY")
        assert confirmed is True
        assert len(checks) >= 2

    def test_m15_bearish_confirmation(self, bearish_indicator_dict):
        confirmed, checks = signals._confirm_m15(bearish_indicator_dict, "SELL")
        assert confirmed is True

    def test_m15_rejection(self, bearish_indicator_dict):
        # Try to confirm BUY with bearish indicators — should fail
        confirmed, checks = signals._confirm_m15(bearish_indicator_dict, "BUY")
        assert confirmed is False


class TestEvaluate:
    @patch("signals.get_session_weight", return_value=1.0)
    def test_buy_signal_generated(self, mock_weight, bullish_indicator_dict, bullish_trend_dict):
        signal = signals.evaluate(
            "USDJPY", bullish_indicator_dict, bullish_trend_dict,
            ask=150.500, bid=150.497,
        )
        assert signal.direction == "BUY"
        assert signal.is_valid
        assert signal.sl_price < 150.500
        assert signal.tp_price > 150.500

    @patch("signals.get_session_weight", return_value=1.0)
    def test_sell_signal_generated(self, mock_weight, bearish_indicator_dict, bearish_trend_dict):
        signal = signals.evaluate(
            "USDJPY", bearish_indicator_dict, bearish_trend_dict,
            ask=149.003, bid=149.000,
        )
        assert signal.direction == "SELL"
        assert signal.is_valid
        assert signal.sl_price > 149.000
        assert signal.tp_price < 149.000

    @patch("signals.get_session_weight", return_value=1.0)
    def test_no_signal_when_scores_low(self, mock_weight, bullish_indicator_dict, bullish_trend_dict):
        # Create a "mixed" state where neither bull nor bear reaches 5.0
        # Bull checks that fail: RSI out of zone, MACD bearish, TK bearish, above upper BB = 4 fails -> 3/7
        # Bear checks that fail: trend above ema200, above cloud, ema50>100, RSI out, TK bullish = many fails
        mixed_ind = bullish_indicator_dict.copy()
        mixed_ind["rsi"] = {"value": 70, "condition": "neutral", "divergence": "none"}
        mixed_ind["macd"] = {"macd": -0.01, "signal": 0.01, "histogram": -0.02, "cross": "bearish"}
        mixed_ind["ichimoku"] = dict(bullish_indicator_dict["ichimoku"])
        mixed_ind["ichimoku"]["tk_cross"] = "bearish"
        mixed_ind["bollinger"] = dict(bullish_indicator_dict["bollinger"])
        mixed_ind["bollinger"]["price_position"] = "above_upper"
        signal = signals.evaluate(
            "USDJPY", mixed_ind, bullish_trend_dict,
            ask=150.500, bid=150.497,
        )
        assert signal.direction is None
        assert not signal.is_valid

    @patch("signals.get_session_weight", return_value=0.7)
    def test_session_weight_can_reject(self, mock_weight, bullish_indicator_dict, bullish_trend_dict):
        # With weight=0.7, a score of 6 becomes 4.2, below threshold 5.0
        # Remove one passing condition to get score=6
        bullish_indicator_dict["rsi"]["value"] = 70  # outside bull zone
        signal = signals.evaluate(
            "USDJPY", bullish_indicator_dict, bullish_trend_dict,
            ask=150.500, bid=150.497,
        )
        assert signal.direction is None

    @patch("signals.get_session_weight", return_value=1.0)
    def test_rr_ratio_calculated(self, mock_weight, bullish_indicator_dict, bullish_trend_dict):
        signal = signals.evaluate(
            "USDJPY", bullish_indicator_dict, bullish_trend_dict,
            ask=150.500, bid=150.497,
        )
        expected_rr = round(config.TP_ATR_MULTIPLIER / config.SL_ATR_MULTIPLIER, 2)
        assert signal.rr_ratio == expected_rr

    @patch("signals.get_session_weight", return_value=1.0)
    def test_jpy_pip_size(self, mock_weight, bullish_indicator_dict, bullish_trend_dict):
        """JPY pairs should use 0.01 pip size for sl_pips calculation."""
        signal = signals.evaluate(
            "USDJPY", bullish_indicator_dict, bullish_trend_dict,
            ask=150.500, bid=150.497,
        )
        atr = bullish_indicator_dict["atr"]
        expected_sl_pips = round(atr * config.SL_ATR_MULTIPLIER / 0.01, 1)
        assert signal.sl_pips == expected_sl_pips

    @patch("signals.get_session_weight", return_value=1.0)
    def test_non_jpy_pip_size(self, mock_weight, bullish_indicator_dict, bullish_trend_dict):
        """Non-JPY pairs should use 0.0001 pip size."""
        # Pretend it's EURUSD
        signal = signals.evaluate(
            "EURUSD", bullish_indicator_dict, bullish_trend_dict,
            ask=1.10000, bid=1.09997,
        )
        atr = bullish_indicator_dict["atr"]
        expected_sl_pips = round(atr * config.SL_ATR_MULTIPLIER / 0.0001, 1)
        assert signal.sl_pips == expected_sl_pips
