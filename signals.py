"""
signals.py — 7-point signal scoring engine with session weighting,
M15 confirmation, and candlestick pattern gating.
Pure logic — no I/O, no MT5 imports.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import config
from candle_patterns import detect_patterns, has_confirming_pattern, get_pattern_names
from sessions import get_session_weight

log = logging.getLogger(__name__)


@dataclass
class Signal:
    """Represents a trade signal with entry, SL, TP, and scoring details."""

    symbol: str
    direction: Optional[str] = None       # "BUY" | "SELL" | None
    sl_pips: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    entry_price: float = 0.0
    rr_ratio: float = 0.0
    raw_score: float = 0.0
    weighted_score: float = 0.0
    reasons: List[str] = field(default_factory=list)    # conditions that passed
    rejected: List[str] = field(default_factory=list)   # conditions that failed

    @property
    def is_valid(self) -> bool:
        """Signal is valid if direction set, SL/TP positive, and RR meets minimum."""
        return (
            self.direction is not None
            and self.sl_price > 0
            and self.tp_price > 0
            and self.rr_ratio >= config.MIN_RR_RATIO
        )


def _score_bull(ind: dict, trend_ind: dict) -> Tuple[float, List[str], List[str]]:
    """Score bullish conditions (7-point checklist). Returns (score, passed, failed)."""
    score = 0.0
    passed: List[str] = []
    failed: List[str] = []

    # 1. Trend: price above EMA200 on higher TF
    if trend_ind["last_close"] > trend_ind["ema"]["ema_200"]:
        score += 1
        passed.append("trend_above_ema200")
    else:
        failed.append("trend_below_ema200")

    # 2. Ichimoku cloud on higher TF
    if trend_ind["ichimoku"]["cloud_position"] == "above_cloud":
        score += 1
        passed.append("trend_above_cloud")
    else:
        failed.append(f"trend_cloud={trend_ind['ichimoku']['cloud_position']}")

    # 3. EMA50 > EMA100 on entry TF
    if ind["ema"]["ema_50"] > ind["ema"]["ema_100"]:
        score += 1
        passed.append("ema50_above_ema100")
    else:
        failed.append("ema50_below_ema100")

    # 4. RSI in bull zone
    rsi = ind["rsi"]["value"]
    if config.RSI_BULL_MIN <= rsi <= config.RSI_OVERBOUGHT:
        score += 1
        passed.append(f"rsi_bull_zone={rsi}")
    else:
        failed.append(f"rsi_out_of_bull_zone={rsi}")

    # 5. MACD bullish cross + positive histogram (0.5 for histogram only)
    macd = ind["macd"]
    if macd["cross"] == "bullish" and macd["histogram"] > 0:
        score += 1
        passed.append("macd_bullish_cross+hist")
    elif macd["histogram"] > 0:
        score += 0.5
        passed.append("macd_hist_positive_only")
    else:
        failed.append("macd_not_bullish")

    # 6. Ichimoku TK cross bullish on entry TF
    if ind["ichimoku"]["tk_cross"] == "bullish":
        score += 1
        passed.append("tk_cross_bullish")
    else:
        failed.append("tk_cross_bearish")

    # 7. Bollinger: price not above upper band
    if ind["bollinger"]["price_position"] != "above_upper":
        score += 1
        passed.append("not_above_upper_bb")
    else:
        failed.append("above_upper_bb")

    return score, passed, failed


def _score_bear(ind: dict, trend_ind: dict) -> Tuple[float, List[str], List[str]]:
    """Score bearish conditions (7-point checklist). Returns (score, passed, failed)."""
    score = 0.0
    passed: List[str] = []
    failed: List[str] = []

    # 1. Trend: price below EMA200 on higher TF
    if trend_ind["last_close"] < trend_ind["ema"]["ema_200"]:
        score += 1
        passed.append("trend_below_ema200")
    else:
        failed.append("trend_above_ema200")

    # 2. Ichimoku cloud on higher TF
    if trend_ind["ichimoku"]["cloud_position"] == "below_cloud":
        score += 1
        passed.append("trend_below_cloud")
    else:
        failed.append(f"trend_cloud={trend_ind['ichimoku']['cloud_position']}")

    # 3. EMA50 < EMA100 on entry TF
    if ind["ema"]["ema_50"] < ind["ema"]["ema_100"]:
        score += 1
        passed.append("ema50_below_ema100")
    else:
        failed.append("ema50_above_ema100")

    # 4. RSI in bear zone
    rsi = ind["rsi"]["value"]
    if config.RSI_OVERSOLD <= rsi <= config.RSI_BEAR_MAX:
        score += 1
        passed.append(f"rsi_bear_zone={rsi}")
    else:
        failed.append(f"rsi_out_of_bear_zone={rsi}")

    # 5. MACD bearish cross + negative histogram (0.5 for histogram only)
    macd = ind["macd"]
    if macd["cross"] == "bearish" and macd["histogram"] < 0:
        score += 1
        passed.append("macd_bearish_cross+hist")
    elif macd["histogram"] < 0:
        score += 0.5
        passed.append("macd_hist_negative_only")
    else:
        failed.append("macd_not_bearish")

    # 6. Ichimoku TK cross bearish on entry TF
    if ind["ichimoku"]["tk_cross"] == "bearish":
        score += 1
        passed.append("tk_cross_bearish")
    else:
        failed.append("tk_cross_bullish")

    # 7. Bollinger: price not below lower band
    if ind["bollinger"]["price_position"] != "below_lower":
        score += 1
        passed.append("not_below_lower_bb")
    else:
        failed.append("below_lower_bb")

    return score, passed, failed


def _confirm_m15(confirm_ind: dict, direction: str) -> Tuple[bool, List[str]]:
    """
    M15 confirmation gate. Checks 3 conditions on M15 timeframe.
    Requires at least 2/3 to pass.
    """
    checks: List[str] = []
    passed = 0

    if direction == "BUY":
        # M15 MACD histogram positive
        if confirm_ind["macd"]["histogram"] > 0:
            passed += 1
            checks.append("m15_macd_hist_positive")
        # M15 RSI not diverging (above 45)
        if confirm_ind["rsi"]["value"] >= config.RSI_BULL_MIN:
            passed += 1
            checks.append("m15_rsi_aligned")
        # M15 price above EMA50
        if confirm_ind["last_close"] > confirm_ind["ema"]["ema_50"]:
            passed += 1
            checks.append("m15_above_ema50")
    else:
        # M15 MACD histogram negative
        if confirm_ind["macd"]["histogram"] < 0:
            passed += 1
            checks.append("m15_macd_hist_negative")
        # M15 RSI not diverging (below 55)
        if confirm_ind["rsi"]["value"] <= config.RSI_BEAR_MAX:
            passed += 1
            checks.append("m15_rsi_aligned")
        # M15 price below EMA50
        if confirm_ind["last_close"] < confirm_ind["ema"]["ema_50"]:
            passed += 1
            checks.append("m15_below_ema50")

    confirmed = passed >= 2
    if not confirmed:
        checks = [f"m15_rejected({passed}/3)"]

    return confirmed, checks


def evaluate(
    symbol: str,
    ind: dict,
    trend_ind: dict,
    ask: float,
    bid: float,
    confirm_ind: Optional[dict] = None,
    candle_df: Optional[object] = None,
) -> Signal:
    """
    Evaluate bull and bear scores with session weighting, M15 confirmation,
    and candlestick pattern gating. Returns a Signal.
    """
    bull_score, bull_pass, bull_fail = _score_bull(ind, trend_ind)
    bear_score, bear_pass, bear_fail = _score_bear(ind, trend_ind)
    atr = ind["atr"]

    # Apply session weight
    utc_hour = datetime.now(timezone.utc).hour
    session_weight = get_session_weight(utc_hour)
    weighted_bull = round(bull_score * session_weight, 2)
    weighted_bear = round(bear_score * session_weight, 2)

    min_score = config.MIN_SIGNAL_SCORE

    log.info(
        "%s scores — BULL=%.1f (weighted=%.1f) BEAR=%.1f (weighted=%.1f) session_wt=%.2f ATR=%.5f",
        symbol, bull_score, weighted_bull, bear_score, weighted_bear, session_weight, atr,
    )

    direction = None
    raw_score = 0.0
    weighted_score = 0.0
    reasons: List[str] = []
    rejected: List[str] = []

    if weighted_bull >= min_score and weighted_bull > weighted_bear:
        direction = "BUY"
        raw_score = bull_score
        weighted_score = weighted_bull
        reasons = bull_pass
        rejected = bull_fail
    elif weighted_bear >= min_score and weighted_bear > weighted_bull:
        direction = "SELL"
        raw_score = bear_score
        weighted_score = weighted_bear
        reasons = bear_pass
        rejected = bear_fail

    if direction is None:
        return Signal(
            symbol=symbol,
            rejected=[
                f"bull={bull_score:.1f} (wt={weighted_bull:.1f})/7 [{', '.join(bull_fail)}]",
                f"bear={bear_score:.1f} (wt={weighted_bear:.1f})/7 [{', '.join(bear_fail)}]",
            ],
        )

    # M15 confirmation gate
    if confirm_ind is not None:
        confirmed, m15_info = _confirm_m15(confirm_ind, direction)
        reasons.extend(m15_info)
        if not confirmed:
            log.info("%s — M15 confirmation failed for %s", symbol, direction)
            return Signal(
                symbol=symbol,
                rejected=[f"{direction} score={raw_score:.1f} but M15 rejected"] + m15_info,
            )

    # Candlestick pattern gate
    if config.REQUIRE_CANDLE_PATTERN and candle_df is not None:
        import pandas as pd
        if isinstance(candle_df, pd.DataFrame) and len(candle_df) >= 2:
            patterns = detect_patterns(candle_df)
            if has_confirming_pattern(patterns, direction):
                pattern_names = get_pattern_names(patterns, direction)
                reasons.extend(pattern_names)
            else:
                log.info("%s — no confirming candle pattern for %s", symbol, direction)
                return Signal(
                    symbol=symbol,
                    rejected=[f"{direction} score={raw_score:.1f} but no candle pattern"],
                )

    # Compute SL/TP
    sl_dist = atr * config.SL_ATR_MULTIPLIER
    tp_dist = atr * config.TP_ATR_MULTIPLIER
    rr_ratio = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0

    if direction == "BUY":
        entry_price = ask
        sl_price = round(ask - sl_dist, 5)
        tp_price = round(ask + tp_dist, 5)
    else:
        entry_price = bid
        sl_price = round(bid + sl_dist, 5)
        tp_price = round(bid - tp_dist, 5)

    # JPY pairs use pip=0.01, others use pip=0.0001
    pip_size = 0.01 if "JPY" in symbol else 0.0001
    sl_pips = round(sl_dist / pip_size, 1)

    sig = Signal(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        sl_pips=sl_pips,
        sl_price=sl_price,
        tp_price=tp_price,
        rr_ratio=rr_ratio,
        raw_score=raw_score,
        weighted_score=weighted_score,
        reasons=reasons,
        rejected=rejected,
    )

    log.info(
        "%s signal %s — raw=%.1f weighted=%.1f RR=%.2f SL=%.5f TP=%.5f reasons=%s",
        direction, symbol, raw_score, weighted_score, rr_ratio, sl_price, tp_price, reasons,
    )
    return sig
