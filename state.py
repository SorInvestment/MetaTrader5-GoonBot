"""
state.py — Bot state JSON interchange for the dashboard.
Writes current bot state to a JSON file each cycle.
"""
import json
import logging
import os
from typing import Any, Dict

import config

log = logging.getLogger(__name__)


def write_state(data: Dict[str, Any]) -> None:
    """Write bot state to the dashboard state file."""
    try:
        tmp_path = config.DASHBOARD_STATE_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, config.DASHBOARD_STATE_FILE)
    except Exception as e:
        log.error("Failed to write state file: %s", e)


def read_state() -> Dict[str, Any]:
    """Read bot state from the dashboard state file."""
    try:
        with open(config.DASHBOARD_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
