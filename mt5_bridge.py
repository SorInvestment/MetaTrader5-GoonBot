"""
mt5_bridge.py — All MetaTrader 5 API interactions.
Nothing else imports MetaTrader5 directly.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd

import config
import indicators

log = logging.getLogger(__name__)

MAGIC: int = 202500  # unique magic number stamped on all bot orders

TF_MAP: dict = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
}


def connect() -> bool:
    """Initialise MT5 terminal and optionally log in."""
    if config.MT5_PATH:
        ok = mt5.initialize(path=config.MT5_PATH)
    else:
        ok = mt5.initialize()

    if not ok:
        log.error("MT5 initialize failed: %s", mt5.last_error())
        return False

    if config.MT5_LOGIN:
        logged = mt5.login(
            login=config.MT5_LOGIN,
            password=config.MT5_PASSWORD,
            server=config.MT5_SERVER,
        )
        if not logged:
            log.error("MT5 login failed: %s", mt5.last_error())
            return False

    info = mt5.account_info()
    if info:
        log.info("MT5 connected — account #%s, balance=%.2f %s",
                 info.login, info.balance, info.currency)
    return True


def disconnect() -> None:
    """Shut down MT5 connection."""
    mt5.shutdown()
    log.info("MT5 disconnected")


def get_candles(symbol: str, timeframe: str = "H1", count: int = 200) -> dict:
    """Fetch OHLCV candles from MT5."""
    tf = TF_MAP.get(timeframe)
    if tf is None:
        return {"error": f"Unknown timeframe: {timeframe}"}

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        return {"error": f"No candle data for {symbol} {timeframe}: {mt5.last_error()}"}

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles_fetched": len(df),
        "last_close": round(float(df["close"].iloc[-1]), 5),
        "last_20_closes": [round(float(c), 5) for c in df["close"].iloc[-20:]],
        "last_20_highs": [round(float(h), 5) for h in df["high"].iloc[-20:]],
        "last_20_lows": [round(float(l), 5) for l in df["low"].iloc[-20:]],
        "last_20_volumes": [int(v) for v in df["tick_volume"].iloc[-20:]],
        "period_high": round(float(df["high"].max()), 5),
        "period_low": round(float(df["low"].min()), 5),
        "timestamp": str(df["time"].iloc[-1]),
    }


def get_indicators(symbol: str, timeframe: str = "H1", count: int = 200) -> dict:
    """Fetch candles and compute all indicators."""
    tf = TF_MAP.get(timeframe)
    if tf is None:
        return {"error": f"Unknown timeframe: {timeframe}"}

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        return {"error": f"No data for {symbol} {timeframe}: {mt5.last_error()}"}

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.rename(columns={"tick_volume": "tick_volume"}, inplace=True)

    return indicators.compute_indicators(df, symbol, timeframe)


def get_tick(symbol: str) -> dict:
    """Get current bid/ask tick and spread in pips."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"error": f"No tick for {symbol}: {mt5.last_error()}"}

    info = mt5.symbol_info(symbol)
    if info is None:
        return {"error": f"No symbol info for {symbol}: {mt5.last_error()}"}

    point = info.point
    spread_pips = round((tick.ask - tick.bid) / point / 10, 2)

    return {
        "symbol": symbol,
        "bid": round(tick.bid, 5),
        "ask": round(tick.ask, 5),
        "spread_pips": spread_pips,
        "time": datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
    }


def get_account_info() -> dict:
    """Return account balance, equity, margin info."""
    info = mt5.account_info()
    if info is None:
        return {"error": f"No account info: {mt5.last_error()}"}

    return {
        "login": info.login,
        "balance": round(info.balance, 2),
        "equity": round(info.equity, 2),
        "margin": round(info.margin, 2),
        "free_margin": round(info.margin_free, 2),
        "margin_level": round(info.margin_level, 2) if info.margin_level else 0.0,
        "profit": round(info.profit, 2),
        "currency": info.currency,
        "leverage": info.leverage,
    }


def get_positions() -> dict:
    """Get all open positions."""
    positions = mt5.positions_get()
    if positions is None:
        return {"positions": [], "count": 0}

    result = []
    for p in positions:
        result.append({
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": p.volume,
            "open_price": round(p.price_open, 5),
            "sl": round(p.sl, 5),
            "tp": round(p.tp, 5),
            "profit": round(p.profit, 2),
            "swap": round(p.swap, 2),
            "comment": p.comment,
            "open_time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
        })

    return {"positions": result, "count": len(result)}


