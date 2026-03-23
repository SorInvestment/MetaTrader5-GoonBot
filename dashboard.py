"""
dashboard.py — Streamlit dashboard for monitoring the MT5 trading bot.
Runs as a separate process: streamlit run dashboard.py

Displays:
- Account overview (balance, equity, drawdown)
- Open positions with live P&L
- Equity curve from trade history
- Trade log with filters
- Health status
"""
import sqlite3
from datetime import datetime

import pandas as pd

import config
from state import read_state

try:
    import streamlit as st
except ImportError:
    print("Streamlit not installed. Run: pip install streamlit")
    exit(1)

st.set_page_config(page_title="MT5 Trading Bot", layout="wide")


def load_trades() -> pd.DataFrame:
    """Load all trades from the SQLite database."""
    try:
        conn = sqlite3.connect(config.TRADE_DB)
        df = pd.read_sql_query("SELECT * FROM trades ORDER BY open_time DESC", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def main() -> None:
    """Render the Streamlit dashboard."""
    st.title("MT5 Rule-Based Trading Bot")

    # Load bot state
    bot_state = read_state()

    # --- Sidebar ---
    st.sidebar.header("Bot Status")
    health = bot_state.get("health", {})
    status = health.get("status", "unknown")
    status_color = {"ok": "green", "degraded": "orange", "critical": "red"}.get(status, "gray")
    st.sidebar.markdown(f"Status: :{status_color}[**{status.upper()}**]")
    st.sidebar.metric("Total Cycles", health.get("total_cycles", 0))
    st.sidebar.metric("Consecutive Errors", health.get("consecutive_errors", 0))
    st.sidebar.metric("Inactive Cycles", health.get("inactive_cycles", 0))

    timestamp = bot_state.get("timestamp", "N/A")
    st.sidebar.text(f"Last update: {timestamp}")

    # --- Account Overview ---
    st.header("Account Overview")
    acct = bot_state.get("account", {})
    if acct:
        cols = st.columns(5)
        cols[0].metric("Balance", f"{acct.get('balance', 0):.2f} {acct.get('currency', '')}")
        cols[1].metric("Equity", f"{acct.get('equity', 0):.2f}")

        balance = acct.get("balance", 1)
        equity = acct.get("equity", 1)
        dd = (1 - equity / balance) * 100 if balance > 0 else 0
        cols[2].metric("Drawdown", f"{dd:.2f}%")
        cols[3].metric("Free Margin", f"{acct.get('free_margin', 0):.2f}")
        cols[4].metric("Leverage", f"1:{acct.get('leverage', 0)}")
    else:
        st.info("No account data available. Is the bot running?")

    # --- Open Positions ---
    st.header("Open Positions")
    positions = bot_state.get("positions", {})
    pos_list = positions.get("positions", [])
    if pos_list:
        pos_df = pd.DataFrame(pos_list)
        st.dataframe(pos_df, use_container_width=True)
    else:
        st.info("No open positions")

    # --- Trade History ---
    st.header("Trade History")
    trades_df = load_trades()
    if not trades_df.empty:
        # Summary metrics
        closed = trades_df[trades_df["status"] == "closed"]
        if not closed.empty:
            summary = bot_state.get("trade_summary", {})
            cols = st.columns(5)
            cols[0].metric("Total Closed", summary.get("total_closed", len(closed)))
            cols[1].metric("Wins", summary.get("wins", 0))
            cols[2].metric("Losses", summary.get("losses", 0))
            cols[3].metric("Win Rate", f"{summary.get('win_rate_pct', 0)}%")
            cols[4].metric("Total Profit", f"{summary.get('total_profit', 0):.2f}")

            # Equity curve
            st.subheader("Equity Curve")
            closed_sorted = closed.sort_values("close_time")
            if "profit" in closed_sorted.columns:
                closed_sorted["cumulative_profit"] = closed_sorted["profit"].cumsum()
                st.line_chart(
                    closed_sorted.set_index("close_time")["cumulative_profit"],
                    use_container_width=True,
                )

        # Trade log table
        st.subheader("Trade Log")
        symbol_filter = st.selectbox("Filter by symbol", ["All"] + sorted(trades_df["symbol"].unique().tolist()))
        if symbol_filter != "All":
            trades_df = trades_df[trades_df["symbol"] == symbol_filter]
        st.dataframe(trades_df, use_container_width=True)
    else:
        st.info("No trades recorded yet")

    # --- Configuration ---
    with st.expander("Current Configuration"):
        config_items = {
            "Watchlist": config.WATCHLIST,
            "Trend TF": config.TREND_TF,
            "Entry TF": config.ENTRY_TF,
            "Confirm TF": config.CONFIRM_TF,
            "Risk/Trade": f"{config.RISK_PER_TRADE_PCT}%",
            "Max Trades": config.MAX_OPEN_TRADES,
            "Max Drawdown": f"{config.MAX_DRAWDOWN_PCT}%",
            "Daily Loss Limit": f"{config.DAILY_LOSS_LIMIT_PCT}%",
            "SL Multiplier": f"{config.SL_ATR_MULTIPLIER}x ATR",
            "TP Multiplier": f"{config.TP_ATR_MULTIPLIER}x ATR",
            "Min RR Ratio": config.MIN_RR_RATIO,
            "Scale Out": f"{config.SCALE_OUT_PCT*100:.0f}% at {config.SCALE_OUT_AT_R}R",
            "News Filter": config.NEWS_FILTER_ENABLED,
            "Candle Pattern": config.REQUIRE_CANDLE_PATTERN,
        }
        for key, val in config_items.items():
            st.text(f"{key}: {val}")

    # Auto-refresh every 60 seconds
    st.markdown(
        '<meta http-equiv="refresh" content="60">',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
