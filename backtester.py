"""
backtester.py — Walk-forward backtesting engine.
Replays historical candles through the same signals.evaluate() and
position_manager.calculate_new_sl() logic used in live trading.

Usage:
    python backtester.py --symbol USDJPY --start 2024-01-01 --end 2024-12-31
    python backtester.py --csv data/USDJPY_H1.csv
"""
import argparse
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd

import config
import indicators
import signals
from risk_math import (
    calculate_new_sl,
    compute_calmar,
    compute_expectancy,
    compute_max_consecutive,
    compute_sharpe,
    compute_sortino,
)

log = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """A simulated trade in the backtester."""
    symbol: str
    direction: str
    entry_price: float
    entry_time: datetime
    sl: float
    tp: float
    volume: float = 1.0
    exit_price: float = 0.0
    exit_time: Optional[datetime] = None
    profit_pips: float = 0.0
    profit_r: float = 0.0
    exit_reason: str = ""
    scaled_out: bool = False


@dataclass
class BacktestResult:
    """Summary of a backtest run."""
    symbol: str
    period: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pips: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pips: float = 0.0
    avg_win_pips: float = 0.0
    avg_loss_pips: float = 0.0
    avg_rr: float = 0.0
    expectancy: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)


class BacktestEngine:
    """Walk-forward backtesting engine using the bot's signal and indicator logic."""

    def __init__(self, symbol: str, h1_data: pd.DataFrame, h4_data: Optional[pd.DataFrame] = None):
        """
        Initialise with OHLCV DataFrames.
        h1_data must have columns: time, open, high, low, close, tick_volume
        h4_data is optional — if not provided, will be resampled from H1.
        """
        self.symbol = symbol
        self.h1 = h1_data.copy()
        self.h4 = h4_data if h4_data is not None else self._resample_to_h4(h1_data)
        self.trades: List[BacktestTrade] = []
        self.open_trade: Optional[BacktestTrade] = None
        self.equity_curve: List[float] = [0.0]

    @staticmethod
    def _resample_to_h4(h1: pd.DataFrame) -> pd.DataFrame:
        """Resample H1 data to H4."""
        df = h1.set_index("time")
        h4 = df.resample("4h").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "tick_volume": "sum",
        }).dropna().reset_index()
        return h4

    def run(self, window: int = 250) -> BacktestResult:
        """Run the backtest over the H1 data."""
        log.info("Backtesting %s — %d H1 bars, window=%d", self.symbol, len(self.h1), window)

        for i in range(window, len(self.h1)):
            bar = self.h1.iloc[i]
            bar_time = bar["time"]

            # Manage open trade
            if self.open_trade is not None:
                self._check_exit(bar, i)

            # Skip if already in a trade
            if self.open_trade is not None:
                continue

            # Get H1 window for indicators
            h1_window = self.h1.iloc[i - window:i + 1]

            # Get matching H4 window
            h4_before = self.h4[self.h4["time"] <= bar_time]
            if len(h4_before) < window // 4:
                continue
            h4_window = h4_before.iloc[-(window):] if len(h4_before) >= window else h4_before

            # Compute indicators
            try:
                entry_ind = indicators.compute_indicators(h1_window, self.symbol, "H1")
                trend_ind = indicators.compute_indicators(h4_window, self.symbol, "H4")
            except Exception:
                continue

            # Evaluate signal (no M15 or candle pattern in backtest for simplicity)
            close = bar["close"]
            spread = entry_ind["atr"] * 0.01  # simulate small spread
            ask = close + spread / 2
            bid = close - spread / 2

            signal = signals.evaluate(
                self.symbol, entry_ind, trend_ind,
                ask=ask, bid=bid,
                confirm_ind=None, candle_df=None,
            )

            if signal.is_valid and signal.direction:
                self.open_trade = BacktestTrade(
                    symbol=self.symbol,
                    direction=signal.direction,
                    entry_price=signal.entry_price,
                    entry_time=bar_time,
                    sl=signal.sl_price,
                    tp=signal.tp_price,
                )
                log.debug("Backtest entry: %s %s @ %.5f  SL=%.5f TP=%.5f",
                          signal.direction, self.symbol, signal.entry_price, signal.sl_price, signal.tp_price)

        # Close any remaining open trade at last bar
        if self.open_trade is not None:
            last_bar = self.h1.iloc[-1]
            self._force_close(last_bar, "end_of_data")

        return self._compile_results()

    def _check_exit(self, bar: pd.Series, bar_idx: int) -> None:
        """Check if SL or TP was hit on this bar, and apply trail/breakeven."""
        trade = self.open_trade
        high = bar["high"]
        low = bar["low"]

        if trade.direction == "BUY":
            # Check SL hit (low touches SL)
            if low <= trade.sl:
                self._close_trade(trade.sl, bar["time"], "sl_hit")
                return
            # Check TP hit (high touches TP)
            if high >= trade.tp:
                self._close_trade(trade.tp, bar["time"], "tp_hit")
                return

            # Trail/breakeven
            r_dist = abs(trade.entry_price - trade.sl)
            if r_dist > 0:
                profit_r = (bar["close"] - trade.entry_price) / r_dist
                # Simple ATR approximation for trailing
                atr = (high - low)  # current bar range as ATR proxy
                new_sl = calculate_new_sl("BUY", trade.entry_price, trade.sl, bar["close"], atr, profit_r)
                if new_sl != trade.sl:
                    trade.sl = new_sl

        else:  # SELL
            if high >= trade.sl:
                self._close_trade(trade.sl, bar["time"], "sl_hit")
                return
            if low <= trade.tp:
                self._close_trade(trade.tp, bar["time"], "tp_hit")
                return

            r_dist = abs(trade.sl - trade.entry_price)
            if r_dist > 0:
                profit_r = (trade.entry_price - bar["close"]) / r_dist
                atr = (high - low)
                new_sl = calculate_new_sl("SELL", trade.entry_price, trade.sl, bar["close"], atr, profit_r)
                if new_sl != trade.sl:
                    trade.sl = new_sl

        # Update equity curve
        pip_size = 0.01 if "JPY" in trade.symbol else 0.0001
        if trade.direction == "BUY":
            unrealised = (bar["close"] - trade.entry_price) / pip_size
        else:
            unrealised = (trade.entry_price - bar["close"]) / pip_size
        self.equity_curve.append(self.equity_curve[-1] + 0)  # flat until closed

    def _close_trade(self, exit_price: float, exit_time: datetime, reason: str) -> None:
        """Close the current trade."""
        trade = self.open_trade
        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.exit_reason = reason

        pip_size = 0.01 if "JPY" in trade.symbol else 0.0001
        if trade.direction == "BUY":
            trade.profit_pips = round((exit_price - trade.entry_price) / pip_size, 1)
        else:
            trade.profit_pips = round((trade.entry_price - exit_price) / pip_size, 1)

        r_dist = abs(trade.entry_price - trade.sl) if trade.sl != trade.entry_price else 1
        trade.profit_r = round(trade.profit_pips * 0.001 / r_dist, 2) if r_dist > 0 else 0

        self.trades.append(trade)
        self.equity_curve.append(self.equity_curve[-1] + trade.profit_pips)
        self.open_trade = None

        log.debug("Backtest exit: %s %.1f pips (%s)", trade.direction, trade.profit_pips, reason)

    def _force_close(self, bar: pd.Series, reason: str) -> None:
        """Force close at bar's close price."""
        self._close_trade(bar["close"], bar["time"], reason)

    def _compile_results(self) -> BacktestResult:
        """Compile trade list into summary statistics."""
        result = BacktestResult(
            symbol=self.symbol,
            period=f"{self.h1['time'].iloc[0]} to {self.h1['time'].iloc[-1]}",
            trades=self.trades,
            equity_curve=self.equity_curve,
        )

        if not self.trades:
            return result

        result.total_trades = len(self.trades)
        wins = [t for t in self.trades if t.profit_pips > 0]
        losses = [t for t in self.trades if t.profit_pips <= 0]
        result.wins = len(wins)
        result.losses = len(losses)
        result.win_rate = round(result.wins / result.total_trades * 100, 1) if result.total_trades else 0
        result.total_pips = round(sum(t.profit_pips for t in self.trades), 1)

        gross_wins = sum(t.profit_pips for t in wins)
        gross_losses = abs(sum(t.profit_pips for t in losses))
        result.profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else float("inf")

        result.avg_win_pips = round(gross_wins / len(wins), 1) if wins else 0
        result.avg_loss_pips = round(gross_losses / len(losses), 1) if losses else 0

        # Max drawdown from equity curve
        peak = 0.0
        max_dd = 0.0
        for eq in self.equity_curve:
            peak = max(peak, eq)
            dd = peak - eq
            max_dd = max(max_dd, dd)
        result.max_drawdown_pips = round(max_dd, 1)

        rr_values = [t.profit_r for t in self.trades if t.profit_r != 0]
        result.avg_rr = round(np.mean(rr_values), 2) if rr_values else 0

        # Advanced stats from risk_math
        result.expectancy = compute_expectancy(
            result.win_rate, result.avg_win_pips, result.avg_loss_pips,
        )

        pip_returns = [t.profit_pips for t in self.trades]
        result.sharpe = compute_sharpe(pip_returns)
        result.sortino = compute_sortino(pip_returns)

        total_return = result.total_pips
        result.calmar = compute_calmar(total_return, result.max_drawdown_pips)

        win_loss_seq = [t.profit_pips > 0 for t in self.trades]
        result.max_consecutive_wins, result.max_consecutive_losses = compute_max_consecutive(win_loss_seq)

        return result


