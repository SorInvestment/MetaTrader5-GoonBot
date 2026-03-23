"""
logger.py — File logging + SQLite trade history.
"""
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import config

log = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configure file + console logging."""
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.FileHandler(config.LOG_FILE),
            logging.StreamHandler(),
        ],
    )


def init_db() -> None:
    """Create trades table in SQLite if it does not exist."""
    conn = sqlite3.connect(config.TRADE_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket      INTEGER,
            symbol      TEXT,
            direction   TEXT,
            lot_size    REAL,
            entry_price REAL,
            sl          REAL,
            tp          REAL,
            comment     TEXT,
            open_time   TEXT,
            close_time  TEXT,
            close_price REAL,
            profit      REAL,
            status      TEXT DEFAULT 'open'
        )
        """
    )
    conn.commit()
    conn.close()
    log.info("Trade database initialised: %s", config.TRADE_DB)


def log_trade(
    ticket: int,
    symbol: str,
    direction: str,
    lot_size: float,
    entry_price: float,
    sl: float,
    tp: float,
    comment: str = "",
) -> None:
    """Insert a new trade record."""
    conn = sqlite3.connect(config.TRADE_DB)
    conn.execute(
        """
        INSERT INTO trades (ticket, symbol, direction, lot_size, entry_price, sl, tp, comment, open_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticket,
            symbol,
            direction,
            lot_size,
            entry_price,
            sl,
            tp,
            comment,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    log.info(
        "Trade logged — ticket=%s %s %s %.2f lots @ %.5f  SL=%.5f  TP=%.5f",
        ticket, direction, symbol, lot_size, entry_price, sl, tp,
    )


def update_trade_close(ticket: int, profit: float) -> None:
    """Mark a trade as closed with profit and close time."""
    conn = sqlite3.connect(config.TRADE_DB)
    conn.execute(
        """
        UPDATE trades SET status='closed', profit=?, close_time=? WHERE ticket=? AND status='open'
        """,
        (profit, datetime.now(timezone.utc).isoformat(), ticket),
    )
    conn.commit()
    conn.close()
    log.info("Trade closed — ticket=%s  profit=%.2f", ticket, profit)


def get_trade_summary() -> dict:
    """Return summary stats of closed trades."""
    conn = sqlite3.connect(config.TRADE_DB)
    cur = conn.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN profit <= 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(profit), 0) as total_profit
        FROM trades WHERE status='closed'
        """
    )
    row = cur.fetchone()
    conn.close()
    total = row[0] or 0
    wins = row[1] or 0
    losses = row[2] or 0
    total_profit = row[3] or 0.0
    win_rate = round((wins / total) * 100, 1) if total > 0 else 0.0
    return {
        "total_closed": total,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
        "total_profit": round(total_profit, 2),
    }
