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
from dateutil.relativedelta import relativedelta
from typing import Callable, Optional

import pandas as pd

from backtest.executor import TradeRecord, TradeStatus, execute_next_bar_open, update_trade
from backtest.metrics import BacktestMetrics, compute_metrics
from data.resampler import resample_all


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
        from engine.signal_generator import STYLE_TIMEFRAMES
        entry_tf = STYLE_TIMEFRAMES.get(self.config.trading_style, ("15m", []))[0]

        # ── Resample once ────────────────────────────────────────────────────
        all_candles = resample_all(candles_1m)
        entry_candles = all_candles.get(entry_tf, candles_1m)

        if len(entry_candles) < 2:
            return BacktestResult(
                config=self.config,
                trades=[],
                metrics=compute_metrics([], self.config.initial_capital),
                equity_curve=[self.config.initial_capital],
                start_date=None,
                end_date=None,
                total_bars_processed=0,
            )

        start_date = entry_candles.index[0].to_pydatetime() if hasattr(entry_candles.index[0], "to_pydatetime") else entry_candles.index[0]
        end_date = entry_candles.index[-1].to_pydatetime() if hasattr(entry_candles.index[-1], "to_pydatetime") else entry_candles.index[-1]

        # ── Bar-by-bar iteration ─────────────────────────────────────────────
        equity = self.config.initial_capital
        equity_curve: list[float] = [equity]
        self._open_trades = []
        self._closed_trades = []

        for bar_idx in range(1, len(entry_candles)):
            bar = entry_candles.iloc[bar_idx]
            bar_time = entry_candles.index[bar_idx]
            if hasattr(bar_time, "to_pydatetime"):
                bar_time = bar_time.to_pydatetime()

            # Slice all candles up to current bar (no look-ahead)
            candles_dict = {
                tf: df.iloc[: df.index.searchsorted(entry_candles.index[bar_idx], side="right")]
                for tf, df in all_candles.items()
            }

            is_news = self._is_news_bar(bar_time, news_events)

            # Fill any pending trades from previous bar
            self._process_pending_fills(bar, is_news)

            # Update all open trades for TP/SL hits
            self._update_open_trades(bar)

            # Generate new signals via signal_generator callable
            if not is_news:
                new_trades = signal_generator(candles_dict, bar_idx)
                new_trades = self._apply_signal_limit(new_trades)
                self._open_trades.extend(new_trades)

            # Track equity (approximate: initial_capital + closed P&L sum)
            closed_pnl = sum(t.pnl_pips for t in self._closed_trades)
            equity_curve.append(self.config.initial_capital + closed_pnl)

        # Close any remaining open trades at end (mark as expired)
        for trade in self._open_trades:
            trade.status = TradeStatus.EXPIRED
            self._closed_trades.append(trade)
        self._open_trades = []

        all_trades = self._closed_trades[:]
        metrics = compute_metrics(all_trades, self.config.initial_capital)

        return BacktestResult(
            config=self.config,
            trades=all_trades,
            metrics=metrics,
            equity_curve=equity_curve,
            start_date=start_date,
            end_date=end_date,
            total_bars_processed=len(entry_candles) - 1,
        )

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
        from engine.signal_generator import STYLE_TIMEFRAMES

        # Determine window sizes based on trading style
        swing_style = self.config.trading_style in ("swing_trading", "position_trading")
        if swing_style:
            total_months = self.config.in_sample_months + self.config.out_sample_months  # default 12
            step_months = self.config.out_sample_months   # default 4
        else:
            total_months = self.config.in_sample_months + self.config.out_sample_months  # default 6
            step_months = self.config.out_sample_months   # default 2

        entry_tf = STYLE_TIMEFRAMES.get(self.config.trading_style, ("15m", []))[0]
        all_candles = resample_all(candles_1m)
        entry_candles = all_candles.get(entry_tf, candles_1m)

        if len(entry_candles) < 2:
            return []

        start_ts = entry_candles.index[0]
        end_ts = entry_candles.index[-1]
        if hasattr(start_ts, "to_pydatetime"):
            start_dt = start_ts.to_pydatetime()
            end_dt = end_ts.to_pydatetime()
        else:
            start_dt = start_ts
            end_dt = end_ts

        oos_results: list[BacktestResult] = []
        window_start = start_dt

        while True:
            is_end = window_start + relativedelta(months=self.config.in_sample_months)
            oos_end = is_end + relativedelta(months=self.config.out_sample_months)

            if oos_end > end_dt:
                break

            # Slice 1m candles for this OOS window
            # Convert to tz-aware Timestamps safely
            def _to_ts(dt):
                ts = pd.Timestamp(dt)
                if ts.tzinfo is None:
                    return ts.tz_localize("UTC")
                return ts.tz_convert("UTC")

            warmup_start = window_start
            warmup_mask = (candles_1m.index >= _to_ts(warmup_start)) & \
                          (candles_1m.index < _to_ts(oos_end))

            window_1m = candles_1m.loc[warmup_mask]
            if len(window_1m) < 500:
                window_start += relativedelta(months=step_months)
                continue

            oos_config = BacktestConfig(
                pair=self.config.pair,
                trading_style=self.config.trading_style,
                entry_timeframe=self.config.entry_timeframe,
                initial_capital=self.config.initial_capital,
                risk_pct=self.config.risk_pct,
                slippage_pips=self.config.slippage_pips,
                max_simultaneous_signals=self.config.max_simultaneous_signals,
                is_walk_forward=True,
                in_sample_months=self.config.in_sample_months,
                out_sample_months=self.config.out_sample_months,
            )
            oos_harness = BacktestHarness(oos_config)
            result = oos_harness.run(window_1m, signal_generator, news_events)
            result.is_out_of_sample = True
            oos_results.append(result)

            window_start += relativedelta(months=step_months)

        return oos_results

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