def calculate_lot_size(symbol: str, sl_pips: float, risk_pct: Optional[float] = None) -> float:
    """Calculate position size based on risk percentage and SL distance."""
    risk_pct = risk_pct or config.RISK_PER_TRADE_PCT

    acct = mt5.account_info()
    if acct is None:
        log.error("Cannot get account info for lot calc")
        return 0.01

    info = mt5.symbol_info(symbol)
    if info is None:
        log.error("Cannot get symbol info for %s", symbol)
        return 0.01

    balance = acct.balance
    risk_amount = balance * (risk_pct / 100.0)
    point = info.point
    tick_value = info.trade_tick_value

    if tick_value <= 0 or point <= 0 or sl_pips <= 0:
        log.warning("Invalid values for lot calc — tick_value=%.5f point=%.5f sl_pips=%.1f",
                     tick_value, point, sl_pips)
        return 0.01

    pip_value = tick_value * (0.0001 / point)
    if pip_value <= 0:
        log.warning("pip_value <= 0, defaulting to min lot")
        return 0.01

    lot = risk_amount / (sl_pips * pip_value)
    lot = max(info.volume_min, min(lot, info.volume_max))
    lot = round(lot, 2)

    log.info("Lot calc: balance=%.2f risk=%.2f sl_pips=%.1f pip_val=%.4f -> %.2f lots",
             balance, risk_amount, sl_pips, pip_value, lot)
    return lot


def execute_trade(
    symbol: str,
    direction: str,
    lot_size: float,
    sl_price: float,
    tp_price: float,
    comment: str = "rule_bot",
) -> dict:
    """Execute a market order."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"success": False, "error": f"No tick: {mt5.last_error()}"}

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type,
        "price": price,
        "sl": round(sl_price, 5),
        "tp": round(tp_price, 5),
        "deviation": 20,
        "magic": MAGIC,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"success": False, "error": f"order_send returned None: {mt5.last_error()}"}

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {
            "success": False,
            "retcode": result.retcode,
            "error": f"Order failed: {result.comment}",
        }

    log.info("Trade executed — %s %s %.2f lots @ %.5f  SL=%.5f  TP=%.5f  ticket=%s",
             direction, symbol, lot_size, result.price, sl_price, tp_price, result.order)

    return {
        "success": True,
        "ticket": result.order,
        "price": round(result.price, 5),
        "lot_size": lot_size,
        "sl": round(sl_price, 5),
        "tp": round(tp_price, 5),
    }


def close_position(ticket: int, reason: str = "") -> dict:
    """Close a position by sending a reverse market order."""
    positions = mt5.positions_get(ticket=ticket)
    if positions is None or len(positions) == 0:
        return {"success": False, "error": f"Position {ticket} not found"}

    pos = positions[0]
    symbol = pos.symbol
    volume = pos.volume

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"success": False, "error": f"No tick for {symbol}"}

    if pos.type == mt5.ORDER_TYPE_BUY:
        close_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        close_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": close_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": MAGIC,
        "comment": f"close_{reason}" if reason else "close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"success": False, "error": f"Close order_send None: {mt5.last_error()}"}

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"success": False, "error": f"Close failed: {result.comment}"}

    log.info("Position closed — ticket=%s  profit=%.2f  reason=%s", ticket, pos.profit, reason)
    return {"success": True, "ticket": ticket, "profit": round(pos.profit, 2)}


def modify_sl_tp(ticket: int, new_sl: float, new_tp: float) -> dict:
    """Modify stop loss and take profit of an open position."""
    positions = mt5.positions_get(ticket=ticket)
    if positions is None or len(positions) == 0:
        return {"success": False, "error": f"Position {ticket} not found"}

    pos = positions[0]

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": ticket,
        "sl": round(new_sl, 5),
        "tp": round(new_tp, 5),
    }

    result = mt5.order_send(request)
    if result is None:
        return {"success": False, "error": f"Modify returned None: {mt5.last_error()}"}

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"success": False, "error": f"Modify failed: {result.comment}"}

    log.info("SL/TP modified — ticket=%s  SL=%.5f  TP=%.5f", ticket, new_sl, new_tp)
    return {
        "success": True,
        "ticket": ticket,
        "sl": round(new_sl, 5),
        "tp": round(new_tp, 5),
    }
