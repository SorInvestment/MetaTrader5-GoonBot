"""
config_validator.py — Validate config.py values at startup.
Catches misconfigurations before they cause trading errors.
"""
import logging
import sys
import config

log = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


def validate():
    """Validate all config values. Raises ConfigError on fatal issues, warns on suspicious values."""
    errors = []
    warnings = []

    # Risk sanity
    if not (0.1 <= config.RISK_PER_TRADE_PCT <= 5.0):
        errors.append(f"RISK_PER_TRADE_PCT={config.RISK_PER_TRADE_PCT} outside safe range 0.1-5.0")
    if config.MAX_DRAWDOWN_PCT <= 0 or config.MAX_DRAWDOWN_PCT > 50:
        errors.append(f"MAX_DRAWDOWN_PCT={config.MAX_DRAWDOWN_PCT} outside safe range 0-50")
    if config.DAILY_LOSS_LIMIT_PCT <= 0 or config.DAILY_LOSS_LIMIT_PCT > config.MAX_DRAWDOWN_PCT:
        warnings.append(f"DAILY_LOSS_LIMIT_PCT={config.DAILY_LOSS_LIMIT_PCT} > MAX_DRAWDOWN_PCT={config.MAX_DRAWDOWN_PCT}")

    # SL/TP relationship
    if config.SL_ATR_MULTIPLIER >= config.TP_ATR_MULTIPLIER:
        errors.append(f"SL_ATR_MULTIPLIER ({config.SL_ATR_MULTIPLIER}) >= TP_ATR_MULTIPLIER ({config.TP_ATR_MULTIPLIER})")
    if config.MIN_RR_RATIO < 1.0:
        warnings.append(f"MIN_RR_RATIO={config.MIN_RR_RATIO} below 1.0 (negative expectancy risk)")

    # Watchlist
    if not config.WATCHLIST:
        errors.append("WATCHLIST is empty")

    # Timeframes
    valid_tfs = {"M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"}
    for tf_name in ("TREND_TF", "ENTRY_TF", "CONFIRM_TF"):
        tf_val = getattr(config, tf_name, "")
        if tf_val not in valid_tfs:
            errors.append(f"{tf_name}='{tf_val}' not in {valid_tfs}")

    # Trail/breakeven ordering
    if config.BREAKEVEN_TRIGGER_R >= config.TRAIL_TRIGGER_R:
        warnings.append(f"BREAKEVEN_TRIGGER_R ({config.BREAKEVEN_TRIGGER_R}) >= TRAIL_TRIGGER_R ({config.TRAIL_TRIGGER_R})")

    # Scale out
    if config.SCALE_OUT_PCT <= 0 or config.SCALE_OUT_PCT >= 1.0:
        warnings.append(f"SCALE_OUT_PCT={config.SCALE_OUT_PCT} should be between 0 and 1")

    # RSI ordering
    if config.RSI_OVERSOLD >= config.RSI_OVERBOUGHT:
        errors.append(f"RSI_OVERSOLD ({config.RSI_OVERSOLD}) >= RSI_OVERBOUGHT ({config.RSI_OVERBOUGHT})")

    # TP targets if they exist
    if hasattr(config, "TP_TARGETS"):
        total_pct = sum(t.get("close_pct", 0) for t in config.TP_TARGETS)
        if abs(total_pct - 1.0) > 0.01:
            errors.append(f"TP_TARGETS close_pct sum={total_pct:.2f}, should be 1.0")

    # Losing streak
    if config.LOSING_STREAK_THRESHOLD < 1:
        errors.append(f"LOSING_STREAK_THRESHOLD={config.LOSING_STREAK_THRESHOLD} must be >= 1")
    if not (0 < config.STREAK_RISK_REDUCTION <= 1.0):
        errors.append(f"STREAK_RISK_REDUCTION={config.STREAK_RISK_REDUCTION} must be in (0, 1]")

    # Max open trades
    if config.MAX_OPEN_TRADES < 1:
        errors.append(f"MAX_OPEN_TRADES={config.MAX_OPEN_TRADES} must be >= 1")

    # Loop interval
    if config.LOOP_INTERVAL_SECONDS < 10:
        warnings.append(f"LOOP_INTERVAL_SECONDS={config.LOOP_INTERVAL_SECONDS} very short, may cause rate limiting")

    # Log results
    for w in warnings:
        log.warning("Config warning: %s", w)
    for e in errors:
        log.error("Config error: %s", e)

    if errors:
        raise ConfigError(f"{len(errors)} config error(s): " + "; ".join(errors))

    log.info("Config validation passed (%d warnings)", len(warnings))
