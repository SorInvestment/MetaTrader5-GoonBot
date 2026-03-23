"""
test_sessions.py — Unit tests for session detection and weighting.
"""
import pytest

import sessions


class TestGetActiveSession:
    def test_tokyo_session(self):
        assert sessions.get_active_session(3) == "tokyo"

    def test_london_session(self):
        assert sessions.get_active_session(10) == "london"

    def test_new_york_session(self):
        assert sessions.get_active_session(18) == "new_york"

    def test_overlap_session(self):
        assert sessions.get_active_session(14) == "overlap_ldn_ny"

    def test_off_session(self):
        assert sessions.get_active_session(23) == "off_session"


class TestGetSessionWeight:
    def test_tokyo_weight(self):
        weight = sessions.get_session_weight(3)
        assert weight == 0.8

    def test_london_weight(self):
        weight = sessions.get_session_weight(10)
        assert weight == 1.2

    def test_overlap_weight(self):
        weight = sessions.get_session_weight(14)
        assert weight == 1.3
