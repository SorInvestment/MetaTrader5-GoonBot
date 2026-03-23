"""
config.py — All user settings for the MT5 Rule-Based Trading Bot.
Edit this file to configure the bot. No hardcoded values anywhere else.
"""
from typing import Optional, List

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

# --- Time Filters ----------------------------------------------------------
ALLOWED_HOURS_UTC: List[int] = list(range(0, 22))  # skip 22:00-23:59 UTC
AVOID_FRIDAY_AFTER: int = 20         # no new entries after this UTC hour on Fridays

# --- Loop ------------------------------------------------------------------
LOOP_INTERVAL_SECONDS: int = 300     # 5 minutes

# --- Logging ---------------------------------------------------------------
LOG_FILE: str = "bot.log"
TRADE_DB: str = "trades.db"
LOG_LEVEL: str = "INFO"
