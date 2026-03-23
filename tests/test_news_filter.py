"""Tests for news_filter.py — news calendar filtering."""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

import config
import news_filter


class TestNewsCacheConfig:
    def test_cache_max_age_uses_config(self):
        """Cache duration should come from config.NEWS_CACHE_HOURS."""
        assert config.NEWS_CACHE_HOURS == 48

    def test_post_buffer_config(self):
        """Post-news buffer should be configurable."""
        assert hasattr(config, "NEWS_POST_BUFFER_MINUTES")
        assert config.NEWS_POST_BUFFER_MINUTES > 0


class TestLoadCachedCalendar:
    def test_returns_cached_within_age(self, tmp_path):
        """Should return cached events when cache is fresh."""
        events = [{"date": "2024-01-02T14:00:00Z", "title": "NFP", "country": "USD", "impact": "High"}]
        cache_file = tmp_path / "test_cache.json"
        cache_file.write_text(json.dumps({"timestamp": time.time(), "events": events}))

        with patch.object(news_filter, "_CACHE_FILE", str(cache_file)):
            result = news_filter._load_cached_calendar()
        assert len(result) == 1
        assert result[0]["title"] == "NFP"

    def test_refetches_when_stale(self, tmp_path):
        """Should refetch when cache is older than NEWS_CACHE_HOURS."""
        stale_time = time.time() - (49 * 3600)  # 49 hours ago
        cache_file = tmp_path / "test_cache.json"
        cache_file.write_text(json.dumps({"timestamp": stale_time, "events": []}))

        with patch.object(news_filter, "_CACHE_FILE", str(cache_file)), \
             patch.object(news_filter, "_fetch_calendar", return_value=[{"title": "fresh"}]):
            result = news_filter._load_cached_calendar()
        assert result[0]["title"] == "fresh"


class TestIsNewsWindow:
    def _make_event(self, minutes_from_now: float, currency: str = "USD") -> list:
        """Create a test event at a specific offset from now."""
        now = datetime.now(timezone.utc)
        event_time = now + timedelta(minutes=minutes_from_now)
        return [{
            "date": event_time.isoformat(),
            "title": "Test Event",
            "country": currency,
            "impact": "High",
        }]

    @patch.object(config, "NEWS_FILTER_ENABLED", True)
    @patch.object(news_filter, "_load_cached_calendar")
    def test_blocks_before_news(self, mock_cal):
        """Should block trading within pre-buffer window."""
        mock_cal.return_value = self._make_event(15)  # 15 min from now
        assert news_filter.is_news_window("USDJPY", buffer_minutes=30) is True

    @patch.object(config, "NEWS_FILTER_ENABLED", True)
    @patch.object(news_filter, "_load_cached_calendar")
    def test_blocks_after_news(self, mock_cal):
        """Should block trading within post-buffer window."""
        mock_cal.return_value = self._make_event(-10)  # 10 min ago
        assert news_filter.is_news_window("USDJPY", buffer_minutes=30,
                                          post_buffer_minutes=15) is True

    @patch.object(config, "NEWS_FILTER_ENABLED", True)
    @patch.object(news_filter, "_load_cached_calendar")
    def test_allows_after_post_buffer(self, mock_cal):
        """Should allow trading after post-buffer expires."""
        mock_cal.return_value = self._make_event(-20)  # 20 min ago
        assert news_filter.is_news_window("USDJPY", buffer_minutes=30,
                                          post_buffer_minutes=15) is False

    @patch.object(config, "NEWS_FILTER_ENABLED", True)
    @patch.object(news_filter, "_load_cached_calendar")
    def test_allows_far_from_event(self, mock_cal):
        """Should allow trading when no event is near."""
        mock_cal.return_value = self._make_event(120)  # 2 hours away
        assert news_filter.is_news_window("USDJPY") is False

    @patch.object(config, "NEWS_FILTER_ENABLED", False)
    def test_disabled_filter_allows_all(self):
        """Should never block when NEWS_FILTER_ENABLED=False."""
        assert news_filter.is_news_window("USDJPY") is False

    @patch.object(config, "NEWS_FILTER_ENABLED", True)
    @patch.object(news_filter, "_load_cached_calendar")
    def test_ignores_low_impact_events(self, mock_cal):
        """Should not block for low-impact events."""
        now = datetime.now(timezone.utc)
        event_time = now + timedelta(minutes=10)
        mock_cal.return_value = [{
            "date": event_time.isoformat(),
            "title": "Minor Report",
            "country": "USD",
            "impact": "Low",
        }]
        assert news_filter.is_news_window("USDJPY") is False

    @patch.object(config, "NEWS_FILTER_ENABLED", True)
    @patch.object(news_filter, "_load_cached_calendar")
    def test_ignores_unrelated_currency(self, mock_cal):
        """Should not block when event currency doesn't match symbol."""
        mock_cal.return_value = self._make_event(10, currency="EUR")
        assert news_filter.is_news_window("USDJPY") is False
