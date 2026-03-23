"""
risk_math.py — Pure mathematical functions for risk calculations.
No I/O, no MT5 imports. Used by both position_manager.py and backtester.py.
"""
import config


def calculate_new_sl(direction, open_price, current_sl, current_price, atr, profit_r):
    """Pure function to calculate new SL based on breakeven and trailing logic."""
    new_sl = current_sl
    if profit_r >= config.TRAIL_TRIGGER_R:
        trail_dist = atr * config.TRAIL_ATR_MULT
        if direction == "BUY":
            candidate = round(current_price - trail_dist, 5)
            if candidate > current_sl:
                new_sl = candidate
        else:
            candidate = round(current_price + trail_dist, 5)
            if candidate < current_sl:
                new_sl = candidate
    elif profit_r >= config.BREAKEVEN_TRIGGER_R:
        buffer = atr * 0.1
        if direction == "BUY" and current_sl < open_price:
            new_sl = round(open_price + buffer, 5)
        elif direction == "SELL" and current_sl > open_price:
            new_sl = round(open_price - buffer, 5)
    return new_sl


def volatility_lot_scale(atr_percentile):
    """Return lot size scaling factor based on ATR percentile.
    Low vol -> slightly larger (1.2x), high vol -> slightly smaller (0.8x)."""
    if atr_percentile < 30:
        return 1.2
    elif atr_percentile > 70:
        return 0.8
    return 1.0


def compute_expectancy(win_rate_pct, avg_win, avg_loss):
    """Compute mathematical expectancy per trade."""
    wr = win_rate_pct / 100.0
    return round(wr * avg_win - (1 - wr) * avg_loss, 2)


def compute_sharpe(returns_list, annualize_factor=252):
    """Compute annualized Sharpe ratio from a list of period returns."""
    import numpy as np
    if len(returns_list) < 2:
        return 0.0
    arr = np.array(returns_list, dtype=float)
    mean_ret = np.mean(arr)
    std_ret = np.std(arr, ddof=1)
    if std_ret == 0:
        return 0.0
    return round(float(mean_ret / std_ret * np.sqrt(annualize_factor)), 2)


def compute_sortino(returns_list, annualize_factor=252):
    """Compute annualized Sortino ratio (downside deviation only)."""
    import numpy as np
    if len(returns_list) < 2:
        return 0.0
    arr = np.array(returns_list, dtype=float)
    mean_ret = np.mean(arr)
    downside = arr[arr < 0]
    if len(downside) < 1:
        return float("inf") if mean_ret > 0 else 0.0
    downside_std = np.std(downside, ddof=1)
    if downside_std == 0:
        return 0.0
    return round(float(mean_ret / downside_std * np.sqrt(annualize_factor)), 2)


def compute_calmar(total_return_pct, max_drawdown_pct, years=1.0):
    """Compute Calmar ratio = annualized return / max drawdown."""
    if max_drawdown_pct == 0 or years == 0:
        return 0.0
    annual_return = total_return_pct / years
    return round(annual_return / max_drawdown_pct, 2)


def compute_max_consecutive(results):
    """Given a list of booleans (True=win, False=loss), return (max_consecutive_wins, max_consecutive_losses)."""
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0
    for is_win in results:
        if is_win:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        else:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)
    return max_wins, max_losses
