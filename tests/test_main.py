"""
test_main.py — Unit tests for time filters, circuit breaker, and duplicate order protection.
"""
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import main


class TestIsTradingAllowed:
    def _mock_time(self, weekday, hour):
        """Create a mock datetime with the given weekday and hour."""
        # 2024-01-01 is Monday (weekday=0). Offset to desired weekday.
        day = 1 + weekday
        return datetime(2024, 1, day, hour, 0, 0, tzinfo=timezone.utc)

    @patch("main.datetime")
    def test_sunday_rejected(self, mock_dt):
        mock_dt.now.return_value = self._mock_time(6, 12)
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        assert main.is_trading_allowed() is False

    @patch("main.datetime")
    def test_saturday_late_rejected(self, mock_dt):
        mock_dt.now.return_value = self._mock_time(5, 20)
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        assert main.is_trading_allowed() is False

    @patch("main.datetime")
    def test_friday_late_rejected(self, mock_dt):
        mock_dt.now.return_value = self._mock_time(4, 20)
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        assert main.is_trading_allowed() is False

    @patch("main.datetime")
    def test_friday_early_allowed(self, mock_dt):
        mock_dt.now.return_value = self._mock_time(4, 10)
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        assert main.is_trading_allowed() is True

    @patch("main.datetime")
    def test_weekday_allowed_hours(self, mock_dt):
        mock_dt.now.return_value = self._mock_time(1, 10)  # Tuesday 10:00
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        assert main.is_trading_allowed() is True

    @patch("main.datetime")
    def test_weekday_disallowed_hours(self, mock_dt):
        mock_dt.now.return_value = self._mock_time(1, 23)  # Tuesday 23:00
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        assert main.is_trading_allowed() is False


class TestOrderCooldown:
    def setup_method(self):
        main._recent_orders.clear()

    def test_no_cooldown_initially(self):
        assert main._order_cooldown_active("USDJPY") is False

    def test_cooldown_after_record(self):
        main._record_order("USDJPY")
        assert main._order_cooldown_active("USDJPY") is True

    def test_cooldown_per_symbol(self):
        main._record_order("USDJPY")
        assert main._order_cooldown_active("EURJPY") is False

    def test_cooldown_expires(self):
        main._recent_orders["USDJPY"] = time.time() - 400  # 6+ min ago
        assert main._order_cooldown_active("USDJPY") is False
