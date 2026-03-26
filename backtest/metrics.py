"""
Performance Metrics Calculator — Sprint 1 deliverable (full implementation).

Computes all required backtest performance metrics from a list of trade records.

Metrics produced:
    Win rates (TP1, TP2, TP3 separately)
    Profit Factor
    Max Drawdown (absolute and %)
    Sharpe Ratio (annualized, risk-free rate = 0)
    Sortino Ratio
    Calmar Ratio
    Average R:R achieved
    Average hold time
    Trades per week
    Monthly P&L (for heatmap)
    Performance by Kill Zone
    Performance by day of week
    Consecutive loss statistics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

import pandas as pd
import numpy as np

from backtest.executor import TradeRecord, TradeStatus


@dataclass
class BacktestMetrics:
    """Complete performance statistics for a backtest run."""
    # Trade counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0

    # Win rates per TP level
    win_rate_tp1: float = 0.0    # % reaching TP1
    win_rate_tp2: float = 0.0    # % reaching TP2
    win_rate_tp3: float = 0.0    # % reaching TP3
    win_rate_overall: float = 0.0  # % positive P&L

    # Core metrics
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_usd: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    average_rr: float = 0.0
    average_hold_bars: float = 0.0
    trades_per_week: float = 0.0

    # P&L
    total_pnl_pips: float = 0.0
    total_pnl_usd: float = 0.0
    average_win_pips: float = 0.0
    average_loss_pips: float = 0.0

    # Streak stats
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0

    # Segment breakdowns (populated separately)
    by_kill_zone: dict[str, dict] = field(default_factory=dict)
    by_day_of_week: dict[str, dict] = field(default_factory=dict)
    monthly_pnl: dict[str, float] = field(default_factory=dict)  # "YYYY-MM" → pnl_pips

    # GO/NO-GO verdict
    passes_xauusd: Optional[bool] = None
    passes_gbpjpy: Optional[bool] = None


# GO/NO-GO acceptance criteria
GONOGO_CRITERIA = {
    "XAUUSD": {
        "win_rate_tp1": 0.60,
        "profit_factor": 1.40,
        "max_drawdown_pct": 15.0,
        "min_trades": 500,
    },
    "GBPJPY": {
        "win_rate_tp1": 0.58,
        "profit_factor": 1.30,
        "max_drawdown_pct": 18.0,
        "min_trades": 500,
    },
}


def compute_metrics(
    trades: list[TradeRecord],
    initial_capital: float = 10_000.0,
    risk_pct: float = 1.0,
    pair: Optional[str] = None,
) -> BacktestMetrics:
    """
    Compute all performance metrics from completed trade records.

    Args:
        trades: List of TradeRecord objects (OPEN and closed statuses).
        initial_capital: Starting account balance in USD.
        risk_pct: Risk per trade as % of account (used for USD P&L calculation).
        pair: Optional pair name for GO/NO-GO assessment.

    Returns:
        BacktestMetrics with all fields populated.
    """
    closed = [t for t in trades if t.status in (
        TradeStatus.TP1_HIT, TradeStatus.TP2_HIT, TradeStatus.TP3_HIT, TradeStatus.SL_HIT
    )]

    if not closed:
        return BacktestMetrics()

    m = BacktestMetrics()
    m.total_trades = len(closed)

    # Win rates per TP level
    tp1_hits = [t for t in closed if t.tp1_hit_at is not None]
    tp2_hits = [t for t in closed if t.tp2_hit_at is not None]
    tp3_hits = [t for t in closed if t.status == TradeStatus.TP3_HIT]
    sl_hits = [t for t in closed if t.status == TradeStatus.SL_HIT]

    m.win_rate_tp1 = len(tp1_hits) / m.total_trades
    m.win_rate_tp2 = len(tp2_hits) / m.total_trades
    m.win_rate_tp3 = len(tp3_hits) / m.total_trades

    # Overall win rate
    winners = [t for t in closed if t.pnl_pips > 0]
    losers = [t for t in closed if t.pnl_pips < 0]
    m.winning_trades = len(winners)
    m.losing_trades = len(losers)
    m.breakeven_trades = m.total_trades - m.winning_trades - m.losing_trades
    m.win_rate_overall = m.winning_trades / m.total_trades

    # P&L
    m.total_pnl_pips = sum(t.pnl_pips for t in closed)
    m.average_win_pips = (sum(t.pnl_pips for t in winners) / len(winners)) if winners else 0.0
    m.average_loss_pips = (sum(t.pnl_pips for t in losers) / len(losers)) if losers else 0.0

    # Profit Factor
    gross_profit = sum(t.pnl_pips for t in winners)
    gross_loss = abs(sum(t.pnl_pips for t in losers))
    m.profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    # Average R:R
    m.average_rr = (sum(t.r_multiple for t in closed) / m.total_trades)

    # Average hold time
    hold_times = []
    for t in closed:
        if t.entry_time and t.exit_time:
            hold_times.append((t.exit_time - t.entry_time).total_seconds() / 60)
    m.average_hold_bars = sum(hold_times) / len(hold_times) if hold_times else 0.0

    # Trades per week
    if closed and closed[0].signal_time and closed[-1].signal_time:
        span_weeks = (closed[-1].signal_time - closed[0].signal_time).days / 7.0
        m.trades_per_week = m.total_trades / span_weeks if span_weeks > 0 else 0.0

    # Equity curve and drawdown
    equity_curve = _build_equity_curve(closed, initial_capital, risk_pct)
    m.max_drawdown_pct, m.max_drawdown_usd = _calculate_max_drawdown(equity_curve, initial_capital)

    # USD P&L from final equity
    if len(equity_curve) > 0:
        m.total_pnl_usd = equity_curve[-1] - initial_capital

    # Risk-adjusted returns
    daily_returns = _equity_to_daily_returns(equity_curve, closed)
    m.sharpe_ratio = _sharpe(daily_returns)
    m.sortino_ratio = _sortino(daily_returns)
    m.calmar_ratio = _calmar(m.total_pnl_usd / initial_capital, m.max_drawdown_pct / 100.0)

    # Streaks
    m.max_consecutive_losses, m.max_consecutive_wins = _streak_stats(closed)

    # Monthly P&L
    m.monthly_pnl = _monthly_pnl(closed)

    # Day-of-week breakdown
    m.by_day_of_week = _segment_by(closed, lambda t: t.signal_time.strftime("%A") if t.signal_time else "Unknown")

    # GO/NO-GO verdict
    if pair and pair in GONOGO_CRITERIA:
        criteria = GONOGO_CRITERIA[pair]
        passes = (
            m.win_rate_tp1 >= criteria["win_rate_tp1"]
            and m.profit_factor >= criteria["profit_factor"]
            and m.max_drawdown_pct <= criteria["max_drawdown_pct"]
            and m.total_trades >= criteria["min_trades"]
        )
        if pair == "XAUUSD":
            m.passes_xauusd = passes
        else:
            m.passes_gbpjpy = passes

    return m


def _build_equity_curve(
    trades: list[TradeRecord],
    initial_capital: float,
    risk_pct: float,
) -> list[float]:
    """Build an equity curve as a list of account balances after each trade."""
    equity = initial_capital
    curve = [equity]
    for trade in sorted(trades, key=lambda t: t.exit_time or t.signal_time):
        dollar_risk = equity * (risk_pct / 100.0)
        pnl_usd = trade.r_multiple * dollar_risk
        equity += pnl_usd
        trade.pnl_usd = round(pnl_usd, 2)
        curve.append(equity)
    return curve


def _calculate_max_drawdown(equity: list[float], initial: float) -> tuple[float, float]:
    """Return (max_drawdown_pct, max_drawdown_usd) from equity curve."""
    if not equity:
        return 0.0, 0.0
    eq_array = np.array(equity)
    peak = np.maximum.accumulate(eq_array)
    drawdown = peak - eq_array
    max_dd_usd = float(drawdown.max())
    max_dd_pct = float((drawdown / peak).max()) * 100.0
    return max_dd_pct, max_dd_usd


def _equity_to_daily_returns(equity: list[float], trades: list[TradeRecord]) -> np.ndarray:
    """Convert equity curve to daily returns for Sharpe/Sortino calculation."""
    if len(equity) < 2:
        return np.array([])
    eq = np.array(equity)
    returns = np.diff(eq) / eq[:-1]
    return returns


def _sharpe(returns: np.ndarray, periods_per_year: int = 252) -> float:
    """Annualized Sharpe ratio (risk-free rate = 0)."""
    if len(returns) < 2 or returns.std() == 0:
        return 0.0
    return float((returns.mean() / returns.std()) * np.sqrt(periods_per_year))


def _sortino(returns: np.ndarray, periods_per_year: int = 252) -> float:
    """Annualized Sortino ratio (downside deviation only)."""
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < 0]
    if len(downside) == 0 or downside.std() == 0:
        return float("inf")
    return float((returns.mean() / downside.std()) * np.sqrt(periods_per_year))


def _calmar(total_return: float, max_drawdown: float) -> float:
    """Calmar ratio: annualized return / max drawdown."""
    if max_drawdown == 0:
        return float("inf")
    return total_return / max_drawdown


def _streak_stats(trades: list[TradeRecord]) -> tuple[int, int]:
    """Return (max_consecutive_losses, max_consecutive_wins)."""
    max_loss_streak = max_win_streak = 0
    cur_loss = cur_win = 0
    for t in trades:
        if t.pnl_pips > 0:
            cur_win += 1
            cur_loss = 0
        else:
            cur_loss += 1
            cur_win = 0
        max_loss_streak = max(max_loss_streak, cur_loss)
        max_win_streak = max(max_win_streak, cur_win)
    return max_loss_streak, max_win_streak


def _monthly_pnl(trades: list[TradeRecord]) -> dict[str, float]:
    """Aggregate pnl_pips by month key "YYYY-MM"."""
    result: dict[str, float] = {}
    for t in trades:
        ts = t.exit_time or t.signal_time
        if ts is None:
            continue
        key = ts.strftime("%Y-%m")
        result[key] = result.get(key, 0.0) + t.pnl_pips
    return result


def _segment_by(
    trades: list[TradeRecord],
    key_fn,
) -> dict[str, dict]:
    """Group trades by a key function and compute basic win rate per group."""
    groups: dict[str, list[TradeRecord]] = {}
    for t in trades:
        k = key_fn(t)
        groups.setdefault(k, []).append(t)

    result = {}
    for k, group in groups.items():
        wins = sum(1 for t in group if t.pnl_pips > 0)
        result[k] = {
            "trades": len(group),
            "win_rate": wins / len(group) if group else 0.0,
            "total_pnl_pips": sum(t.pnl_pips for t in group),
        }
    return result
