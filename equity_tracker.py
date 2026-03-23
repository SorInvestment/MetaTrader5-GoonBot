"""
equity_tracker.py — Losing streak detection and position size adjustment.
Reduces risk during drawdown periods to protect capital.
"""
import logging

import config
import logger as trade_logger

log = logging.getLogger(__name__)


def get_size_adjustment() -> float:
    """
    Return a risk multiplier based on recent trade streak.
    1.0 = normal risk. < 1.0 = reduced risk during losing streak.
    """
    streak = trade_logger.get_streak()

    if streak <= -config.LOSING_STREAK_THRESHOLD:
        multiplier = config.STREAK_RISK_REDUCTION
        log.warning(
            "Losing streak detected: %d consecutive losses — reducing risk to %.0f%%",
            abs(streak), multiplier * 100,
        )
        return multiplier

    return 1.0


def get_adjusted_risk_pct() -> float:
    """Return the adjusted risk percentage accounting for streak."""
    base_risk = config.RISK_PER_TRADE_PCT
    adjustment = get_size_adjustment()
    adjusted = round(base_risk * adjustment, 2)
    if adjusted != base_risk:
        log.info("Risk adjusted: %.2f%% -> %.2f%%", base_risk, adjusted)
    return adjusted
