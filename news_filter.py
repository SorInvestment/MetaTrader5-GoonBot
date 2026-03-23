"""
news_filter.py — Economic calendar integration.
Fetches high-impact news events and pauses trading around them.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import config

log = logging.getLogger(__name__)

# Cache file for calendar data
_CACHE_FILE = "news_cache.json"
_CACHE_MAX_AGE = 6 * 3600  # 6 hours

# Map symbols to their constituent currencies
_SYMBOL_CURRENCIES: Dict[str, List[str]] = {
    "USDJPY": ["USD", "JPY"],
    "EURJPY": ["EUR", "JPY"],
    "GBPJPY": ["GBP", "JPY"],
    "EURUSD": ["EUR", "USD"],
    "GBPUSD": ["GBP", "USD"],
    "EURGBP": ["EUR", "GBP"],
}


def _fetch_calendar() -> List[dict]:
    """Download economic calendar from Forex Factory JSON feed."""
    try:
        import requests
        resp = requests.get(config.NEWS_CALENDAR_URL, timeout=10)
        resp.raise_for_status()
        events = resp.json()

        # Cache to disk
        with open(_CACHE_FILE, "w") as f:
            json.dump({"timestamp": time.time(), "events": events}, f)

        log.info("News calendar fetched: %d events", len(events))
        return events
    except Exception as e:
        log.error("Failed to fetch news calendar: %s", e)
        return []


def _load_cached_calendar() -> List[dict]:
    """Load calendar from cache if fresh enough, otherwise fetch."""
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE) as f:
                data = json.load(f)
            age = time.time() - data.get("timestamp", 0)
            if age < _CACHE_MAX_AGE:
                return data.get("events", [])
        except (json.JSONDecodeError, KeyError):
            pass

    return _fetch_calendar()


def is_news_window(symbol: str, buffer_minutes: Optional[int] = None) -> bool:
    """
    Check if a high-impact news event for the symbol's currencies
    is within the buffer window (before or after).
    """
    if not config.NEWS_FILTER_ENABLED:
        return False

    buffer = buffer_minutes or config.NEWS_BUFFER_MINUTES
    currencies = _SYMBOL_CURRENCIES.get(symbol, [])
    if not currencies:
        return False

    events = _load_cached_calendar()
    now = datetime.now(timezone.utc)

    for event in events:
        # Filter for high impact only
        impact = event.get("impact", "").lower()
        if impact not in ("high", "holiday"):
            continue

        # Check if event currency matches symbol
        event_currency = event.get("country", "").upper()
        if event_currency not in currencies:
            continue

        # Parse event time
        event_date = event.get("date", "")
        if not event_date:
            continue

        try:
            event_time = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        # Check if within buffer window
        delta = abs((event_time - now).total_seconds()) / 60.0
        if delta <= buffer:
            log.info(
                "News filter: %s blocked — %s event '%s' in %.0f minutes",
                symbol, event_currency, event.get("title", "unknown"), delta,
            )
            return True

    return False
