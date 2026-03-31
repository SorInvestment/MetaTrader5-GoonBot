#!/usr/bin/env python3
"""
launch_bot.py — Launch the bot with a simulated MT5 connection.

MetaTrader5 is Windows-only. This launcher injects a realistic mock that
simulates live market data so the bot can run its full cycle on Linux.
It generates random-walk price data per symbol and returns realistic
indicator values so signals, risk management, and all features are exercised.

Usage:
    python launch_bot.py --dry-run          # signals only, no fake trades
    python launch_bot.py                    # simulated trade execution
    python launch_bot.py --once             # single cycle then exit
    python launch_bot.py --once --dry-run   # single dry-run cycle
"""
import sys
import random
import time
import numpy as np
import pandas as pd
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Simulated market state
# ---------------------------------------------------------------------------
_PRICES = {
    "USDJPY": {"bid": 149.850, "ask": 149.853, "digits": 3, "point": 0.001},
    "EURJPY": {"bid": 162.340, "ask": 162.345, "digits": 3, "point": 0.001},
    "GBPJPY": {"bid": 188.920, "ask": 188.927, "digits": 3, "point": 0.001},
}

_TICK_VALUES = {"USDJPY": 6.68, "EURJPY": 6.68, "GBPJPY": 6.68}
_OPEN_POSITIONS = {}  # ticket -> position dict
_NEXT_TICKET = [100001]


def _jitter(price, pips=5):
    """Add small random jitter to simulate price movement."""
    point = 0.001 if price > 50 else 0.00001
    return round(price + random.uniform(-pips, pips) * point, 5)


