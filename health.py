"""
health.py — Connection and loop health monitoring.
Detects disconnects, hung loops, and inactivity.
"""
import logging
import time
from typing import Optional

import config

log = logging.getLogger(__name__)


class HealthMonitor:
    """Tracks bot health: connection status, cycle timing, error counts."""

    def __init__(self) -> None:
        """Initialise health tracking state."""
        self.last_cycle_time: float = time.time()
        self.last_trade_time: Optional[float] = None
        self.consecutive_errors: int = 0
        self.total_cycles: int = 0
        self.inactive_cycles: int = 0
        self.last_health_check: float = time.time()

    def heartbeat(self) -> None:
        """Called after each successful cycle."""
        self.last_cycle_time = time.time()
        self.consecutive_errors = 0
        self.total_cycles += 1

    def record_error(self) -> int:
        """Record a cycle error. Returns current error count."""
        self.consecutive_errors += 1
        log.error(
            "Consecutive errors: %d/%d",
            self.consecutive_errors, config.MAX_CONSECUTIVE_ERRORS,
        )
        return self.consecutive_errors

    def record_trade(self) -> None:
        """Record that a trade was executed."""
        self.last_trade_time = time.time()
        self.inactive_cycles = 0

    def record_no_signal(self) -> None:
        """Record a cycle with no trade signals."""
        self.inactive_cycles += 1

    def is_critical(self) -> bool:
        """Return True if consecutive errors exceed threshold."""
        return self.consecutive_errors >= config.MAX_CONSECUTIVE_ERRORS

    def is_inactive(self) -> bool:
        """Return True if no signals for too many cycles."""
        return self.inactive_cycles >= config.MAX_INACTIVE_CYCLES

    def should_health_check(self) -> bool:
        """Return True if it's time for a periodic health check."""
        elapsed = time.time() - self.last_health_check
        if elapsed >= config.HEALTH_CHECK_INTERVAL:
            self.last_health_check = time.time()
            return True
        return False

    def check_connection(self, connect_fn: callable, disconnect_fn: callable) -> bool:
        """Verify MT5 connection, attempt reconnect if needed."""
        try:
            import mt5_bridge as mt5b
            acct = mt5b.get_account_info()
            if "error" in acct:
                log.warning("MT5 connection lost, attempting reconnect...")
                disconnect_fn()
                if connect_fn():
                    log.info("MT5 reconnected successfully")
                    return True
                else:
                    log.error("MT5 reconnection failed")
                    return False
            return True
        except Exception as e:
            log.error("Health check connection error: %s", e)
            return False

    def get_status(self) -> dict:
        """Return current health status summary."""
        now = time.time()
        cycle_age = now - self.last_cycle_time
        status = "ok"
        if self.consecutive_errors > 0:
            status = "degraded"
        if self.is_critical():
            status = "critical"

        return {
            "status": status,
            "total_cycles": self.total_cycles,
            "consecutive_errors": self.consecutive_errors,
            "inactive_cycles": self.inactive_cycles,
            "last_cycle_age_s": round(cycle_age, 1),
            "last_trade_age_s": round(now - self.last_trade_time, 1) if self.last_trade_time else None,
        }