def print_report(result: BacktestResult) -> None:
    """Print a formatted backtest report."""
    print("\n" + "=" * 60)
    print(f"  Backtest Report: {result.symbol}")
    print(f"  Period: {result.period}")
    print("=" * 60)
    print(f"  Total trades:      {result.total_trades}")
    print(f"  Wins:              {result.wins}")
    print(f"  Losses:            {result.losses}")
    print(f"  Win rate:          {result.win_rate}%")
    print(f"  Total pips:        {result.total_pips}")
    print(f"  Profit factor:     {result.profit_factor}")
    print(f"  Max drawdown:      {result.max_drawdown_pips} pips")
    print(f"  Avg win:           {result.avg_win_pips} pips")
    print(f"  Avg loss:          {result.avg_loss_pips} pips")
    print(f"  Avg R:R achieved:  {result.avg_rr}")
    print(f"  Expectancy:        {result.expectancy} pips/trade")
    print(f"  Sharpe ratio:      {result.sharpe}")
    print(f"  Sortino ratio:     {result.sortino}")
    print(f"  Calmar ratio:      {result.calmar}")
    print(f"  Max consec. wins:  {result.max_consecutive_wins}")
    print(f"  Max consec. losses:{result.max_consecutive_losses}")
    print("=" * 60)

    if result.trades:
        print("\n  Last 10 trades:")
        print(f"  {'Dir':<5} {'Entry':>10} {'Exit':>10} {'Pips':>8} {'Reason':<12}")
        print("  " + "-" * 50)
        for t in result.trades[-10:]:
            print(f"  {t.direction:<5} {t.entry_price:>10.5f} {t.exit_price:>10.5f} "
                  f"{t.profit_pips:>8.1f} {t.exit_reason:<12}")
    print()


