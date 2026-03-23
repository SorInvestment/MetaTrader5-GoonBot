"""
notifier.py — Telegram and Discord alert notifications.
Sends trade alerts, warnings, and status updates.
"""
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

import config

log = logging.getLogger(__name__)


def _send_telegram(message: str) -> bool:
    """Send a message via Telegram Bot API."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        log.error("Telegram send failed: %s", e)
        return False


def _send_discord(message: str) -> bool:
    """Send a message via Discord webhook."""
    if not config.DISCORD_WEBHOOK_URL:
        return False

    payload = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(
        config.DISCORD_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        log.error("Discord send failed: %s", e)
        return False


def notify(message: str, level: str = "info") -> None:
    """
    Dispatch a notification to all enabled channels.
    Level can be 'info', 'warning', or 'critical'.
    """
    prefix = {"warning": "WARNING", "critical": "CRITICAL"}.get(level, "INFO")
    formatted = f"[{prefix}] {message}"

    if config.TELEGRAM_ENABLED:
        _send_telegram(formatted)

    if config.DISCORD_ENABLED:
        _send_discord(formatted)

    log.info("Notification sent (%s): %s", level, message[:100])


def notify_trade(action: str, symbol: str, direction: str, price: float,
                 sl: float, tp: float, lot_size: float = 0.0, profit: float = 0.0) -> None:
    """Send a formatted trade notification."""
    if action == "open":
        msg = (
            f"Trade Opened: {direction} {symbol}\n"
            f"Entry: {price:.5f} | Lots: {lot_size:.2f}\n"
            f"SL: {sl:.5f} | TP: {tp:.5f}"
        )
    elif action == "close":
        msg = (
            f"Trade Closed: {direction} {symbol}\n"
            f"Price: {price:.5f} | Profit: {profit:.2f}"
        )
    elif action == "breakeven":
        msg = f"Breakeven: {direction} {symbol} — SL moved to {sl:.5f}"
    elif action == "trail":
        msg = f"Trailing: {direction} {symbol} — SL moved to {sl:.5f}"
    else:
        msg = f"{action}: {direction} {symbol} @ {price:.5f}"

    notify(msg)
