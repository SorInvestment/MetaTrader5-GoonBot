"""
correlation.py — Cross-pair correlation analysis.
Detects when multiple JPY pairs are moving together to limit correlated risk.
"""
import logging
from typing import Dict, List

import config

log = logging.getLogger(__name__)

# Currency mapping for correlation grouping
SYMBOL_CURRENCIES: Dict[str, List[str]] = {
    "USDJPY": ["USD", "JPY"],
    "EURJPY": ["EUR", "JPY"],
    "GBPJPY": ["GBP", "JPY"],
    "EURUSD": ["EUR", "USD"],
    "GBPUSD": ["GBP", "USD"],
    "EURGBP": ["EUR", "GBP"],
}


def get_shared_currency(sym1: str, sym2: str) -> str:
    """Return the shared currency between two symbols, or empty string."""
    c1 = set(SYMBOL_CURRENCIES.get(sym1, []))
    c2 = set(SYMBOL_CURRENCIES.get(sym2, []))
    shared = c1 & c2
    return shared.pop() if shared else ""


def check_correlated_exposure(
    open_positions: List[dict],
    proposed_symbol: str,
    proposed_direction: str,
) -> bool:
    """
    Return True if adding this trade would exceed correlated exposure limits.
    Checks same-direction positions on pairs sharing a currency.
    """
    same_dir_correlated = 0

    for pos in open_positions:
        if pos["type"] != proposed_direction:
            continue

        shared = get_shared_currency(pos["symbol"], proposed_symbol)
        if shared:
            same_dir_correlated += 1

    if same_dir_correlated >= config.MAX_CORRELATED_TRADES:
        log.info(
            "Correlation filter: %s %s blocked — %d correlated %s positions already open",
            proposed_direction, proposed_symbol, same_dir_correlated, proposed_direction,
        )
        return True

    return False
