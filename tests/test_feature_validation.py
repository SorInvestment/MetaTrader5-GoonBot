"""
test_feature_validation.py — Integration-style tests validating all 16 features
added in the improvements commit. Each test exercises the feature end-to-end
with mocks to confirm correct wiring and behavior.

Run: python -m pytest tests/test_feature_validation.py -v
"""
import json
import logging
import logging.handlers
import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, call

import pytest

import config
import equity_tracker
import logger as trade_logger
import main
import news_filter
import position_manager as pm


# ---------------------------------------------------------------------------
# Feature 1: JPY pip_value fix (digits-based pip size)
# ---------------------------------------------------------------------------
class TestFeature01_JPYPipValue:
    """Verify lot sizing uses correct pip size based on symbol digits."""

    @patch("mt5_bridge.mt5")
    def test_jpy_pair_uses_001_pip(self, mock_mt5):
        """USDJPY (digits=3) should use pip_size=0.01, not 0.0001."""
        import mt5_bridge as mt5b

        mock_mt5.account_info.return_value = MagicMock(balance=10000.0)

        mock_info = MagicMock()
        mock_info.point = 0.001
        mock_info.trade_tick_value = 6.7
        mock_info.digits = 3
        mock_info.volume_min = 0.01
        mock_info.volume_max = 100.0
        mock_info.volume_step = 0.01
        mock_mt5.symbol_info.return_value = mock_info

        lot = mt5b.calculate_lot_size("USDJPY", sl_pips=15.0, risk_pct=1.0)
        # pip_size = 0.01 (digits=3), pip_value = 6.7 * (0.01 / 0.001) = 67.0
        # risk_amount = 10000 * 0.01 = 100, lot = 100 / (15 * 67) = 0.0995 -> 0.10
        assert lot == pytest.approx(0.10, abs=0.02)

    @patch("mt5_bridge.mt5")
    def test_non_jpy_pair_uses_00001_pip(self, mock_mt5):
        """EURUSD (digits=5) should use pip_size=0.0001."""
        import mt5_bridge as mt5b

        mock_mt5.account_info.return_value = MagicMock(balance=10000.0)

        mock_info = MagicMock()
        mock_info.point = 0.00001
        mock_info.trade_tick_value = 1.0
        mock_info.digits = 5
        mock_info.volume_min = 0.01
        mock_info.volume_max = 100.0
        mock_info.volume_step = 0.01
        mock_mt5.symbol_info.return_value = mock_info

        lot = mt5b.calculate_lot_size("EURUSD", sl_pips=15.0, risk_pct=1.0)
        # pip_size = 0.0001 (digits=5), pip_value = 1.0 * (0.0001 / 0.00001) = 10.0
        # risk_amount = 100, lot = 100 / (15 * 10) = 0.67
        assert lot == pytest.approx(0.67, abs=0.05)


# ---------------------------------------------------------------------------
# Feature 2: Circuit breaker
# ---------------------------------------------------------------------------
class TestFeature02_CircuitBreaker:
    """Circuit breaker pauses trading after MAX_CONSECUTIVE_LOSSES."""

    def setup_method(self):
        equity_tracker.reset_circuit_breaker()

    @patch("equity_tracker.trade_logger")
    def test_trips_at_5_losses(self, mock_logger):
        mock_logger.get_streak.return_value = -5
        assert equity_tracker.circuit_breaker_active() is True

    @patch("equity_tracker.trade_logger")
    def test_no_trip_at_4_losses(self, mock_logger):
        mock_logger.get_streak.return_value = -4
        assert equity_tracker.circuit_breaker_active() is False

    @patch("equity_tracker.trade_logger")
    def test_cooldown_duration(self, mock_logger):
        mock_logger.get_streak.return_value = -5
        equity_tracker.circuit_breaker_active()  # Trip

        # Still active 1 hour later
        equity_tracker._circuit_breaker_tripped_at = time.time() - 3600
        mock_logger.get_streak.return_value = 0
        assert equity_tracker.circuit_breaker_active() is True

        # Expired after 4+ hours
        equity_tracker._circuit_breaker_tripped_at = time.time() - (4 * 3600 + 1)
        assert equity_tracker.circuit_breaker_active() is False


