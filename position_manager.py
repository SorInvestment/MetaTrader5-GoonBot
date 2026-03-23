"""
position_manager.py — Breakeven, trailing stop, scaling out, and risk guards.
Uses mt5_bridge for all MT5 interactions.
"""
import logging
from typing import Set

import config
import logger as trade_logger
import mt5_bridge as mt5b
from correlation import check_correlated_exposure
from notifier import notify, notify_trade

log = logging.getLogger(__name__)

# Track tickets that have already been scaled out (cleared on restart)
_scaled_tickets: Set[int] = set()


def already_open(symbol: str) -> bool:
    """Return True if there is already an open position for the symbol."""
    data = mt5b.get_positions()
    count = sum(1 for p in data["positions"] if p["symbol"] == symbol)
    return count >= config.MAX_TRADES_PER_SYMBOL


def drawdown_ok() -> bool:
    """Return False (and log warning) if equity drawdown exceeds threshold."""
    acct = mt5b.get_account_info()
    if "error" in acct:
        log.error("Cannot check drawdown: %s", acct["error"])
        return False

    balance = acct["balance"]
    equity = acct["equity"]

    if balance <= 0:
        return False

    dd_pct = (1 - equity / balance) * 100
    if dd_pct >= config.MAX_DRAWDOWN_PCT:
        log.warning("Drawdown guard triggered: %.2f%% >= %.2f%%", dd_pct, config.MAX_DRAWDOWN_PCT)
        notify(f"Drawdown guard: {dd_pct:.2f}% >= {config.MAX_DRAWDOWN_PCT}%", level="warning")
        return False
    return True


def max_trades_ok() -> bool:
    """Return False if open positions >= MAX_OPEN_TRADES."""
    data = mt5b.get_positions()
    if data["count"] >= config.MAX_OPEN_TRADES:
        log.info("Max trades reached: %d/%d", data["count"], config.MAX_OPEN_TRADES)
        return False
    return True


def spread_ok(symbol: str) -> bool:
    """Return False if current spread exceeds SPREAD_LIMIT_PIPS."""
    tick = mt5b.get_tick(symbol)
    if "error" in tick:
        log.error("Cannot check spread for %s: %s", symbol, tick["error"])
        return False

    if tick["spread_pips"] > config.SPREAD_LIMIT_PIPS:
        log.info("Spread too wide for %s: %.2f > %.2f pips",
                 symbol, tick["spread_pips"], config.SPREAD_LIMIT_PIPS)
        return False
    return True


def daily_loss_ok() -> bool:
    """Return False if today's realised losses exceed the daily limit."""
    acct = mt5b.get_account_info()
    if "error" in acct:
        return False

    daily_pnl = trade_logger.get_daily_pnl()
    limit = acct["balance"] * (config.DAILY_LOSS_LIMIT_PCT / 100.0)

    if daily_pnl < 0 and abs(daily_pnl) >= limit:
        log.warning("Daily loss limit hit: %.2f >= %.2f", abs(daily_pnl), limit)
        notify(f"Daily loss limit: {abs(daily_pnl):.2f} >= {limit:.2f}", level="warning")
        return False
    return True


def volatility_ok(ind: dict) -> bool:
    """Return False if ATR percentile is outside acceptable range."""
    pct = ind.get("atr_percentile", 50.0)
    if pct < config.ATR_LOW_PERCENTILE:
        log.info("Volatility too low: ATR percentile=%.1f < %.1f", pct, config.ATR_LOW_PERCENTILE)
        return False
    if pct > config.ATR_HIGH_PERCENTILE:
        log.info("Volatility too high: ATR percentile=%.1f > %.1f", pct, config.ATR_HIGH_PERCENTILE)
        return False
    return True


def correlation_ok(symbol: str, direction: str) -> bool:
    """Return False if adding this trade would exceed correlated exposure limits."""
    data = mt5b.get_positions()
    return not check_correlated_exposure(data["positions"], symbol, direction)