def _generate_candles(symbol, timeframe_val, count=250):
    """Generate a realistic OHLCV DataFrame for the symbol."""
    np.random.seed(hash(symbol + str(timeframe_val)) % (2**31))
    base = _PRICES[symbol]["bid"]

    returns = np.random.normal(0.0001, 0.003, count)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + np.abs(np.random.normal(0, 0.002, count)))
    low = close * (1 - np.abs(np.random.normal(0, 0.002, count)))
    open_ = close + np.random.normal(0, 0.1, count)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    now = datetime.now(timezone.utc)
    freq_map = {1: "1min", 5: "5min", 15: "15min", 30: "30min",
                16385: "1h", 16388: "4h", 16408: "1D"}
    freq = freq_map.get(timeframe_val, "1h")

    times = pd.date_range(end=now, periods=count, freq=freq)

    # Return structured array matching MT5's copy_rates_from_pos format
    dtype = np.dtype([
        ("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
        ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8"),
    ])
    arr = np.empty(count, dtype=dtype)
    arr["time"] = np.array([int(t.timestamp()) for t in times])
    arr["open"] = np.round(open_, 3)
    arr["high"] = np.round(high, 3)
    arr["low"] = np.round(low, 3)
    arr["close"] = np.round(close, 3)
    arr["tick_volume"] = np.random.randint(500, 5000, count)
    arr["spread"] = 3
    arr["real_volume"] = 0
    return arr


# ---------------------------------------------------------------------------
# Build mock MT5 module
# ---------------------------------------------------------------------------
mock_mt5 = MagicMock()

# Constants
mock_mt5.TIMEFRAME_M1 = 1
mock_mt5.TIMEFRAME_M5 = 5
mock_mt5.TIMEFRAME_M15 = 15
mock_mt5.TIMEFRAME_M30 = 30
mock_mt5.TIMEFRAME_H1 = 16385
mock_mt5.TIMEFRAME_H4 = 16388
mock_mt5.TIMEFRAME_D1 = 16408
mock_mt5.TIMEFRAME_W1 = 32769
mock_mt5.ORDER_TYPE_BUY = 0
mock_mt5.ORDER_TYPE_SELL = 1
mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
mock_mt5.TRADE_ACTION_DEAL = 1
mock_mt5.TRADE_ACTION_PENDING = 5
mock_mt5.TRADE_ACTION_SLTP = 6
mock_mt5.TRADE_ACTION_REMOVE = 8
mock_mt5.TRADE_RETCODE_DONE = 10009
mock_mt5.ORDER_FILLING_IOC = 1
mock_mt5.ORDER_TIME_GTC = 0


def mock_initialize(**kwargs):
    return True

def mock_login(**kwargs):
    return True

def mock_shutdown():
    pass

def mock_last_error():
    return (0, "OK")

def mock_account_info():
    acct = MagicMock()
    acct.login = 5048716399
    acct.balance = 10000.0
    acct.equity = 10000.0 + sum(p.get("profit", 0) for p in _OPEN_POSITIONS.values())
    acct.margin = sum(p.get("margin", 100) for p in _OPEN_POSITIONS.values())
    acct.margin_free = acct.equity - acct.margin
    acct.margin_level = (acct.equity / acct.margin * 100) if acct.margin > 0 else 0
    acct.profit = acct.equity - 10000.0
    acct.currency = "USD"
    acct.leverage = 100
    return acct


def mock_symbol_info(symbol):
    if symbol not in _PRICES:
        return None
    info = MagicMock()
    info.point = _PRICES[symbol]["point"]
    info.digits = _PRICES[symbol]["digits"]
    info.trade_tick_value = _TICK_VALUES.get(symbol, 6.68)
    info.volume_min = 0.01
    info.volume_max = 100.0
    info.volume_step = 0.01
    info.spread = 3
    return info


def mock_symbol_info_tick(symbol):
    if symbol not in _PRICES:
        return None
    # Simulate price movement
    p = _PRICES[symbol]
    p["bid"] = _jitter(p["bid"], 3)
    p["ask"] = p["bid"] + p["point"] * random.randint(1, 5)

    tick = MagicMock()
    tick.bid = round(p["bid"], 5)
    tick.ask = round(p["ask"], 5)
    tick.time = int(time.time())
    return tick


def mock_copy_rates_from_pos(symbol, timeframe, start_pos, count):
    return _generate_candles(symbol, timeframe, count)


def mock_positions_get(**kwargs):
    symbol = kwargs.get("symbol")
    positions = list(_OPEN_POSITIONS.values())
    if symbol:
        positions = [p for p in positions if p["_symbol"] == symbol]

    result = []
    for p in positions:
        pos = MagicMock()
        pos.ticket = p["ticket"]
        pos.symbol = p["_symbol"]
        pos.type = 0 if p["_direction"] == "BUY" else 1
        pos.volume = p["volume"]
        pos.price_open = p["open_price"]
        pos.sl = p["sl"]
        pos.tp = p["tp"]
        pos.profit = p.get("profit", 0)
        pos.magic = 202500
        pos.comment = p.get("comment", "rule_bot")
        pos.time = int(time.time()) - 3600
        result.append(pos)

    return result if result else None


def mock_order_send(request):
    result = MagicMock()
    result.retcode = 10009  # TRADE_RETCODE_DONE

    action = request.get("action")

    if action == 1:  # TRADE_ACTION_DEAL
        if "position" in request:
            # Close/partial close
            ticket = request["position"]
            if ticket in _OPEN_POSITIONS:
                close_vol = request["volume"]
                pos = _OPEN_POSITIONS[ticket]
                remaining = round(pos["volume"] - close_vol, 2)
                if remaining <= 0.005:
                    del _OPEN_POSITIONS[ticket]
                    remaining = 0.0
                else:
                    pos["volume"] = remaining
                result.volume = close_vol
                result.price = _PRICES.get(pos["_symbol"], {}).get("bid", 150.0)
                result.order = ticket
                result.comment = "closed"
            else:
                result.retcode = 10013
                result.comment = "position not found"
        else:
            # New market order
            ticket = _NEXT_TICKET[0]
            _NEXT_TICKET[0] += 1
            symbol = request["symbol"]
            direction = "BUY" if request["type"] == 0 else "SELL"
            price = _PRICES[symbol]["ask"] if direction == "BUY" else _PRICES[symbol]["bid"]

            _OPEN_POSITIONS[ticket] = {
                "ticket": ticket,
                "_symbol": symbol,
                "_direction": direction,
                "volume": request["volume"],
                "open_price": round(price, 5),
                "sl": request.get("sl", 0),
                "tp": request.get("tp", 0),
                "profit": 0.0,
                "margin": 100.0,
                "comment": request.get("comment", ""),
            }
            result.order = ticket
            result.price = round(price, 5)
            result.volume = request["volume"]

    elif action == 5:  # TRADE_ACTION_PENDING (limit order)
        ticket = _NEXT_TICKET[0]
        _NEXT_TICKET[0] += 1
        result.order = ticket
        result.price = request.get("price", 0)
        result.volume = request.get("volume", 0)

    elif action == 6:  # TRADE_ACTION_SLTP
        ticket = request.get("position")
        if ticket in _OPEN_POSITIONS:
            _OPEN_POSITIONS[ticket]["sl"] = request.get("sl", 0)
            _OPEN_POSITIONS[ticket]["tp"] = request.get("tp", 0)
        result.order = ticket

    elif action == 8:  # TRADE_ACTION_REMOVE
        result.order = request.get("order", 0)

    return result


def mock_order_calc_margin(order_type, symbol, volume, price):
    # ~$100 per 0.01 lot for JPY pairs at 1:100 leverage
    return round(volume * 10000 * price / 100, 2) if symbol in _PRICES else None


def mock_orders_get(**kwargs):
    return None  # No pending orders in sim


def mock_history_deals_get(*args, **kwargs):
    return None


# Wire up the mock
mock_mt5.initialize = mock_initialize
mock_mt5.login = mock_login
mock_mt5.shutdown = mock_shutdown
mock_mt5.last_error = mock_last_error
mock_mt5.account_info = mock_account_info
mock_mt5.symbol_info = mock_symbol_info
mock_mt5.symbol_info_tick = mock_symbol_info_tick
mock_mt5.copy_rates_from_pos = mock_copy_rates_from_pos
mock_mt5.positions_get = mock_positions_get
mock_mt5.order_send = mock_order_send
mock_mt5.order_calc_margin = mock_order_calc_margin
mock_mt5.orders_get = mock_orders_get
mock_mt5.history_deals_get = mock_history_deals_get

# Inject before any bot code imports
sys.modules["MetaTrader5"] = mock_mt5

# ---------------------------------------------------------------------------
# Now launch the real bot
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  MT5 GoonBot — Simulated Market Launch")
    print("  MetaTrader5 is Windows-only; using realistic mock data")
    print("  Account: 5048716399 (MetaQuotes-Demo simulated)")
    print("=" * 60)
    print()

    import main
    main.main()