# ---------------------------------------------------------------------------
# Feature 3: Limit order support
# ---------------------------------------------------------------------------
class TestFeature03_LimitOrders:
    """Limit orders placed for moderate-score signals."""

    @patch("mt5_bridge.mt5")
    def test_place_limit_order(self, mock_mt5):
        import mt5_bridge as mt5b

        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
        mock_mt5.TRADE_ACTION_PENDING = 5
        mock_mt5.ORDER_FILLING_IOC = 1
        mock_mt5.ORDER_TIME_GTC = 0

        mock_result = MagicMock()
        mock_result.retcode = 10009
        mock_result.order = 99999
        mock_mt5.order_send.return_value = mock_result

        result = mt5b.place_limit_order(
            symbol="USDJPY", direction="BUY", lot_size=0.1,
            limit_price=150.000, sl_price=149.500, tp_price=151.000,
        )
        assert result["success"] is True
        assert result["ticket"] == 99999

    @patch("mt5_bridge.mt5")
    def test_cancel_pending_order(self, mock_mt5):
        import mt5_bridge as mt5b

        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.TRADE_ACTION_REMOVE = 8

        mock_result = MagicMock()
        mock_result.retcode = 10009
        mock_mt5.order_send.return_value = mock_result

        result = mt5b.cancel_order(ticket=99999)
        assert result["success"] is True

    def test_limit_order_config_exists(self):
        assert hasattr(config, "USE_LIMIT_ORDERS")
        assert hasattr(config, "LIMIT_ORDER_SCORE_THRESHOLD")
        assert hasattr(config, "LIMIT_ORDER_EXPIRY_BARS")


# ---------------------------------------------------------------------------
# Feature 4: Per-symbol daily loss limit
# ---------------------------------------------------------------------------
class TestFeature04_SymbolDailyLoss:
    """Per-symbol loss limit blocks trading after threshold."""

    @patch("position_manager.mt5b")
    @patch("position_manager.trade_logger")
    def test_blocks_when_exceeded(self, mock_logger, mock_mt5b):
        mock_mt5b.get_account_info.return_value = {"balance": 10000.0}
        # 1.5% of 10000 = 150. Loss of 200 exceeds it.
        mock_logger.get_symbol_daily_pnl.return_value = -200.0
        assert pm.symbol_daily_loss_ok("USDJPY") is False

    @patch("position_manager.mt5b")
    @patch("position_manager.trade_logger")
    def test_allows_when_within_limit(self, mock_logger, mock_mt5b):
        mock_mt5b.get_account_info.return_value = {"balance": 10000.0}
        mock_logger.get_symbol_daily_pnl.return_value = -100.0
        assert pm.symbol_daily_loss_ok("USDJPY") is True


# ---------------------------------------------------------------------------
# Feature 5: Multi-TP target scale-out
# ---------------------------------------------------------------------------
class TestFeature05_MultiTP:
    """Multi-TP scale-out closes at 1R, 2R, 3R."""

    def setup_method(self):
        pm._multi_tp_completed.clear()

    @patch("position_manager.mt5b")
    @patch("position_manager.trade_logger")
    @patch("position_manager.notify_trade")
    def test_scales_out_at_each_level(self, mock_notify, mock_logger, mock_mt5b):
        mock_mt5b.partial_close.return_value = {"success": True, "remaining_volume": 0.07}

        # Simulate 1.5R profit — should trigger 1R target
        pm._handle_multi_tp_scaleout(
            ticket=100, symbol="USDJPY", direction="BUY", volume=0.10,
            current_profit_r=1.5, current_price=151.0, current_sl=149.5, current_tp=152.0,
        )
        assert 1.0 in pm._multi_tp_completed[100]
        assert mock_mt5b.partial_close.called

    @patch("position_manager.mt5b")
    @patch("position_manager.trade_logger")
    @patch("position_manager.notify_trade")
    def test_does_not_repeat_level(self, mock_notify, mock_logger, mock_mt5b):
        pm._multi_tp_completed[100] = {1.0}

        pm._handle_multi_tp_scaleout(
            ticket=100, symbol="USDJPY", direction="BUY", volume=0.07,
            current_profit_r=1.5, current_price=151.0, current_sl=149.5, current_tp=152.0,
        )
        # Should NOT call partial_close since 1.0R already completed and 2.0R not reached
        mock_mt5b.partial_close.assert_not_called()


