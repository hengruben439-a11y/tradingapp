"""
Backtesting Harness — VectorBT-powered simulation framework.

Wraps the signal engine and executor into a complete walk-forward
backtesting pipeline with dynamic spreads and next-bar-open execution.

Configuration:
    Initial capital:    $10,000
    Risk per trade:     1% of account
    Execution:          Next-bar-open (signal bar close → next bar open)
    Spreads:            Session/news-dependent (from config/spreads.yaml)
    Slippage:           1 pip
    Commission:         $0

Usage:
    harness = BacktestHarness(pair="XAUUSD", trading_style="day_trading")
    results = harness.run(candles_1m, signal_generator_fn)
    print(results.metrics.profit_factor)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import pandas as pd

from backtest.executor import TradeRecord, execute_next_bar_open, update_trade
from backtest.metrics import BacktestMetrics, compute_metrics
from data.resampler import get_higher_timeframes, resample


@dataclass
class BacktestConfig:
    """Configuration for a single backtest run."""
    pair: str
    trading_style: str                # "scalping" | "day_trading" | "swing_trading" | "position_trading"
    entry_timeframe: str              # e.g. "15m"
    initial_capital: float = 10_000.0
    risk_pct: float = 1.0
    slippage_pips: float = 1.0
    max_simultaneous_signals: int = 3
    is_walk_forward: bool = False
    in_sample_months: int = 4
    out_sample_months: int = 2


@dataclass
class BacktestResult:
    """Results from a complete backtest run."""
    config: BacktestConfig
    trades: list[TradeRecord]
    metrics: BacktestMetrics
    equity_curve: list[float]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    total_bars_processed: int = 0
    is_out_of_sample: bool = False   # True for walk-forward OOS windows


class BacktestHarness:
    """
    Orchestrates the full backtesting pipeline.

    Signal generator function signature:
        def generate_signals(
            candles: dict[str, pd.DataFrame],  # keyed by timeframe
            bar_index: int,
        ) -> list[TradeRecord]:  # zero or more new signals (PENDING status)

    Sprint 1 deliverable: framework setup.
    Sprint 6 deliverable: full integration with all 9 engine modules.
    """

    def __init__(self, config: BacktestConfig):
        self.config = config
        self._open_trades: list[TradeRecord] = []
        self._closed_trades: list[TradeRecord] = []

    def run(
        self,
        candles_1m: pd.DataFrame,
        signal_generator: Callable,
        news_events: Optional[pd.DataFrame] = None,
    ) -> BacktestResult:
        """
        Run the full backtest over the provided 1-minute candle data.

        Args:
            candles_1m: 1-minute OHLCV DataFrame (full 5-year history).
            signal_generator: Function that takes (candles_dict, bar_index) → list[TradeRecord]
            news_events: Optional DataFrame with high-impact news timestamps.

        Returns:
            BacktestResult with all trades and computed metrics.

        Sprint 6 implementation notes:
        - Resample 1m data to all required TFs once (not per bar)
        - Iterate bar-by-bar on the entry timeframe
        - On each bar close: call signal_generator; check for news proximity
        - Next bar: attempt to fill any PENDING trades
        - Each bar: update all OPEN trades for TP/SL hits
        - Apply max_simultaneous_signals limit per pair
        - Accumulate trades; compute metrics at the end
        """
        raise NotImplementedError("Implement in Sprint 6")

    def run_walk_forward(
        self,
        candles_1m: pd.DataFrame,
        signal_generator: Callable,
        news_events: Optional[pd.DataFrame] = None,
    ) -> list[BacktestResult]:
        """
        Walk-forward optimization: slide in-sample/out-of-sample windows
        across the full data range.

        Day Trading / Scalping:
            Window: 6 months (4 IS + 2 OOS), step: 2 months
        Swing Trading:
            Window: 12 months (8 IS + 4 OOS), step: 4 months

        Returns:
            List of BacktestResult objects, one per OOS window.
            Compute WFO efficiency ratio from these: avg_oos_pf / avg_is_pf >= 0.6

        Sprint 6 implementation.
        """
        raise NotImplementedError("Implement in Sprint 6")

    def _is_news_bar(
        self,
        bar_time: datetime,
        news_events: Optional[pd.DataFrame],
        window_minutes: int = 5,
    ) -> bool:
        """
        Return True if bar_time falls within window_minutes of a high-impact event.
        """
        if news_events is None or news_events.empty:
            return False
        for _, event in news_events.iterrows():
            event_time = event.get("timestamp")
            if event_time is None:
                continue
            delta = abs((bar_time - event_time).total_seconds() / 60.0)
            if delta <= window_minutes:
                return True
        return False

    def _apply_signal_limit(self, new_trades: list[TradeRecord]) -> list[TradeRecord]:
        """
        Enforce max_simultaneous_signals per pair.
        Discard lowest-confidence signals if limit is exceeded.
        """
        current_open = len([t for t in self._open_trades if t.status in ("OPEN", "PENDING")])
        available = self.config.max_simultaneous_signals - current_open
        return new_trades[:max(0, available)]

    def _process_pending_fills(
        self,
        bar: pd.Series,
        is_news_bar: bool,
    ) -> None:
        """Fill all PENDING trades at the current bar's open."""
        for trade in self._open_trades:
            if trade.status.value == "PENDING":
                execute_next_bar_open(trade, bar, is_news_bar)

    def _update_open_trades(self, bar: pd.Series) -> None:
        """Check TP/SL for all open trades on the current bar."""
        updated = []
        for trade in self._open_trades:
            if trade.status.value in ("TP3_HIT", "SL_HIT", "EXPIRED"):
                self._closed_trades.append(trade)
            else:
                risk_pips = abs(trade.entry_price - trade.stop_loss) / _pip_size(trade.pair)
                updated_trade = update_trade(trade, bar, risk_pips)
                if updated_trade.status.value in ("TP3_HIT", "SL_HIT", "EXPIRED"):
                    self._closed_trades.append(updated_trade)
                else:
                    updated.append(updated_trade)
        self._open_trades = updated


def _pip_size(pair: str) -> float:
    if pair == "GBPJPY":
        return 0.01
    elif pair == "XAUUSD":
        return 0.1
    return 0.0001
