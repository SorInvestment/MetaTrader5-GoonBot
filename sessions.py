"""
sessions.py — Trading session detection and signal weighting.
Identifies Tokyo, London, New York sessions and overlaps.
"""
import logging
from datetime import datetime, timezone

import config

log = logging.getLogger(__name__)


def get_active_session(utc_hour: int) -> str:
    """Return the most relevant active trading session for the given UTC hour."""
    # Check overlap first (highest priority)
    overlap = config.SESSION_WEIGHTS.get("overlap_ldn_ny", {})
    if overlap:
        start, end = overlap["hours_utc"]
        if start <= utc_hour < end:
            return "overlap_ldn_ny"

    # Check individual sessions
    for name in ("london", "new_york", "tokyo"):
        session = config.SESSION_WEIGHTS.get(name, {})
        if session:
            start, end = session["hours_utc"]
            if start <= utc_hour < end:
                return name

    return "off_session"


def get_session_weight(utc_hour: int) -> float:
    """Return the signal weight multiplier for the current session."""
    session = get_active_session(utc_hour)
    session_data = config.SESSION_WEIGHTS.get(session, {})
    weight = session_data.get("weight", 1.0)
    log.debug("Session=%s hour=%d weight=%.2f", session, utc_hour, weight)
    return weight


def get_current_session_info() -> dict:
    """Return current session name and weight."""
    now = datetime.now(timezone.utc)
    session = get_active_session(now.hour)
    weight = get_session_weight(now.hour)
    return {
        "session": session,
        "weight": weight,
        "utc_hour": now.hour,
    }