# ---------------------------------------------------------------------------
# Feature 6: Log rotation (RotatingFileHandler)
# ---------------------------------------------------------------------------
class TestFeature06_LogRotation:
    """Verify log rotation is configured."""

    def test_config_has_rotation_settings(self):
        assert hasattr(config, "LOG_MAX_BYTES")
        assert config.LOG_MAX_BYTES == 10 * 1024 * 1024  # 10 MB
        assert hasattr(config, "LOG_BACKUP_COUNT")
        assert config.LOG_BACKUP_COUNT == 5

    def test_setup_logging_uses_rotating_handler(self, tmp_path):
        """After setup_logging, the root logger should have a RotatingFileHandler."""
        # Use a temp log file to avoid polluting the project
        original_log = config.LOG_FILE
        config.LOG_FILE = str(tmp_path / "test.log")

        # Clear existing handlers
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)

        trade_logger.setup_logging()

        rotating_handlers = [
            h for h in root.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(rotating_handlers) >= 1
        handler = rotating_handlers[0]
        assert handler.maxBytes == config.LOG_MAX_BYTES
        assert handler.backupCount == config.LOG_BACKUP_COUNT

        # Cleanup
        for h in root.handlers[:]:
            root.removeHandler(h)
        config.LOG_FILE = original_log


# ---------------------------------------------------------------------------
# Feature 7: Health reconnect exponential backoff
# ---------------------------------------------------------------------------
class TestFeature07_HealthReconnect:
    """Health reconnect uses exponential backoff."""

    def test_config_has_reconnect_settings(self):
        assert config.RECONNECT_MAX_RETRIES == 5
        assert config.RECONNECT_BASE_WAIT == 5

    @patch("time.sleep")
    def test_backoff_attempts(self, mock_sleep):
        from health import HealthMonitor
        import mt5_bridge as mt5b_mod

        health_mon = HealthMonitor()

        with patch.object(mt5b_mod, "get_account_info", return_value={"error": "disconnected"}):
            mock_connect = MagicMock(return_value=False)
            mock_disconnect = MagicMock()

            result = health_mon.check_connection(mock_connect, mock_disconnect)
            assert result is False
            assert mock_connect.call_count == config.RECONNECT_MAX_RETRIES

            # Verify exponential backoff delays: 5, 10, 20, 40, 80
            expected_delays = [config.RECONNECT_BASE_WAIT * (2 ** i) for i in range(config.RECONNECT_MAX_RETRIES)]
            actual_delays = [c.args[0] for c in mock_sleep.call_args_list]
            assert actual_delays == expected_delays


# ---------------------------------------------------------------------------
# Feature 8: Post-news buffer
# ---------------------------------------------------------------------------
class TestFeature08_PostNewsBuffer:
    """Post-news buffer blocks trading after high-impact events."""

    def test_config_exists(self):
        assert config.NEWS_POST_BUFFER_MINUTES == 15

    @patch.object(config, "NEWS_FILTER_ENABLED", True)
    @patch.object(news_filter, "_load_cached_calendar")
    def test_blocks_after_event(self, mock_cal):
        now = datetime.now(timezone.utc)
        # Event happened 10 minutes ago
        event_time = now - timedelta(minutes=10)
        mock_cal.return_value = [{
            "date": event_time.isoformat(),
            "title": "NFP",
            "country": "USD",
            "impact": "High",
        }]
        assert news_filter.is_news_window("USDJPY", post_buffer_minutes=15) is True

    @patch.object(config, "NEWS_FILTER_ENABLED", True)
    @patch.object(news_filter, "_load_cached_calendar")
    def test_allows_after_buffer_expires(self, mock_cal):
        now = datetime.now(timezone.utc)
        event_time = now - timedelta(minutes=20)  # 20 min ago > 15 min buffer
        mock_cal.return_value = [{
            "date": event_time.isoformat(),
            "title": "NFP",
            "country": "USD",
            "impact": "High",
        }]
        assert news_filter.is_news_window("USDJPY", post_buffer_minutes=15) is False


# ---------------------------------------------------------------------------
# Feature 9: Closed-trade reconciliation
# ---------------------------------------------------------------------------
class TestFeature09_Reconciliation:
    """Detect positions closed outside the bot and update DB."""

    @patch("position_manager.notify")
    @patch("position_manager._get_closed_profit", return_value=50.0)
    @patch("position_manager.trade_logger")
    @patch("position_manager.mt5b")
    def test_reconciles_missing_position(self, mock_mt5b, mock_logger, mock_profit, mock_notify):
        mock_logger.get_open_tickets.return_value = [100, 200]
        mock_mt5b.get_positions.return_value = {"positions": [{"ticket": 200}], "count": 1}

        pm.reconcile_closed_trades()

        mock_logger.update_trade_close.assert_called_once_with(100, 50.0)

    @patch("position_manager.trade_logger")
    @patch("position_manager.mt5b")
    def test_no_action_when_all_present(self, mock_mt5b, mock_logger):
        mock_logger.get_open_tickets.return_value = [100]
        mock_mt5b.get_positions.return_value = {"positions": [{"ticket": 100}], "count": 1}

        pm.reconcile_closed_trades()
        mock_logger.update_trade_close.assert_not_called()


# ---------------------------------------------------------------------------
# Feature 10: Graceful shutdown sync
# ---------------------------------------------------------------------------
class TestFeature10_GracefulShutdown:
    """Verify reconcile_closed_trades is called before disconnect in shutdown."""

    def test_reconcile_in_main_shutdown(self):
        """The main.py finally block should call reconcile_closed_trades."""
        import inspect
        source = inspect.getsource(main.main)
        assert "reconcile_closed_trades" in source
        assert "finally:" in source


# ---------------------------------------------------------------------------
# Feature 11: Margin pre-check
# ---------------------------------------------------------------------------
class TestFeature11_MarginPreCheck:
    """Verify margin is checked before trade execution."""

    @patch("mt5_bridge.mt5")
    def test_sufficient_margin(self, mock_mt5):
        import mt5_bridge as mt5b

        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=150.0, bid=149.997)
        mock_mt5.order_calc_margin.return_value = 500.0
        mock_mt5.account_info.return_value = MagicMock(margin_free=5000.0)

        result = mt5b.check_margin("USDJPY", "BUY", 0.1)
        assert result["ok"] is True
        assert result["required_margin"] == 500.0

    @patch("mt5_bridge.mt5")
    def test_insufficient_margin(self, mock_mt5):
        import mt5_bridge as mt5b

        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=150.0, bid=149.997)
        mock_mt5.order_calc_margin.return_value = 4800.0
        mock_mt5.account_info.return_value = MagicMock(margin_free=5000.0)

        result = mt5b.check_margin("USDJPY", "BUY", 0.1)
        # 5000 < 4800 * 1.1 = 5280 — insufficient with 10% buffer
        assert result["ok"] is False

    def test_margin_check_in_main_loop(self):
        """main.py run_cycle should call check_margin before execute_trade."""
        import inspect
        source = inspect.getsource(main.run_cycle)
        margin_idx = source.index("check_margin")
        execute_idx = source.index("execute_trade")
        assert margin_idx < execute_idx


