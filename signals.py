"""
signals.py — 7-point signal scoring engine.
Pure logic — no I/O, no MT5 imports.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import config

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


def evaluate(symbol: str, ind: dict, trend_ind: dict, ask: float, bid: float) -> Signal:
    """Evaluate bull and bear scores and return a Signal."""
    bull_score, bull_pass, bull_fail = _score_bull(ind, trend_ind)
    bear_score, bear_pass, bear_fail = _score_bear(ind, trend_ind)
    atr = ind["atr"]

    log.info(
        "%s scores — BULL=%.1f/7 BEAR=%.1f/7  ATR=%.5f",
        symbol, bull_score, bear_score, atr,
    )

    if bull_score >= 5.0 and bull_score > bear_score:
        sl_dist = atr * config.SL_ATR_MULTIPLIER
        tp_dist = atr * config.TP_ATR_MULTIPLIER
        sl_price = round(ask - sl_dist, 5)
        tp_price = round(ask + tp_dist, 5)
        sl_pips = round(sl_dist / 0.001, 1)
        rr_ratio = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0

        sig = Signal(
            symbol=symbol,
            direction="BUY",
            entry_price=ask,
            sl_pips=sl_pips,
            sl_price=sl_price,
            tp_price=tp_price,
            rr_ratio=rr_ratio,
            reasons=bull_pass,
            rejected=bull_fail,
        )
        log.info(
            "BUY signal %s — score=%.1f RR=%.2f SL=%.5f TP=%.5f reasons=%s",
            symbol, bull_score, rr_ratio, sl_price, tp_price, bull_pass,
        )
        return sig

    elif bear_score >= 5.0 and bear_score > bull_score:
        sl_dist = atr * config.SL_ATR_MULTIPLIER
        tp_dist = atr * config.TP_ATR_MULTIPLIER
        sl_price = round(bid + sl_dist, 5)
        tp_price = round(bid - tp_dist, 5)
        sl_pips = round(sl_dist / 0.001, 1)
        rr_ratio = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0.0

        sig = Signal(
            symbol=symbol,
            direction="SELL",
            entry_price=bid,
            sl_pips=sl_pips,
            sl_price=sl_price,
            tp_price=tp_price,
            rr_ratio=rr_ratio,
            reasons=bear_pass,
            rejected=bear_fail,
        )
        log.info(
            "SELL signal %s — score=%.1f RR=%.2f SL=%.5f TP=%.5f reasons=%s",
            symbol, bear_score, rr_ratio, sl_price, tp_price, bear_pass,
        )
        return sig

    else:
        sig = Signal(
            symbol=symbol,
            rejected=[
                f"bull={bull_score:.1f}/7 [{', '.join(bull_fail)}]",
                f"bear={bear_score:.1f}/7 [{', '.join(bear_fail)}]",
            ],
        )
        log.info("No signal %s — bull=%.1f bear=%.1f", symbol, bull_score, bear_score)
        return sig
