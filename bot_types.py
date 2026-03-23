"""
types.py — TypedDict definitions and shared type aliases for the bot.
Provides structured typing for indicator results, tick data, account info, etc.
"""
from typing import List, Optional
from typing_extensions import TypedDict


class RSIData(TypedDict):
    value: float
    condition: str           # "overbought" | "oversold" | "neutral"
    divergence: str          # "bullish_hidden" | "bearish_hidden" | "none"


class MACDData(TypedDict):
    macd: float
    signal: float
    histogram: float
    cross: str               # "bullish" | "bearish"


class BollingerData(TypedDict):
    upper: float
    mid: float
    lower: float
    price_position: str      # "above_upper" | "below_lower" | "inside"


class IchimokuData(TypedDict):
    tenkan: float
    kijun: float
    senkou_a: float
    senkou_b: float
    cloud_position: str      # "above_cloud" | "below_cloud" | "inside_cloud"
    tk_cross: str            # "bullish" | "bearish"


class EMAData(TypedDict):
    ema_50: float
    ema_100: float
    ema_200: float
    trend: str               # "strong_bullish" | "strong_bearish" | "mixed"


class SupportResistance(TypedDict):
    recent_high: float
    recent_low: float


class IndicatorResult(TypedDict):
    symbol: str
    timeframe: str
    last_close: float
    rsi: RSIData
    macd: MACDData
    bollinger: BollingerData
    ichimoku: IchimokuData
    ema: EMAData
    atr: float
    atr_pips: float
    atr_percentile: float
    support_resistance: SupportResistance


class TickData(TypedDict):
    symbol: str
    bid: float
    ask: float
    spread_pips: float
    time: str


class AccountInfo(TypedDict):
    login: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float
    profit: float
    currency: str
    leverage: int


class PositionInfo(TypedDict):
    ticket: int
    symbol: str
    type: str                # "BUY" | "SELL"
    volume: float
    open_price: float
    sl: float
    tp: float
    profit: float
    swap: float
    comment: str
    open_time: str


class PositionsResult(TypedDict):
    positions: List[PositionInfo]
    count: int


class TradeResult(TypedDict, total=False):
    success: bool
    ticket: int
    price: float
    lot_size: float
    sl: float
    tp: float
    retcode: int
    error: str
    profit: float


class CandleData(TypedDict):
    symbol: str
    timeframe: str
    candles_fetched: int
    last_close: float
    last_20_closes: List[float]
    last_20_highs: List[float]
    last_20_lows: List[float]
    last_20_volumes: List[int]
    period_high: float
    period_low: float
    timestamp: str


class TradeSummary(TypedDict):
    total_closed: int
    wins: int
    losses: int
    win_rate_pct: float
    total_profit: float


class TradeRecord(TypedDict, total=False):
    id: int
    ticket: int
    symbol: str
    direction: str
    lot_size: float
    entry_price: float
    sl: float
    tp: float
    comment: str
    open_time: str
    close_time: Optional[str]
    close_price: Optional[float]
    profit: Optional[float]
    status: str


class ErrorResult(TypedDict):
    error: str
