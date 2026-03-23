"""
position_manager.py — Breakeven, trailing stop, risk guards.
Uses mt5_bridge for all MT5 interactions.
"""
import logging

import config
import mt5_bridge as mt5b

log = logging.getLogger(__name__)


def already_open(symbol: str) -> bool:
    """Return True if there is already an open position for the symbol."""
    data = mt5b.get_positions()
    for pos in data["positions"]:
        if pos["symbol"] == symbol:
            return True
    return False


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


def manage_open_positions() -> None:
    """Check all open positions for breakeven and trailing stop adjustments."""
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
        new_sl = current_sl

        # Trailing stop logic (check first — higher priority)
        if current_profit_r >= config.TRAIL_TRIGGER_R:
            trail_dist = atr * config.TRAIL_ATR_MULT
            if direction == "BUY":
                candidate = round(current_price - trail_dist, 5)
                if candidate > current_sl:
                    new_sl = candidate
                    log.info("Trail BUY %s ticket=%s — new_sl=%.5f (profit=%.1fR)",
                             symbol, ticket, new_sl, current_profit_r)
            else:
                candidate = round(current_price + trail_dist, 5)
                if candidate < current_sl:
                    new_sl = candidate
                    log.info("Trail SELL %s ticket=%s — new_sl=%.5f (profit=%.1fR)",
                             symbol, ticket, new_sl, current_profit_r)

        # Breakeven logic (only if trail hasn't already moved SL)
        elif current_profit_r >= config.BREAKEVEN_TRIGGER_R:
            buffer = atr * 0.1
            if direction == "BUY" and current_sl < open_price:
                new_sl = round(open_price + buffer, 5)
                log.info("Breakeven BUY %s ticket=%s — new_sl=%.5f",
                         symbol, ticket, new_sl)
            elif direction == "SELL" and current_sl > open_price:
                new_sl = round(open_price - buffer, 5)
                log.info("Breakeven SELL %s ticket=%s — new_sl=%.5f",
                         symbol, ticket, new_sl)

        # Apply modification if SL changed
        if new_sl != current_sl:
            result = mt5b.modify_sl_tp(ticket, new_sl, current_tp)
            if not result["success"]:
                log.error("Failed to modify SL for ticket=%s: %s", ticket, result["error"])
