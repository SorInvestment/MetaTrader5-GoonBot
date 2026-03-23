"""
news_filter.py — Economic calendar integration.
Fetches high-impact news events and pauses trading around them.
Supports configurable cache duration (default 48h) and fetches both
this week and next week calendars for full coverage.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import config

log = logging.getLogger(__name__)

# Cache file for calendar data
_CACHE_FILE = "news_cache.json"

# Map symbols to their constituent currencies
_SYMBOL_CURRENCIES: Dict[str, List[str]] = {
    "USDJPY": ["USD", "JPY"],
    "EURJPY": ["EUR", "JPY"],
    "GBPJPY": ["GBP", "JPY"],
    "EURUSD": ["EUR", "USD"],
    "GBPUSD": ["GBP", "USD"],
    "EURGBP": ["EUR", "GBP"],
    "AUDUSD": ["AUD", "USD"],
    "NZDUSD": ["NZD", "USD"],
    "USDCAD": ["USD", "CAD"],
    "USDCHF": ["USD", "CHF"],
}


def _fetch_single_calendar(url: str) -> List[dict]:
    """Download a single calendar feed."""
    try:
        import requests
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning("Failed to fetch calendar from %s: %s", url, e)
        return []


def _fetch_calendar() -> List[dict]:
    """Download economic calendar from Forex Factory JSON feeds (this week + next week)."""
    this_week = _fetch_single_calendar(config.NEWS_CALENDAR_URL)
    next_week = _fetch_single_calendar(config.NEWS_CALENDAR_NEXT_WEEK_URL)

    events = this_week + next_week

    # Deduplicate by (date, title, country)
    seen = set()
    unique_events = []
    for e in events:
        key = (e.get("date", ""), e.get("title", ""), e.get("country", ""))
        if key not in seen:
            seen.add(key)
            unique_events.append(e)

    # Cache to disk
    try:
        with open(_CACHE_FILE, "w") as f:
            json.dump({"timestamp": time.time(), "events": unique_events}, f)
    except OSError as e:
        log.warning("Failed to write news cache: %s", e)

    log.info("News calendar fetched: %d events (%d this week, %d next week)",
             len(unique_events), len(this_week), len(next_week))
    return unique_events


def _load_cached_calendar() -> List[dict]:
    """Load calendar from cache if fresh enough, otherwise fetch."""
    cache_max_age = getattr(config, "NEWS_CACHE_HOURS", 48) * 3600

    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE) as f:
                data = json.load(f)
            age = time.time() - data.get("timestamp", 0)
            if age < cache_max_age:
                return data.get("events", [])
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    return _fetch_calendar()


def is_news_window(symbol: str, buffer_minutes: Optional[int] = None,
                   post_buffer_minutes: Optional[int] = None) -> bool:
    """
    Check if a high-impact news event for the symbol's currencies
    is within the buffer window (before or after).

    Uses separate pre-event and post-event buffer durations.
    """
    if not config.NEWS_FILTER_ENABLED:
        return False

    pre_buffer = buffer_minutes or config.NEWS_BUFFER_MINUTES
    post_buffer = post_buffer_minutes or getattr(config, "NEWS_POST_BUFFER_MINUTES", 15)
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

        # Check if within pre or post buffer window
        delta_minutes = (event_time - now).total_seconds() / 60.0

        # Event is in the future and within pre-buffer
        if 0 <= delta_minutes <= pre_buffer:
            log.info(
                "News filter: %s blocked — %s event '%s' in %.0f minutes (pre-news)",
                symbol, event_currency, event.get("title", "unknown"), delta_minutes,
            )
            return True

        # Event already happened and within post-buffer
        if -post_buffer <= delta_minutes < 0:
            log.info(
                "News filter: %s blocked — %s event '%s' was %.0f minutes ago (post-news)",
                symbol, event_currency, event.get("title", "unknown"), abs(delta_minutes),
            )
            return True

    return False