# ---------------------------------------------------------------------------
# Feature 12: Duplicate order protection
# ---------------------------------------------------------------------------
class TestFeature12_DuplicateOrderProtection:
    """5-minute cooldown per symbol prevents duplicate orders."""

    def setup_method(self):
        main._recent_orders.clear()

    def test_no_cooldown_initially(self):
        assert main._order_cooldown_active("USDJPY") is False

    def test_cooldown_after_order(self):
        main._record_order("USDJPY")
        assert main._order_cooldown_active("USDJPY") is True
        assert main._order_cooldown_active("EURJPY") is False

    def test_cooldown_expires(self):
        main._recent_orders["USDJPY"] = time.time() - 301  # > 300s
        assert main._order_cooldown_active("USDJPY") is False


# ---------------------------------------------------------------------------
# Feature 13: SQLite WAL mode
# ---------------------------------------------------------------------------
class TestFeature13_SQLiteWAL:
    """Database uses WAL journal mode for concurrent access."""

    def test_wal_mode_on_init(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        original = config.TRADE_DB
        config.TRADE_DB = db_path
        trade_logger.init_db()

        conn = sqlite3.connect(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        config.TRADE_DB = original
        assert mode == "wal"


# ---------------------------------------------------------------------------
# Feature 14: News cache 48h + configurable
# ---------------------------------------------------------------------------
class TestFeature14_NewsCache:
    """News cache duration is 48h and configurable."""

    def test_default_cache_48h(self):
        assert config.NEWS_CACHE_HOURS == 48

    def test_cache_respects_config(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        # Write cache from 47 hours ago — should still be valid
        cache_data = {
            "timestamp": time.time() - (47 * 3600),
            "events": [{"title": "Test"}],
        }
        cache_file.write_text(json.dumps(cache_data))

        with patch.object(news_filter, "_CACHE_FILE", str(cache_file)):
            result = news_filter._load_cached_calendar()
        assert len(result) == 1

    def test_cache_expires_after_config(self, tmp_path):
        cache_file = tmp_path / "cache.json"
        cache_data = {
            "timestamp": time.time() - (49 * 3600),  # > 48h
            "events": [{"title": "Old"}],
        }
        cache_file.write_text(json.dumps(cache_data))

        with patch.object(news_filter, "_CACHE_FILE", str(cache_file)), \
             patch.object(news_filter, "_fetch_calendar", return_value=[{"title": "Fresh"}]):
            result = news_filter._load_cached_calendar()
        assert result[0]["title"] == "Fresh"


# ---------------------------------------------------------------------------
# Feature 15: Next week calendar fetch
# ---------------------------------------------------------------------------
class TestFeature15_NextWeekCalendar:
    """Calendar fetches both this week and next week events."""

    def test_config_has_next_week_url(self):
        assert hasattr(config, "NEWS_CALENDAR_NEXT_WEEK_URL")
        assert "nextweek" in config.NEWS_CALENDAR_NEXT_WEEK_URL

    @patch.object(news_filter, "_fetch_single_calendar")
    def test_fetches_both_calendars(self, mock_fetch):
        this_week = [{"date": "2024-01-02", "title": "A", "country": "USD"}]
        next_week = [{"date": "2024-01-09", "title": "B", "country": "EUR"}]
        mock_fetch.side_effect = [this_week, next_week]

        with patch("builtins.open", MagicMock()):
            events = news_filter._fetch_calendar()

        assert len(events) == 2
        assert mock_fetch.call_count == 2

    @patch.object(news_filter, "_fetch_single_calendar")
    def test_deduplicates_events(self, mock_fetch):
        event = {"date": "2024-01-02", "title": "NFP", "country": "USD"}
        mock_fetch.side_effect = [[event], [event]]  # Same event in both feeds

        with patch("builtins.open", MagicMock()):
            events = news_filter._fetch_calendar()

        assert len(events) == 1


# ---------------------------------------------------------------------------
# Feature 16: requirements.txt
# ---------------------------------------------------------------------------
class TestFeature16_Requirements:
    """requirements.txt has correct dependencies."""

    def test_file_exists(self):
        req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
        assert os.path.exists(req_path)

    def test_core_dependencies(self):
        req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
        with open(req_path) as f:
            content = f.read()
        assert "MetaTrader5" in content
        assert "pandas" in content
        assert "numpy" in content
        assert "requests" in content
        assert "pytest" in content


# ---------------------------------------------------------------------------
# End-to-end: Config validation with new settings
# ---------------------------------------------------------------------------
class TestConfigValidation:
    """All new config keys pass validation."""

    def test_full_config_valid(self):
        from config_validator import validate
        validate()  # Should not raise

    def test_env_var_loading(self):
        """Config loads demo account credentials."""
        assert config.MT5_LOGIN == 5048716399
        assert config.MT5_SERVER == "MetaQuotes-Demo"
        assert len(config.MT5_PASSWORD) > 0
