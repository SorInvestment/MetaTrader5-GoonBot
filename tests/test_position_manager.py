"""
test_position_manager.py — Unit tests for position management logic.
"""
import pytest

import config
import position_manager as pm


class TestCalculateNewSL:
    """Tests for the pure SL calculation function."""

    def test_no_change_below_breakeven(self):
        new_sl = pm.calculate_new_sl(
            direction="BUY", open_price=150.0, current_sl=149.5,
            current_price=150.3, atr=0.35, profit_r=0.6,
        )
        assert new_sl == 149.5  # No change — profit below breakeven trigger

    def test_breakeven_buy(self):
        new_sl = pm.calculate_new_sl(
            direction="BUY", open_price=150.0, current_sl=149.5,
            current_price=150.6, atr=0.35, profit_r=1.2,
        )
        expected = round(150.0 + 0.35 * 0.1, 5)
        assert new_sl == expected
        assert new_sl > 150.0  # SL moved above entry

    def test_breakeven_sell(self):
        new_sl = pm.calculate_new_sl(
            direction="SELL", open_price=150.0, current_sl=150.5,
            current_price=149.4, atr=0.35, profit_r=1.2,
        )
        expected = round(150.0 - 0.35 * 0.1, 5)
        assert new_sl == expected
        assert new_sl < 150.0

    def test_no_breakeven_if_already_moved(self):
        # SL already at breakeven — should not change
        new_sl = pm.calculate_new_sl(
            direction="BUY", open_price=150.0, current_sl=150.05,
            current_price=150.6, atr=0.35, profit_r=1.2,
        )
        assert new_sl == 150.05  # No change — SL already above entry

    def test_trail_buy(self):
        new_sl = pm.calculate_new_sl(
            direction="BUY", open_price=150.0, current_sl=150.05,
            current_price=151.2, atr=0.35, profit_r=2.5,
        )
        expected = round(151.2 - 0.35 * config.TRAIL_ATR_MULT, 5)
        assert new_sl == expected
        assert new_sl > 150.05

    def test_trail_sell(self):
        new_sl = pm.calculate_new_sl(
            direction="SELL", open_price=150.0, current_sl=149.95,
            current_price=148.8, atr=0.35, profit_r=2.5,
        )
        expected = round(148.8 + 0.35 * config.TRAIL_ATR_MULT, 5)
        assert new_sl == expected
        assert new_sl < 149.95

    def test_trail_does_not_move_sl_backward_buy(self):
        # Candidate trail SL is below current SL — should not move
        new_sl = pm.calculate_new_sl(
            direction="BUY", open_price=150.0, current_sl=150.9,
            current_price=151.0, atr=0.35, profit_r=2.1,
        )
        # candidate = 151.0 - 0.35 = 150.65, which is < 150.9
        assert new_sl == 150.9


class TestVolatilityOk:
    def test_normal_volatility(self):
        ind = {"atr_percentile": 50.0}
        assert pm.volatility_ok(ind) is True

    def test_low_volatility(self):
        ind = {"atr_percentile": 5.0}
        assert pm.volatility_ok(ind) is False

    def test_high_volatility(self):
        ind = {"atr_percentile": 98.0}
        assert pm.volatility_ok(ind) is False