def main() -> None:
    """CLI entry point for backtesting."""
    parser = argparse.ArgumentParser(description="MT5 Bot Backtester")
    parser.add_argument("--symbol", default="USDJPY", help="Symbol to backtest")
    parser.add_argument("--csv", help="Path to H1 CSV file (time,open,high,low,close,tick_volume)")
    parser.add_argument("--csv-h4", help="Path to H4 CSV file (optional)")
    parser.add_argument("--window", type=int, default=250, help="Indicator lookback window")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.csv:
        h1_data = pd.read_csv(args.csv, parse_dates=["time"])
        h4_data = pd.read_csv(args.csv_h4, parse_dates=["time"]) if args.csv_h4 else None
    else:
        # Try to fetch from MT5 if available
        try:
            import mt5_bridge as mt5b
            if not mt5b.connect():
                print("Cannot connect to MT5. Provide --csv instead.")
                return
            import MetaTrader5 as mt5
            rates = mt5.copy_rates_from_pos(args.symbol, mt5.TIMEFRAME_H1, 0, 5000)
            if rates is None:
                print(f"No data for {args.symbol}")
                return
            h1_data = pd.DataFrame(rates)
            h1_data["time"] = pd.to_datetime(h1_data["time"], unit="s")
            h4_data = None
            mt5b.disconnect()
        except ImportError:
            print("MT5 not available. Provide --csv with historical data.")
            return

    engine = BacktestEngine(args.symbol, h1_data, h4_data)
    result = engine.run(window=args.window)
    print_report(result)


if __name__ == "__main__":
    main()
