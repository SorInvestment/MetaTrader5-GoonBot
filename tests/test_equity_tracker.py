"""Tests for equity_tracker.py — streak adjustment and circuit breaker."""
import time
from unittest.mock import patch

import pytest

import config
import equity_tracker


class TestGetSizeAdjustment:
    @patch("equity_tracker.trade_logger")
    def test_no_streak_returns_1(self, mock_logger):
        mock_logger.get_streak.return_value = 0
        assert equity_tracker.get_size_adjustment() == 1.0

    @patch("equity_tracker.trade_logger")
    def test_winning_streak_returns_1(self, mock_logger):
        mock_logger.get_streak.return_value = 5
        assert equity_tracker.get_size_adjustment() == 1.0

    @patch("equity_tracker.trade_logger")
    def test_losing_streak_reduces(self, mock_logger):
        mock_logger.get_streak.return_value = -3  # == LOSING_STREAK_THRESHOLD
        result = equity_tracker.get_size_adjustment()
        assert result == config.STREAK_RISK_REDUCTION

    @patch("equity_tracker.trade_logger")
    def test_deep_losing_streak_reduces(self, mock_logger):
        mock_logger.get_streak.return_value = -7
        result = equity_tracker.get_size_adjustment()
        assert result == config.STREAK_RISK_REDUCTION


class TestGetAdjustedRiskPct:
    @patch("equity_tracker.trade_logger")
    def test_normal_returns_base_risk(self, mock_logger):
        mock_logger.get_streak.return_value = 0
        assert equity_tracker.get_adjusted_risk_pct() == config.RISK_PER_TRADE_PCT

    @patch("equity_tracker.trade_logger")
    def test_streak_reduces_risk(self, mock_logger):
        mock_logger.get_streak.return_value = -3
        result = equity_tracker.get_adjusted_risk_pct()
        expected = round(config.RISK_PER_TRADE_PCT * config.STREAK_RISK_REDUCTION, 2)
        assert result == expected


class TestCircuitBreaker:
    def setup_method(self):
        equity_tracker.reset_circuit_breaker()

    @patch("equity_tracker.trade_logger")
    def test_not_active_normal(self, mock_logger):
        mock_logger.get_streak.return_value = -2
        assert equity_tracker.circuit_breaker_active() is False

    @patch("equity_tracker.trade_logger")
    def test_trips_at_threshold(self, mock_logger):
        mock_logger.get_streak.return_value = -5  # == MAX_CONSECUTIVE_LOSSES
        assert equity_tracker.circuit_breaker_active() is True

    @patch("equity_tracker.trade_logger")
    def test_stays_active_during_cooldown(self, mock_logger):
        mock_logger.get_streak.return_value = -5
        equity_tracker.circuit_breaker_active()  # Trip it
        # Still active on next check (even if streak recovered)
        mock_logger.get_streak.return_value = 0
        assert equity_tracker.circuit_breaker_active() is True

    @patch("equity_tracker.trade_logger")
    def test_resets_after_cooldown(self, mock_logger):
        mock_logger.get_streak.return_value = -5
        equity_tracker.circuit_breaker_active()  # Trip it
        # Fast-forward past cooldown
        equity_tracker._circuit_breaker_tripped_at = time.time() - (5 * 3600)
        mock_logger.get_streak.return_value = 0
        assert equity_tracker.circuit_breaker_active() is False

    @patch("equity_tracker.trade_logger")
    def test_manual_reset(self, mock_logger):
        mock_logger.get_streak.return_value = -5
        equity_tracker.circuit_breaker_active()  # Trip it
        equity_tracker.reset_circuit_breaker()
        mock_logger.get_streak.return_value = 0
        assert equity_tracker.circuit_breaker_active() is False
