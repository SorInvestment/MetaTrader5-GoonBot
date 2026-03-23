"""Tests for risk_math.py — pure math functions."""
import pytest
from risk_math import (
    calculate_new_sl,
    compute_calmar,
    compute_expectancy,
    compute_max_consecutive,
    compute_sharpe,
    compute_sortino,
    volatility_lot_scale,
)


class TestCalculateNewSL:
    def test_trailing_stop_buy(self):
        # profit_r=2.5 >= TRAIL_TRIGGER_R (2.0), should trail
        new_sl = calculate_new_sl("BUY", 150.0, 149.5, 151.0, 0.35, 2.5)
        assert new_sl > 149.5  # SL should move up

    def test_trailing_stop_sell(self):
        new_sl = calculate_new_sl("SELL", 150.0, 150.5, 149.0, 0.35, 2.5)
        assert new_sl < 150.5  # SL should move down

    def test_breakeven_buy(self):
        # profit_r=1.0 >= BREAKEVEN_TRIGGER_R, below TRAIL_TRIGGER_R
        new_sl = calculate_new_sl("BUY", 150.0, 149.5, 150.5, 0.35, 1.0)
        assert new_sl > 150.0  # SL moved above entry (breakeven + buffer)

    def test_breakeven_sell(self):
        new_sl = calculate_new_sl("SELL", 150.0, 150.5, 149.5, 0.35, 1.0)
        assert new_sl < 150.0  # SL moved below entry

    def test_no_change_below_breakeven(self):
        new_sl = calculate_new_sl("BUY", 150.0, 149.5, 150.2, 0.35, 0.3)
        assert new_sl == 149.5  # No change

    def test_trail_only_ratchets_up(self):
        # Already at a good SL, trail candidate is worse
        new_sl = calculate_new_sl("BUY", 150.0, 150.8, 151.0, 0.35, 2.5)
        trail_candidate = round(151.0 - 0.35 * 1.0, 5)
        if trail_candidate > 150.8:
            assert new_sl == trail_candidate
        else:
            assert new_sl == 150.8


class TestVolatilityLotScale:
    def test_low_vol_scales_up(self):
        assert volatility_lot_scale(20) == 1.2

    def test_high_vol_scales_down(self):
        assert volatility_lot_scale(80) == 0.8

    def test_normal_vol_no_scale(self):
        assert volatility_lot_scale(50) == 1.0

    def test_boundary_30(self):
        assert volatility_lot_scale(30) == 1.0

    def test_boundary_70(self):
        assert volatility_lot_scale(70) == 1.0


class TestExpectancy:
    def test_positive_expectancy(self):
        result = compute_expectancy(60, 20, 10)
        assert result > 0

    def test_negative_expectancy(self):
        result = compute_expectancy(30, 10, 20)
        assert result < 0

    def test_zero_win_rate(self):
        assert compute_expectancy(0, 10, 10) == -10.0


class TestSharpe:
    def test_positive_returns(self):
        returns = [1.0, 2.0, 1.5, 3.0, 0.5]
        result = compute_sharpe(returns)
        assert result > 0

    def test_insufficient_data(self):
        assert compute_sharpe([1.0]) == 0.0

    def test_zero_std(self):
        assert compute_sharpe([1.0, 1.0, 1.0]) == 0.0


class TestSortino:
    def test_with_downside(self):
        returns = [1.0, -0.5, 2.0, -1.0, 3.0]
        result = compute_sortino(returns)
        assert result > 0

    def test_no_downside(self):
        returns = [1.0, 2.0, 3.0]
        result = compute_sortino(returns)
        assert result == float("inf")

    def test_insufficient_data(self):
        assert compute_sortino([1.0]) == 0.0


class TestCalmar:
    def test_positive(self):
        result = compute_calmar(20.0, 5.0)
        assert result == 4.0

    def test_zero_drawdown(self):
        assert compute_calmar(20.0, 0.0) == 0.0


class TestMaxConsecutive:
    def test_basic(self):
        results = [True, True, True, False, False, True, False, False, False, False]
        wins, losses = compute_max_consecutive(results)
        assert wins == 3
        assert losses == 4

    def test_all_wins(self):
        wins, losses = compute_max_consecutive([True, True, True])
        assert wins == 3
        assert losses == 0

    def test_empty(self):
        wins, losses = compute_max_consecutive([])
        assert wins == 0
        assert losses == 0
