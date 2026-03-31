#!/usr/bin/env python3
"""
validate_setup.py — Quick validation that the bot is correctly configured.
Run this before starting the bot to check credentials, config, database, and imports.

Usage: python validate_setup.py
"""
import os
import sys
import sqlite3

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(__file__))


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    msg = f"  [{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return ok


def main():
    print("=" * 60)
    print("  MT5 GoonBot — Setup Validation")
    print("=" * 60)
    errors = 0

    # 1. Python version
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 9
    if not check(f"Python {v.major}.{v.minor}.{v.micro}", ok, "requires 3.9+"):
        errors += 1

    # 2. Core imports
    print("\n--- Imports ---")
    for mod_name in ["config", "signals", "indicators", "logger", "position_manager",
                     "mt5_bridge", "news_filter", "equity_tracker", "health",
                     "risk_math", "config_validator", "config_watcher", "notifier",
                     "correlation", "backtester"]:
        try:
            __import__(mod_name)
            check(f"import {mod_name}", True)
        except ImportError as e:
            check(f"import {mod_name}", False, str(e))
            errors += 1

    # 3. Config validation
    print("\n--- Config ---")
    import config
    if not check("MT5_LOGIN set", config.MT5_LOGIN != 0, f"login={config.MT5_LOGIN}"):
        errors += 1
    if not check("MT5_PASSWORD set", len(config.MT5_PASSWORD) > 0):
        errors += 1
    if not check("MT5_SERVER set", len(config.MT5_SERVER) > 0, config.MT5_SERVER):
        errors += 1
    check("Watchlist", True, ", ".join(config.WATCHLIST))
    check("Risk per trade", True, f"{config.RISK_PER_TRADE_PCT}%")
    check("Max open trades", True, str(config.MAX_OPEN_TRADES))
    check("Max drawdown", True, f"{config.MAX_DRAWDOWN_PCT}%")
    check("Circuit breaker", True, f"after {config.MAX_CONSECUTIVE_LOSSES} losses, {config.CIRCUIT_BREAKER_COOLDOWN_HOURS}h cooldown")
    check("Per-symbol daily loss limit", True, f"{config.SYMBOL_DAILY_LOSS_LIMIT_PCT}%")
    check("News filter", True, f"enabled={config.NEWS_FILTER_ENABLED}, pre={config.NEWS_BUFFER_MINUTES}m, post={config.NEWS_POST_BUFFER_MINUTES}m, cache={config.NEWS_CACHE_HOURS}h")
    check("Log rotation", True, f"{config.LOG_MAX_BYTES // (1024*1024)}MB x {config.LOG_BACKUP_COUNT} files")
    check("Multi-TP targets", True, f"enabled={config.USE_MULTI_TP}, levels={len(config.TP_TARGETS)}")
    check("Limit orders", True, f"enabled={config.USE_LIMIT_ORDERS}, threshold={config.LIMIT_ORDER_SCORE_THRESHOLD}")

    # 4. Config validator
    print("\n--- Config Validator ---")
    try:
        from config_validator import validate
        validate()
        check("Config validates", True)
    except Exception as e:
        check("Config validates", False, str(e))
        errors += 1

    # 5. Database
    print("\n--- Database ---")
    import logger as trade_logger
    try:
        trade_logger.init_db()
        check("Database initialized", True, config.TRADE_DB)

        conn = sqlite3.connect(config.TRADE_DB)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        if not check("WAL mode enabled", mode == "wal", f"mode={mode}"):
            errors += 1
    except Exception as e:
        check("Database initialized", False, str(e))
        errors += 1

    # 6. .env file
    print("\n--- Environment ---")
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    check(".env file exists", os.path.exists(env_path),
          "credentials loaded from .env" if os.path.exists(env_path) else "using config.py defaults")

    gitignore_path = os.path.join(os.path.dirname(__file__), ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path) as f:
            check(".env in .gitignore", ".env" in f.read(), "credentials won't be committed")

    # 7. MT5 connection test
    print("\n--- MT5 Connection ---")
    try:
        import MetaTrader5
        check("MetaTrader5 package", True)
        try:
            import mt5_bridge as mt5b
            connected = mt5b.connect()
            if connected:
                check("MT5 connection", True, "connected to demo account")
                acct = mt5b.get_account_info()
                if "error" not in acct:
                    check("Account info", True,
                          f"balance={acct['balance']:.2f} {acct.get('currency', 'USD')}")
                mt5b.disconnect()
            else:
                check("MT5 connection", False, "could not connect — is terminal running?")
                errors += 1
        except Exception as e:
            check("MT5 connection", False, str(e))
            errors += 1
    except ImportError:
        check("MetaTrader5 package", False,
              "not installed (Windows-only). Install with: pip install MetaTrader5")
        print("         NOTE: MT5 requires Windows with terminal64.exe running.")
        print("         On Linux, use Wine or deploy to a Windows machine.")

    # Summary
    print("\n" + "=" * 60)
    if errors == 0:
        print("  All checks passed! Bot is ready to run.")
        print("  Start: ./run_bot.sh start")
        print("  Dry run: ./run_bot.sh start --dry-run")
    else:
        print(f"  {errors} check(s) failed. Fix issues above before running.")
    print("=" * 60)

    return errors


if __name__ == "__main__":
    sys.exit(main())
