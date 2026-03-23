"""
config_watcher.py — Config file hot-reload.
Detects changes to config.py and reloads without restart.
"""
import importlib
import logging
import os
from typing import Dict, Optional

log = logging.getLogger(__name__)

_config_path: str = os.path.join(os.path.dirname(__file__), "config.py")
_last_mtime: Optional[float] = None

# Settings that are safe to hot-reload
_RELOADABLE_KEYS = {
    "RISK_PER_TRADE_PCT", "MAX_OPEN_TRADES", "MAX_DRAWDOWN_PCT",
    "SPREAD_LIMIT_PIPS", "MIN_RR_RATIO", "SL_ATR_MULTIPLIER",
    "TP_ATR_MULTIPLIER", "BREAKEVEN_TRIGGER_R", "TRAIL_TRIGGER_R",
    "TRAIL_ATR_MULT", "RSI_OVERBOUGHT", "RSI_OVERSOLD",
    "RSI_BULL_MIN", "RSI_BEAR_MAX", "MIN_SIGNAL_SCORE",
    "ALLOWED_HOURS_UTC", "AVOID_FRIDAY_AFTER", "LOOP_INTERVAL_SECONDS",
    "MAX_CORRELATED_TRADES", "ATR_LOW_PERCENTILE", "ATR_HIGH_PERCENTILE",
    "REQUIRE_CANDLE_PATTERN", "DAILY_LOSS_LIMIT_PCT",
    "SCALE_OUT_AT_R", "SCALE_OUT_PCT", "NEWS_FILTER_ENABLED",
    "NEWS_BUFFER_MINUTES", "LOSING_STREAK_THRESHOLD",
    "STREAK_RISK_REDUCTION", "TELEGRAM_ENABLED", "DISCORD_ENABLED",
    "LOG_LEVEL", "SESSION_WEIGHTS",
}


def init() -> None:
    """Record initial config.py modification time."""
    global _last_mtime
    try:
        _last_mtime = os.path.getmtime(_config_path)
    except OSError:
        _last_mtime = None


def check_and_reload() -> bool:
    """Check if config.py has changed and reload if so. Returns True if reloaded."""
    global _last_mtime

    import config

    if not getattr(config, "HOT_RELOAD_ENABLED", True):
        return False

    try:
        current_mtime = os.path.getmtime(_config_path)
    except OSError:
        return False

    if _last_mtime is not None and current_mtime <= _last_mtime:
        return False

    # Capture old values for diff logging
    old_values: Dict[str, object] = {}
    for key in _RELOADABLE_KEYS:
        if hasattr(config, key):
            old_values[key] = getattr(config, key)

    # Reload
    try:
        importlib.reload(config)
    except Exception as e:
        log.error("Config reload failed: %s", e)
        return False

    _last_mtime = current_mtime

    # Log changes
    changes = []
    for key in _RELOADABLE_KEYS:
        new_val = getattr(config, key, None)
        old_val = old_values.get(key)
        if new_val != old_val:
            changes.append(f"{key}: {old_val} -> {new_val}")

    if changes:
        log.info("Config reloaded with changes: %s", "; ".join(changes))
    else:
        log.info("Config reloaded (no reloadable changes detected)")

    return True
