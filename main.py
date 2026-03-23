"""
main.py — Scheduler loop, time filters, orchestrator.
Integrates all features: M15 confirmation, session awareness, volatility/news filters,
correlation guards, equity tracking, health monitoring, config hot-reload, and notifications.
Entry point: python main.py
"""
import argparse
import logging
import sys
import time
from datetime import datetime, timezone

import config
import config_validator
import config_watcher
import logger as trade_logger
import mt5_bridge as mt5b
import news_filter
import position_manager as pm
import signals
import state
from equity_tracker import get_adjusted_risk_pct
from health import HealthMonitor
from notifier import notify, notify_trade
from risk_math import volatility_lot_scale

log = logging.getLogger(__name__)


def is_trading_allowed() -> bool:
    """Check if current UTC time is within allowed trading hours."""
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon ... 6=Sun
    hour = now.hour

    if weekday == 6:
        log.debug("Trading paused — Sunday")
        return False
    if weekday == 5 and hour >= 20:
        log.debug("Trading paused — Saturday close")
        return False
    if weekday == 4 and hour >= config.AVOID_FRIDAY_AFTER:
        log.debug("Trading paused — Friday after %d UTC", config.AVOID_FRIDAY_AFTER)
        return False
    if hour not in config.ALLOWED_HOURS_UTC:
        log.debug("Trading paused — hour %d not in allowed hours", hour)
        return False
    return True


def run_cycle(dry_run: bool = False, health: HealthMonitor = None) -> None:
    """Execute one full scan cycle."""
    # Hot-reload config if changed
    config_watcher.check_and_reload()

    # Always manage existing positions first
    pm.manage_open_positions()

    if not is_trading_allowed():
        log.info("Outside trading hours — skipping signal scan")
        return

    if not pm.drawdown_ok():
        log.warning("Drawdown guard active — skipping signal scan")
        return

    if not pm.daily_loss_ok():
        log.warning("Daily loss limit active — skipping signal scan")
        return

    if not pm.max_trades_ok():
        log.info("Max trades reached — skipping signal scan")
        return

    any_signal = False

    for symbol in config.WATCHLIST:
        if pm.already_open(symbol):
            log.debug("%s — already has open position, skipping", symbol)
            continue

        if not pm.spread_ok(symbol):
            continue

        # News calendar filter
        if news_filter.is_news_window(symbol):
            log.info("%s — news window active, skipping", symbol)
            continue

        # Fetch indicators for all timeframes
        entry_ind = mt5b.get_indicators(symbol, config.ENTRY_TF, config.CANDLES)
        if "error" in entry_ind:
            log.error("%s entry indicators error: %s", symbol, entry_ind["error"])
            continue

        trend_ind = mt5b.get_indicators(symbol, config.TREND_TF, config.CANDLES)
        if "error" in trend_ind:
            log.error("%s trend indicators error: %s", symbol, trend_ind["error"])
            continue

        # Volatility filter
        if not pm.volatility_ok(entry_ind):
            continue

        # M15 confirmation indicators
        confirm_ind = mt5b.get_indicators(symbol, config.CONFIRM_TF, config.CANDLES)
        if "error" in confirm_ind:
            log.warning("%s M15 indicators error: %s — proceeding without confirmation",
                        symbol, confirm_ind["error"])
            confirm_ind = None

        # Candle DataFrame for pattern detection
        candle_df = mt5b.get_candle_dataframe(symbol, config.ENTRY_TF, 10)

        # Get current tick
        tick = mt5b.get_tick(symbol)
        if "error" in tick:
            log.error("%s tick error: %s", symbol, tick["error"])
            continue

        # Evaluate signal
        signal = signals.evaluate(
            symbol=symbol,
            ind=entry_ind,
            trend_ind=trend_ind,
            ask=tick["ask"],
            bid=tick["bid"],
            confirm_ind=confirm_ind,
            candle_df=candle_df if not candle_df.empty else None,
        )

        if not signal.is_valid:
            log.info("%s — no valid signal", symbol)
            continue

        any_signal = True

        if signal.rr_ratio < config.MIN_RR_RATIO:
            log.info("%s — RR ratio %.2f below minimum %.2f",
                     symbol, signal.rr_ratio, config.MIN_RR_RATIO)
            continue

        # Correlation filter
        if not pm.correlation_ok(symbol, signal.direction):
            continue

        if dry_run:
            log.info("[DRY RUN] Would %s %s — entry=%.5f SL=%.5f TP=%.5f RR=%.2f "
                     "raw_score=%.1f weighted=%.1f reasons=%s",
                     signal.direction, symbol, signal.entry_price,
                     signal.sl_price, signal.tp_price, signal.rr_ratio,
                     signal.raw_score, signal.weighted_score, signal.reasons)
            continue

        # Calculate lot size with streak + volatility adjustment
        adjusted_risk = get_adjusted_risk_pct()
        vol_scale = volatility_lot_scale(entry_ind.get("atr_percentile", 50.0))
        lot = mt5b.calculate_lot_size(symbol, signal.sl_pips, risk_pct=adjusted_risk)
        lot = round(lot * vol_scale, 2)

        result = mt5b.execute_trade(
            symbol=symbol,
            direction=signal.direction,
            lot_size=lot,
            sl_price=signal.sl_price,
            tp_price=signal.tp_price,
            comment="rule_bot",
        )

        if result["success"]:
            trade_logger.log_trade(
                ticket=result["ticket"],
                symbol=symbol,
                direction=signal.direction,
                lot_size=lot,
                entry_price=result["price"],
                sl=signal.sl_price,
                tp=signal.tp_price,
                comment=f"score={signal.raw_score:.1f}/{signal.weighted_score:.1f}",
            )
            notify_trade(
                "open", symbol, signal.direction, result["price"],
                signal.sl_price, signal.tp_price, lot_size=lot,
            )
            if health:
                health.record_trade()
        else:
            log.error("Trade execution failed for %s: %s", symbol, result.get("error", "unknown"))

        # Stop scanning if max trades reached
        if not pm.max_trades_ok():
            log.info("Max trades reached after entry — stopping scan")
            break

    if not any_signal and health:
        health.record_no_signal()


