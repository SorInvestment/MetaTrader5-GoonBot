"""
config.py — All user settings for the MT5 Rule-Based Trading Bot.
Edit this file to configure the bot. No hardcoded values anywhere else.
"""
from typing import Dict, List, Optional

# --- MT5 Connection --------------------------------------------------------
MT5_LOGIN: int = 0                    # MT5 account number
MT5_PASSWORD: str = ""                # MT5 password
MT5_SERVER: str = ""                  # broker server, e.g. "ICMarkets-Live01"
MT5_PATH: Optional[str] = None       # full path to terminal64.exe if needed

# --- Instruments -----------------------------------------------------------
WATCHLIST: List[str] = ["USDJPY", "EURJPY", "GBPJPY"]

# --- Timeframes ------------------------------------------------------------
TREND_TF: str = "H4"                 # higher timeframe for trend direction
ENTRY_TF: str = "H1"                 # timeframe for entry signals
CONFIRM_TF: str = "M15"              # lower timeframe for entry confirmation
CANDLES: int = 250                    # candles to fetch (needs 200+ for EMA200)

# --- Risk Management -------------------------------------------------------
RISK_PER_TRADE_PCT: float = 1.0      # % of account balance risked per trade
MAX_OPEN_TRADES: int = 3             # max simultaneous positions
MAX_DRAWDOWN_PCT: float = 6.0        # pause bot if equity drawdown exceeds this %
SPREAD_LIMIT_PIPS: float = 3.0       # skip trade if spread > this
MIN_RR_RATIO: float = 1.5            # minimum reward:risk ratio to take a trade
SL_ATR_MULTIPLIER: float = 1.5       # stop loss = 1.5 x ATR
TP_ATR_MULTIPLIER: float = 2.5       # take profit = 2.5 x ATR
BREAKEVEN_TRIGGER_R: float = 1.0     # move SL to entry when profit reaches 1R
TRAIL_TRIGGER_R: float = 2.0         # start trailing when profit reaches 2R
TRAIL_ATR_MULT: float = 1.0          # trail distance = 1.0 x ATR

# --- Signal Thresholds -----------------------------------------------------
RSI_OVERBOUGHT: int = 65             # RSI must be below this for long entries
RSI_OVERSOLD: int = 35               # RSI must be above this for short entries
RSI_BULL_MIN: int = 45               # RSI floor for long signal (momentum needed)
RSI_BEAR_MAX: int = 55               # RSI ceiling for short signal
MIN_SIGNAL_SCORE: float = 5.0        # minimum 7-point score to trigger signal

# --- Session Weights -------------------------------------------------------
SESSION_WEIGHTS: Dict[str, dict] = {
    "tokyo":           {"hours_utc": (0, 8),   "weight": 0.8},
    "london":          {"hours_utc": (7, 16),  "weight": 1.2},
    "new_york":        {"hours_utc": (13, 21), "weight": 1.0},
    "overlap_ldn_ny":  {"hours_utc": (13, 16), "weight": 1.3},
}

# --- Correlation Filter ----------------------------------------------------
MAX_CORRELATED_TRADES: int = 2       # max same-direction positions on correlated pairs
CORRELATION_THRESHOLD: float = 0.85  # Pearson correlation threshold

# --- Volatility Filter -----------------------------------------------------
ATR_FILTER_LOOKBACK: int = 50        # bars to evaluate ATR percentile
ATR_LOW_PERCENTILE: float = 10.0     # skip if ATR below this percentile (choppy)
ATR_HIGH_PERCENTILE: float = 95.0    # skip if ATR above this percentile (news spike)

# --- Candlestick Patterns --------------------------------------------------
REQUIRE_CANDLE_PATTERN: bool = True   # require confirming candle pattern for entry

# --- Daily Loss Limit ------------------------------------------------------
DAILY_LOSS_LIMIT_PCT: float = 3.0    # stop trading for the day after this % loss

# --- Scaling Out -----------------------------------------------------------
SCALE_OUT_AT_R: float = 1.0          # partial close when profit reaches this R
SCALE_OUT_PCT: float = 0.5           # fraction of position to close

# --- News Calendar ---------------------------------------------------------
NEWS_FILTER_ENABLED: bool = True
NEWS_BUFFER_MINUTES: int = 30        # pause trading N minutes before high-impact news
NEWS_CALENDAR_URL: str = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# --- Per-Symbol Exposure Cap -----------------------------------------------
MAX_TRADES_PER_SYMBOL: int = 1       # max simultaneous positions per symbol

# --- Equity Curve / Streak Tracking ----------------------------------------
LOSING_STREAK_THRESHOLD: int = 3     # reduce size after N consecutive losses
STREAK_RISK_REDUCTION: float = 0.5   # multiply risk by this during losing streak

# --- Notifications ---------------------------------------------------------
TELEGRAM_ENABLED: bool = False
TELEGRAM_BOT_TOKEN: str = ""
TELEGRAM_CHAT_ID: str = ""
DISCORD_ENABLED: bool = False
DISCORD_WEBHOOK_URL: str = ""

# --- Health Monitoring -----------------------------------------------------
HEALTH_CHECK_INTERVAL: int = 3600    # seconds between health checks
MAX_INACTIVE_CYCLES: int = 50        # warn if no signals in N cycles
MAX_CONSECUTIVE_ERRORS: int = 5      # critical alert after N consecutive errors

# --- Config Hot-Reload -----------------------------------------------------
HOT_RELOAD_ENABLED: bool = True

# --- Time Filters ----------------------------------------------------------
ALLOWED_HOURS_UTC: List[int] = list(range(0, 22))  # skip 22:00-23:59 UTC
AVOID_FRIDAY_AFTER: int = 20         # no new entries after this UTC hour on Fridays

# --- Loop ------------------------------------------------------------------
LOOP_INTERVAL_SECONDS: int = 300     # 5 minutes

# --- Logging ---------------------------------------------------------------
LOG_FILE: str = "bot.log"
TRADE_DB: str = "trades.db"
LOG_LEVEL: str = "INFO"
LOG_FORMAT: str = "text"              # "text" or "json"

# --- Dashboard -------------------------------------------------------------
DASHBOARD_STATE_FILE: str = "bot_state.json"
