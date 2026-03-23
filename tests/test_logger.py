"""Tests for logger.py — trade database and logging."""
import os
import sqlite3
from datetime import datetime, timezone

import pytest

import config
import logger as trade_logger


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = str(tmp_path / "test_trades.db")
    original = config.TRADE_DB
    config.TRADE_DB = db_path
    trade_logger.init_db()
    yield db_path
    config.TRADE_DB = original


class TestInitDb:
    def test_creates_table(self, temp_db):
        conn = sqlite3.connect(temp_db)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        assert cur.fetchone() is not None
        conn.close()

    def test_wal_mode_enabled(self, temp_db):
        conn = sqlite3.connect(temp_db)
        cur = conn.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        assert mode == "wal"
        conn.close()


class TestLogTrade:
    def test_insert_and_retrieve(self, temp_db):
        trade_logger.log_trade(
            ticket=123, symbol="USDJPY", direction="BUY",
            lot_size=0.1, entry_price=150.0, sl=149.5, tp=151.0,
        )
        conn = sqlite3.connect(temp_db)
        cur = conn.execute("SELECT * FROM trades WHERE ticket=123")
        row = cur.fetchone()
        conn.close()
        assert row is not None


class TestGetOpenTickets:
    def test_returns_open_tickets(self, temp_db):
        trade_logger.log_trade(
            ticket=100, symbol="USDJPY", direction="BUY",
            lot_size=0.1, entry_price=150.0, sl=149.5, tp=151.0,
        )
        trade_logger.log_trade(
            ticket=200, symbol="EURJPY", direction="SELL",
            lot_size=0.1, entry_price=160.0, sl=160.5, tp=159.0,
        )
        # Close one
        trade_logger.update_trade_close(100, 50.0)
        tickets = trade_logger.get_open_tickets()
        assert 200 in tickets
        assert 100 not in tickets


class TestGetSymbolDailyPnl:
    def test_returns_symbol_pnl(self, temp_db):
        trade_logger.log_trade(
            ticket=100, symbol="USDJPY", direction="BUY",
            lot_size=0.1, entry_price=150.0, sl=149.5, tp=151.0,
        )
        trade_logger.update_trade_close(100, -25.0)
        pnl = trade_logger.get_symbol_daily_pnl("USDJPY")
        assert pnl == -25.0

    def test_ignores_other_symbols(self, temp_db):
        trade_logger.log_trade(
            ticket=100, symbol="USDJPY", direction="BUY",
            lot_size=0.1, entry_price=150.0, sl=149.5, tp=151.0,
        )
        trade_logger.update_trade_close(100, -25.0)
        pnl = trade_logger.get_symbol_daily_pnl("EURJPY")
        assert pnl == 0.0


class TestGetStreak:
    def test_losing_streak(self, temp_db):
        for i in range(3):
            trade_logger.log_trade(
                ticket=100 + i, symbol="USDJPY", direction="BUY",
                lot_size=0.1, entry_price=150.0, sl=149.5, tp=151.0,
            )
            trade_logger.update_trade_close(100 + i, -10.0)
        streak = trade_logger.get_streak()
        assert streak == -3

    def test_winning_streak(self, temp_db):
        for i in range(4):
            trade_logger.log_trade(
                ticket=200 + i, symbol="USDJPY", direction="BUY",
                lot_size=0.1, entry_price=150.0, sl=149.5, tp=151.0,
            )
            trade_logger.update_trade_close(200 + i, 20.0)
        streak = trade_logger.get_streak()
        assert streak == 4

    def test_empty_returns_zero(self, temp_db):
        assert trade_logger.get_streak() == 0
