"""Tests for config_validator.py — startup config validation."""
import pytest
from unittest.mock import patch

import config
from config_validator import ConfigError, validate


class TestConfigValidator:
    def test_valid_config_passes(self):
        """Default config should pass validation."""
        validate()

    def test_risk_too_high(self):
        with patch.object(config, "RISK_PER_TRADE_PCT", 10.0):
            with pytest.raises(ConfigError, match="RISK_PER_TRADE_PCT"):
                validate()

    def test_risk_too_low(self):
        with patch.object(config, "RISK_PER_TRADE_PCT", 0.01):
            with pytest.raises(ConfigError, match="RISK_PER_TRADE_PCT"):
                validate()

    def test_sl_gte_tp_errors(self):
        with patch.object(config, "SL_ATR_MULTIPLIER", 3.0), \
             patch.object(config, "TP_ATR_MULTIPLIER", 2.0):
            with pytest.raises(ConfigError, match="SL_ATR_MULTIPLIER"):
                validate()

    def test_empty_watchlist_errors(self):
        with patch.object(config, "WATCHLIST", []):
            with pytest.raises(ConfigError, match="WATCHLIST"):
                validate()

    def test_invalid_timeframe_errors(self):
        with patch.object(config, "ENTRY_TF", "M3"):
            with pytest.raises(ConfigError, match="ENTRY_TF"):
                validate()

    def test_rsi_inverted_errors(self):
        with patch.object(config, "RSI_OVERSOLD", 70), \
             patch.object(config, "RSI_OVERBOUGHT", 30):
            with pytest.raises(ConfigError, match="RSI_OVERSOLD"):
                validate()

    def test_tp_targets_sum_wrong(self):
        with patch.object(config, "TP_TARGETS", [
            {"r_multiple": 1.0, "close_pct": 0.5},
            {"r_multiple": 2.0, "close_pct": 0.3},
        ]):
            with pytest.raises(ConfigError, match="TP_TARGETS"):
                validate()

    def test_max_open_trades_zero_errors(self):
        with patch.object(config, "MAX_OPEN_TRADES", 0):
            with pytest.raises(ConfigError, match="MAX_OPEN_TRADES"):
                validate()

    def test_drawdown_over_50_errors(self):
        with patch.object(config, "MAX_DRAWDOWN_PCT", 60.0):
            with pytest.raises(ConfigError, match="MAX_DRAWDOWN_PCT"):
                validate()
