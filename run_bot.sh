#!/usr/bin/env bash
# run_bot.sh — Start/stop/manage the MT5 trading bot in the background.
# Usage: ./run_bot.sh {start|stop|restart|status|logs} [--dry-run]
#
# The bot runs in a loop with auto-restart on unexpected exit.
# PID is saved to bot.pid for process tracking.
# Sends SIGINT for graceful shutdown (triggers KeyboardInterrupt).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/bot.pid"
LOG_FILE="$SCRIPT_DIR/bot.log"
PYTHON="${PYTHON:-python3}"
RESTART_DELAY=30

# Load .env if it exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

_is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        # Stale PID file
        rm -f "$PID_FILE"
    fi
    return 1
}

_bot_loop() {
    # Auto-restart loop — runs until explicitly stopped
    local extra_args="$*"
    while true; do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting bot... $extra_args" >> "$LOG_FILE"
        # shellcheck disable=SC2086
        "$PYTHON" "$SCRIPT_DIR/main.py" $extra_args >> "$LOG_FILE" 2>&1
        local exit_code=$?

        if [ $exit_code -eq 0 ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot exited cleanly (code 0)" >> "$LOG_FILE"
            break
        fi

        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot exited with code $exit_code — restarting in ${RESTART_DELAY}s..." >> "$LOG_FILE"
        sleep "$RESTART_DELAY"
    done

    rm -f "$PID_FILE"
}

cmd_start() {
    if _is_running; then
        local pid
        pid=$(cat "$PID_FILE")
        echo "Bot is already running (PID $pid)"
        exit 1
    fi

    local extra_args=""
    shift 2>/dev/null || true  # skip "start"
    for arg in "$@"; do
        extra_args="$extra_args $arg"
    done

    echo "Starting bot in background..."
    nohup bash -c "$(declare -f _bot_loop); PYTHON='$PYTHON' SCRIPT_DIR='$SCRIPT_DIR' PID_FILE='$PID_FILE' LOG_FILE='$LOG_FILE' RESTART_DELAY='$RESTART_DELAY' _bot_loop $extra_args" > /dev/null 2>&1 &
    local bg_pid=$!
    echo "$bg_pid" > "$PID_FILE"
    echo "Bot started (PID $bg_pid)"
    echo "Log: $LOG_FILE"
    echo "Stop: $0 stop"
}

cmd_stop() {
    if ! _is_running; then
        echo "Bot is not running"
        exit 0
    fi

    local pid
    pid=$(cat "$PID_FILE")
    echo "Stopping bot (PID $pid) with SIGINT for graceful shutdown..."

    # Send SIGINT (triggers KeyboardInterrupt → graceful shutdown)
    kill -INT "$pid" 2>/dev/null || true

    # Wait up to 30s for graceful exit
    local waited=0
    while kill -0 "$pid" 2>/dev/null && [ $waited -lt 30 ]; do
        sleep 1
        waited=$((waited + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        echo "Bot did not stop gracefully — sending SIGTERM..."
        kill -TERM "$pid" 2>/dev/null || true
        sleep 2
        if kill -0 "$pid" 2>/dev/null; then
            echo "Force killing..."
            kill -9 "$pid" 2>/dev/null || true
        fi
    fi

    rm -f "$PID_FILE"
    echo "Bot stopped"
}

cmd_restart() {
    cmd_stop
    sleep 2
    cmd_start "$@"
}

cmd_status() {
    if _is_running; then
        local pid
        pid=$(cat "$PID_FILE")
        echo "Bot is RUNNING (PID $pid)"
        echo ""
        echo "--- Last 10 log lines ---"
        tail -10 "$LOG_FILE" 2>/dev/null || echo "(no log file)"
    else
        echo "Bot is NOT running"
        if [ -f "$LOG_FILE" ]; then
            echo ""
            echo "--- Last 5 log lines ---"
            tail -5 "$LOG_FILE" 2>/dev/null
        fi
    fi
}

cmd_logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "No log file found at $LOG_FILE"
        exit 1
    fi
}

# --- Main dispatch ---------------------------------------------------------
case "${1:-help}" in
    start)
        shift
        cmd_start "$@"
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        shift
        cmd_restart "$@"
        ;;
    status)
        cmd_status
        ;;
    logs)
        cmd_logs
        ;;
    *)
        echo "MT5 GoonBot — Background Runner"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs} [options]"
        echo ""
        echo "Commands:"
        echo "  start [--dry-run]   Start the bot in background"
        echo "  stop                Gracefully stop the bot"
        echo "  restart [--dry-run] Restart the bot"
        echo "  status              Show if running + recent logs"
        echo "  logs                Tail the log file (Ctrl+C to exit)"
        echo ""
        echo "Environment:"
        echo "  PYTHON=python3      Python interpreter to use"
        echo "  Credentials loaded from .env if present"
        exit 1
        ;;
esac
