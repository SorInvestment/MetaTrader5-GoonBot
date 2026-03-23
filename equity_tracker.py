"""
equity_tracker.py — Losing streak detection, position size adjustment,
and circuit breaker logic.
Reduces risk during drawdown periods and pauses trading after extreme streaks.
"""
import logging
import time
from typing import Optional

import config
import logger as trade_logger

log = logging.getLogger(__name__)

# Circuit breaker state
_circuit_breaker_tripped_at: Optional[float] = None


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


def circuit_breaker_active() -> bool:
    """
    Return True if the circuit breaker is tripped and cooldown has not expired.
    Trips after MAX_CONSECUTIVE_LOSSES consecutive losses.
    Resets after CIRCUIT_BREAKER_COOLDOWN_HOURS.
    """
    global _circuit_breaker_tripped_at

    cooldown_seconds = config.CIRCUIT_BREAKER_COOLDOWN_HOURS * 3600

    # Check if currently in cooldown
    if _circuit_breaker_tripped_at is not None:
        elapsed = time.time() - _circuit_breaker_tripped_at
        if elapsed < cooldown_seconds:
            remaining_minutes = (cooldown_seconds - elapsed) / 60
            log.warning(
                "Circuit breaker active — %.0f minutes remaining",
                remaining_minutes,
            )
            return True
        else:
            log.info("Circuit breaker cooldown expired — resuming trading")
            _circuit_breaker_tripped_at = None
            return False

    # Check if we should trip the circuit breaker
    streak = trade_logger.get_streak()
    if streak <= -config.MAX_CONSECUTIVE_LOSSES:
        _circuit_breaker_tripped_at = time.time()
        log.warning(
            "CIRCUIT BREAKER TRIPPED: %d consecutive losses (threshold=%d) — "
            "pausing for %d hours",
            abs(streak), config.MAX_CONSECUTIVE_LOSSES,
            config.CIRCUIT_BREAKER_COOLDOWN_HOURS,
        )
        return True

    return False


def reset_circuit_breaker() -> None:
    """Manually reset the circuit breaker (e.g. after config reload)."""
    global _circuit_breaker_tripped_at
    _circuit_breaker_tripped_at = None
    log.info("Circuit breaker manually reset")
