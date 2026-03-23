"""
candle_patterns.py — Candlestick pattern detection.
Pure functions operating on DataFrames, no I/O.
"""
import logging
from typing import Dict, List, Optional

import pandas as pd

log = logging.getLogger(__name__)


def _body_size(row: pd.Series) -> float:
    """Absolute size of the candle body."""
    return abs(row["close"] - row["open"])


def _range_size(row: pd.Series) -> float:
    """Full candle range (high - low)."""
    return row["high"] - row["low"]


def _is_bullish(row: pd.Series) -> bool:
    """True if close > open."""
    return row["close"] > row["open"]


def is_pin_bar(df: pd.DataFrame) -> Optional[str]:
    """Detect pin bar on the last candle. Returns 'bullish', 'bearish', or None."""
    if len(df) < 1:
        return None

    candle = df.iloc[-1]
    rng = _range_size(candle)
    if rng == 0:
        return None

    body = _body_size(candle)
    body_ratio = body / rng

    # Pin bar: small body (< 30% of range)
    if body_ratio > 0.30:
        return None

    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]

    # Bullish pin: long lower wick (> 60% of range)
    if lower_wick / rng > 0.60:
        return "bullish"

    # Bearish pin: long upper wick (> 60% of range)
    if upper_wick / rng > 0.60:
        return "bearish"

    return None


def is_engulfing(df: pd.DataFrame) -> Optional[str]:
    """Detect engulfing pattern on last two candles. Returns 'bullish', 'bearish', or None."""
    if len(df) < 2:
        return None

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    prev_body_top = max(prev["open"], prev["close"])
    prev_body_bot = min(prev["open"], prev["close"])
    curr_body_top = max(curr["open"], curr["close"])
    curr_body_bot = min(curr["open"], curr["close"])

    # Current body must fully engulf previous body
    if curr_body_top <= prev_body_top or curr_body_bot >= prev_body_bot:
        return None

    # Bullish engulfing: prev bearish, curr bullish
    if not _is_bullish(prev) and _is_bullish(curr):
        return "bullish"

    # Bearish engulfing: prev bullish, curr bearish
    if _is_bullish(prev) and not _is_bullish(curr):
        return "bearish"

    return None


def is_inside_bar(df: pd.DataFrame) -> bool:
    """Detect inside bar: current candle entirely within previous candle's range."""
    if len(df) < 2:
        return False

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    return bool(curr["high"] < prev["high"] and curr["low"] > prev["low"])


def detect_patterns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """Run all pattern detectors on the DataFrame. Returns a dict of pattern results."""
    last_bars = df.iloc[-3:] if len(df) >= 3 else df

    return {
        "pin_bar": is_pin_bar(last_bars),
        "engulfing": is_engulfing(last_bars),
        "inside_bar": is_inside_bar(last_bars),
    }


def has_confirming_pattern(patterns: Dict[str, Optional[str]], direction: str) -> bool:
    """Check if any detected pattern confirms the trade direction."""
    target = "bullish" if direction == "BUY" else "bearish"

    if patterns.get("pin_bar") == target:
        return True
    if patterns.get("engulfing") == target:
        return True
    # Inside bar is direction-neutral — confirms any breakout
    if patterns.get("inside_bar"):
        return True

    return False


def get_pattern_names(patterns: Dict[str, Optional[str]], direction: str) -> List[str]:
    """Return list of confirming pattern names for logging."""
    target = "bullish" if direction == "BUY" else "bearish"
    names: List[str] = []
    if patterns.get("pin_bar") == target:
        names.append(f"pin_bar_{target}")
    if patterns.get("engulfing") == target:
        names.append(f"engulfing_{target}")
    if patterns.get("inside_bar"):
        names.append("inside_bar")
    return names