def calculate_new_sl(
    direction: str,
    open_price: float,
    current_sl: float,
    current_price: float,
    atr: float,
    profit_r: float,
) -> float:
    """
    Pure function to calculate new SL based on breakeven and trailing logic.
    Returns the new SL, or current_sl if no change needed.
    Used by both live position manager and backtester.
    """
    new_sl = current_sl

    # Trailing stop logic (higher priority — check first)
    if profit_r >= config.TRAIL_TRIGGER_R:
        trail_dist = atr * config.TRAIL_ATR_MULT
        if direction == "BUY":
            candidate = round(current_price - trail_dist, 5)
            if candidate > current_sl:
                new_sl = candidate
        else:
            candidate = round(current_price + trail_dist, 5)
            if candidate < current_sl:
                new_sl = candidate

    # Breakeven logic (only if trail hasn't already moved SL)
    elif profit_r >= config.BREAKEVEN_TRIGGER_R:
        buffer = atr * 0.1
        if direction == "BUY" and current_sl < open_price:
            new_sl = round(open_price + buffer, 5)
        elif direction == "SELL" and current_sl > open_price:
            new_sl = round(open_price - buffer, 5)

    return new_sl


def manage_open_positions() -> None:
    """Check all open positions for scale-out, breakeven, and trailing stop adjustments."""
    data = mt5b.get_positions()
    if data["count"] == 0:
        return

    for pos in data["positions"]:
        ticket = pos["ticket"]
        symbol = pos["symbol"]
        direction = pos["type"]
        open_price = pos["open_price"]
        current_sl = pos["sl"]
        current_tp = pos["tp"]
        volume = pos["volume"]

        # Skip positions without SL (not managed by us)
        if current_sl == 0:
            continue

        r_distance = abs(open_price - current_sl)
        if r_distance == 0:
            continue

        # Get current price
        tick = mt5b.get_tick(symbol)
        if "error" in tick:
            log.error("Cannot get tick for %s: %s", symbol, tick["error"])
            continue

        if direction == "BUY":
            current_price = tick["bid"]
            current_profit_r = (current_price - open_price) / r_distance
        else:
            current_price = tick["ask"]
            current_profit_r = (open_price - current_price) / r_distance

        # Get ATR for trail distance
        ind = mt5b.get_indicators(symbol, config.ENTRY_TF)
        if "error" in ind:
            log.error("Cannot get indicators for %s: %s", symbol, ind["error"])
            continue

        atr = ind["atr"]

        # --- Scale out logic ---
        if (
            ticket not in _scaled_tickets
            and current_profit_r >= config.SCALE_OUT_AT_R
            and volume > 0.02  # need enough volume to split
        ):
            close_vol = round(volume * config.SCALE_OUT_PCT, 2)
            if close_vol >= 0.01:
                result = mt5b.partial_close(ticket, close_vol, "scale_out")
                if result.get("success"):
                    _scaled_tickets.add(ticket)
                    remaining = result["remaining_volume"]
                    trade_logger.log_partial_close(ticket, close_vol, remaining, 0.0)
                    notify_trade("scale_out", symbol, direction, current_price,
                                 current_sl, current_tp, lot_size=close_vol)
                    log.info("Scaled out %s ticket=%s — closed %.2f, remaining %.2f",
                             symbol, ticket, close_vol, remaining)
                else:
                    log.error("Scale out failed for ticket=%s: %s", ticket, result.get("error"))

        # --- Breakeven and trailing stop ---
        new_sl = calculate_new_sl(direction, open_price, current_sl, current_price, atr, current_profit_r)

        if new_sl != current_sl:
            # Determine action type for logging
            if current_profit_r >= config.TRAIL_TRIGGER_R and new_sl != current_sl:
                action = "trail"
            else:
                action = "breakeven"

            result = mt5b.modify_sl_tp(ticket, new_sl, current_tp)
            if result["success"]:
                log.info("%s %s %s ticket=%s — new_sl=%.5f (profit=%.1fR)",
                         action.capitalize(), direction, symbol, ticket, new_sl, current_profit_r)
                notify_trade(action, symbol, direction, current_price, new_sl, current_tp)
            else:
                log.error("Failed to modify SL for ticket=%s: %s", ticket, result["error"])
