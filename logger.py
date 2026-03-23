"""
logger.py — File logging + SQLite trade history.
Supports both text and JSON log formats.
"""
import json
import logging
import logging.handlers
import sqlite3
from datetime import datetime, date, timezone
from typing import Dict, List, Optional

import config
from bot_types import TradeSummary

log = logging.getLogger(__name__)


class JSONFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record to a JSON string."""
        entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            entry["extra"] = record.extra_data
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def setup_logging() -> None:
    """Configure file + console logging. Supports text or JSON format."""
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    text_fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"

    # Console always gets human-readable text
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(text_fmt))

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
    )
    if getattr(config, "LOG_FORMAT", "text") == "json":
        file_handler.setFormatter(JSONFormatter())
    else:
        file_handler.setFormatter(logging.Formatter(text_fmt))

    logging.basicConfig(
        level=level,
        handlers=[file_handler, console_handler],
    )


def init_db() -> None:
    """Create trades table in SQLite if it does not exist. Enables WAL mode for concurrent access."""
    conn = sqlite3.connect(config.TRADE_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket          INTEGER,
            symbol          TEXT,
            direction       TEXT,
            lot_size        REAL,
            original_volume REAL,
            entry_price     REAL,
            sl              REAL,
            tp              REAL,
            comment         TEXT,
            open_time       TEXT,
            close_time      TEXT,
            close_price     REAL,
            profit          REAL,
            status          TEXT DEFAULT 'open'
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
        INSERT INTO trades (ticket, symbol, direction, lot_size, original_volume,
                            entry_price, sl, tp, comment, open_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticket,
            symbol,
            direction,
            lot_size,
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


def log_partial_close(ticket: int, closed_volume: float, remaining_volume: float, profit: float) -> None:
    """Log a partial close event by updating lot_size to remaining volume."""
    conn = sqlite3.connect(config.TRADE_DB)
    conn.execute(
        "UPDATE trades SET lot_size=?, comment=comment||' partial_close' WHERE ticket=? AND status='open'",
        (remaining_volume, ticket),
    )
    conn.commit()
    conn.close()
    log.info(
        "Partial close — ticket=%s closed=%.2f remaining=%.2f profit=%.2f",
        ticket, closed_volume, remaining_volume, profit,
    )


def update_trade_close(ticket: int, profit: float) -> None:
    """Mark a trade as closed with profit and close time."""
    conn = sqlite3.connect(config.TRADE_DB)
    conn.execute(
        "UPDATE trades SET status='closed', profit=?, close_time=? WHERE ticket=? AND status='open'",
        (profit, datetime.now(timezone.utc).isoformat(), ticket),
    )
    conn.commit()
    conn.close()
    log.info("Trade closed — ticket=%s  profit=%.2f", ticket, profit)


def get_trade_summary() -> TradeSummary:
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


def get_daily_pnl() -> float:
    """Return total realised P&L for today (UTC)."""
    today = date.today().isoformat()
    conn = sqlite3.connect(config.TRADE_DB)
    cur = conn.execute(
        "SELECT COALESCE(SUM(profit), 0) FROM trades WHERE status='closed' AND close_time LIKE ?",
        (today + "%",),
    )
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0


def get_symbol_daily_pnl(symbol: str) -> float:
    """Return total realised P&L for a specific symbol today (UTC)."""
    today = date.today().isoformat()
    conn = sqlite3.connect(config.TRADE_DB)
    cur = conn.execute(
        "SELECT COALESCE(SUM(profit), 0) FROM trades WHERE status='closed' AND symbol=? AND close_time LIKE ?",
        (symbol, today + "%"),
    )
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else 0.0


def get_recent_trades(n: int = 10) -> List[Dict]:
    """Fetch the last N closed trades ordered by close time."""
    conn = sqlite3.connect(config.TRADE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT * FROM trades WHERE status='closed' ORDER BY close_time DESC LIMIT ?",
        (n,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_open_tickets() -> List[int]:
    """Return all ticket numbers currently marked as open in the database."""
    conn = sqlite3.connect(config.TRADE_DB)
    cur = conn.execute("SELECT ticket FROM trades WHERE status='open'")
    tickets = [row[0] for row in cur.fetchall()]
    conn.close()
    return tickets


def get_streak() -> int:
    """Return current streak: negative for losses, positive for wins. 0 if no trades."""
    trades = get_recent_trades(20)
    if not trades:
        return 0
    streak = 0
    first_sign = None
    for t in trades:
        profit = t.get("profit", 0) or 0
        is_win = profit > 0
        if first_sign is None:
            first_sign = is_win
        if is_win != first_sign:
            break
        streak += 1
    return streak if first_sign else -streak