def write_cycle_state(health: HealthMonitor) -> None:
    """Write current bot state for the dashboard."""
    acct = mt5b.get_account_info()
    positions = mt5b.get_positions()
    summary = trade_logger.get_trade_summary()

    state.write_state({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "account": acct if "error" not in acct else {},
        "positions": positions,
        "trade_summary": summary,
        "health": health.get_status(),
    })


def print_banner(dry_run: bool, once: bool) -> None:
    """Print startup banner with configuration summary."""
    print("=" * 60)
    print("  MT5 Rule-Based Trading Bot v2.0")
    print("=" * 60)
    print(f"  Mode:           {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"  Single cycle:   {once}")
    print(f"  Watchlist:      {config.WATCHLIST}")
    print(f"  Trend TF:       {config.TREND_TF}")
    print(f"  Entry TF:       {config.ENTRY_TF}")
    print(f"  Confirm TF:     {config.CONFIRM_TF}")
    print(f"  Risk/trade:     {config.RISK_PER_TRADE_PCT}%")
    print(f"  Max trades:     {config.MAX_OPEN_TRADES}")
    print(f"  Max drawdown:   {config.MAX_DRAWDOWN_PCT}%")
    print(f"  Daily loss max: {config.DAILY_LOSS_LIMIT_PCT}%")
    print(f"  Spread limit:   {config.SPREAD_LIMIT_PIPS} pips")
    print(f"  Min RR ratio:   {config.MIN_RR_RATIO}")
    print(f"  SL multiplier:  {config.SL_ATR_MULTIPLIER}x ATR")
    print(f"  TP multiplier:  {config.TP_ATR_MULTIPLIER}x ATR")
    print(f"  Scale out:      {config.SCALE_OUT_PCT*100:.0f}% at {config.SCALE_OUT_AT_R}R")
    print(f"  News filter:    {config.NEWS_FILTER_ENABLED}")
    print(f"  Candle pattern: {config.REQUIRE_CANDLE_PATTERN}")
    print(f"  Telegram:       {config.TELEGRAM_ENABLED}")
    print(f"  Discord:        {config.DISCORD_ENABLED}")
    print(f"  Hot reload:     {config.HOT_RELOAD_ENABLED}")
    print(f"  Loop interval:  {config.LOOP_INTERVAL_SECONDS}s")
    print(f"  Allowed hours:  {config.ALLOWED_HOURS_UTC[0]}-{config.ALLOWED_HOURS_UTC[-1]} UTC")
    print("=" * 60)


def main() -> None:
    """Main entry point with argument parsing and scheduler loop."""
    parser = argparse.ArgumentParser(description="MT5 Rule-Based Trading Bot")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate signals without trading")
    args = parser.parse_args()

    trade_logger.setup_logging()
    trade_logger.init_db()
    config_validator.validate()
    config_watcher.init()

    health = HealthMonitor()

    print_banner(args.dry_run, args.once)

    if not mt5b.connect():
        log.error("Failed to connect to MT5 — exiting")
        sys.exit(1)

    notify("Bot started" + (" (DRY RUN)" if args.dry_run else ""))

    try:
        while True:
            cycle_start = time.time()
            log.info("--- Cycle start ---")

            try:
                # Periodic health check
                if health.should_health_check():
                    health.check_connection(mt5b.connect, mt5b.disconnect)

                run_cycle(dry_run=args.dry_run, health=health)
                health.heartbeat()

                # Write state for dashboard
                write_cycle_state(health)

            except Exception as e:
                error_count = health.record_error()
                log.exception("Cycle error: %s", e)
                if health.is_critical():
                    notify(f"CRITICAL: {error_count} consecutive errors — last: {e}", level="critical")

            if health.is_inactive():
                log.warning("No signals for %d cycles", health.inactive_cycles)

            if args.once:
                log.info("Single cycle complete — exiting")
                break

            elapsed = time.time() - cycle_start
            sleep_time = max(0, config.LOOP_INTERVAL_SECONDS - elapsed)
            log.info("Cycle done in %.1fs — sleeping %.1fs", elapsed, sleep_time)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        log.info("Keyboard interrupt — shutting down gracefully")
    finally:
        mt5b.disconnect()
        summary = trade_logger.get_trade_summary()
        notify("Bot stopped")
        print("\n" + "=" * 60)
        print("  Trade Summary")
        print("=" * 60)
        print(f"  Total closed:  {summary['total_closed']}")
        print(f"  Wins:          {summary['wins']}")
        print(f"  Losses:        {summary['losses']}")
        print(f"  Win rate:      {summary['win_rate_pct']}%")
        print(f"  Total profit:  {summary['total_profit']}")
        print("=" * 60)


if __name__ == "__main__":
    main()
