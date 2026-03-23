"""
indicators.py — Pure pandas/numpy technical indicator calculations.
No MT5 imports. Receives a DataFrame, returns a structured dict.
"""
import logging
from typing import Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Standard Wilder RSI using rolling mean of gains/losses."""
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()


def _macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, and histogram."""
    macd_line = _ema(series, fast) - _ema(series, slow)
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _bollinger(
    series: pd.Series, period: int = 20, std_dev: int = 2
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands: upper, middle, lower."""
    mid = series.rolling(period).mean()
    sigma = series.rolling(period).std()
    return mid + std_dev * sigma, mid, mid - std_dev * sigma


def _ichimoku(
    df: pd.DataFrame,
) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Ichimoku Cloud: tenkan, kijun, senkou_a, senkou_b, chikou."""
    def midpoint(high: pd.Series, low: pd.Series, period: int) -> pd.Series:
        return (high.rolling(period).max() + low.rolling(period).min()) / 2

    tenkan = midpoint(df["high"], df["low"], 9)
    kijun = midpoint(df["high"], df["low"], 26)
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = midpoint(df["high"], df["low"], 52).shift(26)
    chikou = df["close"].shift(-26)
    return tenkan, kijun, senkou_a, senkou_b, chikou


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def compute_indicators(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    """Compute all indicators and return a structured dict."""
    close = df["close"]
    last_close = round(float(close.iloc[-1]), 5)

    # RSI
    rsi_series = _rsi(close)
    rsi_val = round(float(rsi_series.iloc[-1]), 2)
    if rsi_val >= 70:
        rsi_cond = "overbought"
    elif rsi_val <= 30:
        rsi_cond = "oversold"
    else:
        rsi_cond = "neutral"

    # RSI divergence over last 3 bars
    rsi_last3 = rsi_series.iloc[-3:]
    close_last3 = close.iloc[-3:]
    rsi_dir = rsi_last3.iloc[-1] - rsi_last3.iloc[0]
    price_dir = close_last3.iloc[-1] - close_last3.iloc[0]
    if rsi_dir > 0 and price_dir < 0:
        rsi_div = "bullish_hidden"
    elif rsi_dir < 0 and price_dir > 0:
        rsi_div = "bearish_hidden"
    else:
        rsi_div = "none"

    # MACD
    macd_line, signal_line, histogram = _macd(close)
    macd_val = round(float(macd_line.iloc[-1]), 5)
    signal_val = round(float(signal_line.iloc[-1]), 5)
    hist_val = round(float(histogram.iloc[-1]), 5)
    macd_cross = "bullish" if macd_val > signal_val else "bearish"

    # Bollinger
    bb_upper, bb_mid, bb_lower = _bollinger(close)
    bb_u = round(float(bb_upper.iloc[-1]), 5)
    bb_m = round(float(bb_mid.iloc[-1]), 5)
    bb_l = round(float(bb_lower.iloc[-1]), 5)
    if last_close > bb_u:
        bb_pos = "above_upper"
    elif last_close < bb_l:
        bb_pos = "below_lower"
    else:
        bb_pos = "inside"

    # Ichimoku
    tenkan, kijun, senkou_a, senkou_b, chikou = _ichimoku(df)
    tenkan_val = round(float(tenkan.iloc[-1]), 5)
    kijun_val = round(float(kijun.iloc[-1]), 5)
    # senkou values are shifted forward, use current index
    sa_val = round(float(senkou_a.iloc[-1]), 5) if not np.isnan(senkou_a.iloc[-1]) else 0.0
    sb_val = round(float(senkou_b.iloc[-1]), 5) if not np.isnan(senkou_b.iloc[-1]) else 0.0

    cloud_top = max(sa_val, sb_val)
    cloud_bot = min(sa_val, sb_val)
    if last_close > cloud_top:
        cloud_pos = "above_cloud"
    elif last_close < cloud_bot:
        cloud_pos = "below_cloud"
    else:
        cloud_pos = "inside_cloud"

    tk_cross = "bullish" if tenkan_val > kijun_val else "bearish"

    # EMA
    ema50 = round(float(_ema(close, 50).iloc[-1]), 5)
    ema100 = round(float(_ema(close, 100).iloc[-1]), 5)
    ema200 = round(float(_ema(close, 200).iloc[-1]), 5)

    if last_close > ema50 > ema100 > ema200:
        ema_trend = "strong_bullish"
    elif last_close < ema50 < ema100 < ema200:
        ema_trend = "strong_bearish"
    else:
        ema_trend = "mixed"

    # ATR
    atr_series = _atr(df)
    atr_val = round(float(atr_series.iloc[-1]), 5)
    atr_pips = round(atr_val / 0.001, 2)

    # Support/Resistance
    recent_high = round(float(df["high"].iloc[-50:].max()), 5)
    recent_low = round(float(df["low"].iloc[-50:].min()), 5)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "last_close": last_close,
        "rsi": {
            "value": rsi_val,
            "condition": rsi_cond,
            "divergence": rsi_div,
        },
        "macd": {
            "macd": macd_val,
            "signal": signal_val,
            "histogram": hist_val,
            "cross": macd_cross,
        },
        "bollinger": {
            "upper": bb_u,
            "mid": bb_m,
            "lower": bb_l,
            "price_position": bb_pos,
        },
        "ichimoku": {
            "tenkan": tenkan_val,
            "kijun": kijun_val,
            "senkou_a": sa_val,
            "senkou_b": sb_val,
            "cloud_position": cloud_pos,
            "tk_cross": tk_cross,
        },
        "ema": {
            "ema_50": ema50,
            "ema_100": ema100,
            "ema_200": ema200,
            "trend": ema_trend,
        },
        "atr": atr_val,
        "atr_pips": atr_pips,
        "support_resistance": {
            "recent_high": recent_high,
            "recent_low": recent_low,
        },
    }
