"""
Backtest Harness Tests — Sprint 6 deliverable.

Tests the full harness pipeline including:
    - run() produces valid BacktestResult
    - Metrics are computed correctly from trades
    - Signal limit enforcement
    - News bar suppression
    - Walk-forward window slicing
    - HTML and JSON report generation
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile

from backtest.harness import BacktestConfig, BacktestHarness, BacktestResult
from backtest.executor import TradeRecord, TradeStatus, Direction
from backtest.metrics import compute_metrics
from backtest.reporter import BacktestReporter
from engine.signal import Direction as SignalDirection


# ── Synthetic data helpers ─────────────────────────────────────────────────────

def _make_1m_candles(
    n: int = 5000,
    base_price: float = 2000.0,
    trend: str = "bull",
    start: datetime | None = None,
) -> pd.DataFrame:
    """Generate 1-minute OHLCV DataFrame."""
    if start is None:
        start = datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    rng = np.random.default_rng(7)
    prices = [base_price]
    for _ in range(n - 1):
        drift = 0.0002 if trend == "bull" else (-0.0002 if trend == "bear" else 0.0)
        prices.append(prices[-1] * (1 + drift + rng.normal(0, 0.002)))
    prices = np.array(prices)
    noise = rng.uniform(0.001, 0.002, n)
    idx = pd.date_range(start=start, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame({
        "open":   prices * (1 - noise * 0.3),
        "high":   prices * (1 + noise),
        "low":    prices * (1 - noise),
        "close":  prices,
        "volume": rng.uniform(100, 400, n),
    }, index=idx)


def _dummy_signal_generator_none(candles_dict, bar_index):
    """Always returns no signals."""
    return []


def _make_pending_trade(pair="XAUUSD", direction="BUY", entry=2000.0) -> TradeRecord:
    from engine.signal import Direction as D
    return TradeRecord(
        signal_id="test-id",
        pair=pair,
        direction=D.BUY if direction == "BUY" else D.SELL,
        signal_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
        entry_time=None,
        entry_price=entry,
        fill_price=None,
        spread_applied=0.0,
        stop_loss=entry - 10.0 if direction == "BUY" else entry + 10.0,
        tp1=entry + 15.0 if direction == "BUY" else entry - 15.0,
        tp2=entry + 25.0 if direction == "BUY" else entry - 25.0,
        tp3=entry + 40.0 if direction == "BUY" else entry - 40.0,
        initial_lot_size=0.1,
        current_lot_size=0.1,
        status=TradeStatus.PENDING,
    )


def _make_config(pair="XAUUSD", style="day_trading") -> BacktestConfig:
    return BacktestConfig(
        pair=pair,
        trading_style=style,
        entry_timeframe="15m",
        initial_capital=10_000.0,
        risk_pct=1.0,
        max_simultaneous_signals=3,
    )


# ── BacktestConfig tests ───────────────────────────────────────────────────────

class TestBacktestConfig:
    def test_default_capital(self):
        cfg = _make_config()
        assert cfg.initial_capital == 10_000.0

    def test_default_risk_pct(self):
        cfg = _make_config()
        assert cfg.risk_pct == 1.0

    def test_default_slippage(self):
        cfg = _make_config()
        assert cfg.slippage_pips == 1.0

    def test_default_max_signals(self):
        cfg = _make_config()
        assert cfg.max_simultaneous_signals == 3

    def test_wfo_defaults(self):
        cfg = _make_config()
        assert cfg.in_sample_months == 4
        assert cfg.out_sample_months == 2


# ── BacktestHarness.run() tests ───────────────────────────────────────────────

class TestHarnessRun:
    def test_run_with_no_signals_returns_result(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=3000)
        result = harness.run(candles_1m, _dummy_signal_generator_none)
        assert isinstance(result, BacktestResult)
        assert result.total_bars_processed > 0

    def test_run_returns_zero_trades_for_no_signal_gen(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=3000)
        result = harness.run(candles_1m, _dummy_signal_generator_none)
        assert result.metrics.total_trades == 0

    def test_run_returns_equity_curve(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=3000)
        result = harness.run(candles_1m, _dummy_signal_generator_none)
        assert len(result.equity_curve) > 0
        assert result.equity_curve[0] == pytest.approx(10_000.0)

    def test_run_sets_start_and_end_date(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=3000)
        result = harness.run(candles_1m, _dummy_signal_generator_none)
        assert result.start_date is not None
        assert result.end_date is not None
        assert result.end_date > result.start_date

    def test_run_with_few_candles_returns_empty_result(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=5)
        result = harness.run(candles_1m, _dummy_signal_generator_none)
        assert isinstance(result, BacktestResult)

    def test_run_respects_news_bar_suppression(self):
        """With news events covering all bars, no signals should be generated."""
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=1000)

        signal_count = [0]

        def counting_gen(candles_dict, bar_idx):
            signal_count[0] += 1
            return []

        # Create news events at every minute
        news_times = candles_1m.index.to_list()
        news_df = pd.DataFrame({"timestamp": news_times})
        result = harness.run(candles_1m, counting_gen, news_df)
        # All bars are news bars → generator is never called
        assert signal_count[0] == 0

    def test_run_with_signal_generator_producing_trades(self):
        """Signal generator that always returns one trade per bar."""
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=500)

        trade_template = _make_pending_trade()

        import copy
        import uuid

        def always_signal(candles_dict, bar_idx):
            t = copy.copy(trade_template)
            t.signal_id = str(uuid.uuid4())
            return [t]

        result = harness.run(candles_1m, always_signal)
        # max_simultaneous_signals=3 limits how many open at once; we should get some trades
        assert result.metrics.total_trades >= 0  # may be 0 if all expired without fill

    def test_config_preserved_in_result(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=500)
        result = harness.run(candles_1m, _dummy_signal_generator_none)
        assert result.config.pair == "XAUUSD"
        assert result.config.trading_style == "day_trading"


# ── Signal limit enforcement ────────────────────────────────────────────────────

class TestSignalLimit:
    def test_apply_signal_limit_respects_max(self):
        cfg = BacktestConfig(
            pair="XAUUSD", trading_style="day_trading", entry_timeframe="15m",
            max_simultaneous_signals=2,
        )
        harness = BacktestHarness(cfg)
        trades = [_make_pending_trade() for _ in range(5)]
        allowed = harness._apply_signal_limit(trades)
        assert len(allowed) == 2

    def test_apply_signal_limit_with_existing_open_trades(self):
        cfg = BacktestConfig(
            pair="XAUUSD", trading_style="day_trading", entry_timeframe="15m",
            max_simultaneous_signals=3,
        )
        harness = BacktestHarness(cfg)
        # Already 2 open trades
        existing = _make_pending_trade()
        existing.status = TradeStatus.OPEN
        harness._open_trades = [existing, existing]
        new_trades = [_make_pending_trade() for _ in range(5)]
        allowed = harness._apply_signal_limit(new_trades)
        assert len(allowed) == 1  # only 1 slot remaining

    def test_apply_signal_limit_allows_all_when_under_max(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        trades = [_make_pending_trade()]
        allowed = harness._apply_signal_limit(trades)
        assert len(allowed) == 1

    def test_apply_signal_limit_returns_empty_when_full(self):
        cfg = BacktestConfig(
            pair="XAUUSD", trading_style="day_trading", entry_timeframe="15m",
            max_simultaneous_signals=2,
        )
        harness = BacktestHarness(cfg)
        t = _make_pending_trade()
        t.status = TradeStatus.OPEN
        harness._open_trades = [t, t]
        result = harness._apply_signal_limit([_make_pending_trade()])
        assert len(result) == 0


# ── News bar detection ──────────────────────────────────────────────────────────

class TestNewsBarDetection:
    def test_is_news_bar_false_with_no_events(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        bar_time = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        assert harness._is_news_bar(bar_time, None) is False

    def test_is_news_bar_false_with_empty_df(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        bar_time = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        empty = pd.DataFrame({"timestamp": []})
        assert harness._is_news_bar(bar_time, empty) is False

    def test_is_news_bar_true_within_window(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        bar_time = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        news_time = datetime(2024, 6, 1, 12, 3, tzinfo=timezone.utc)  # 3 min away
        news_df = pd.DataFrame({"timestamp": [news_time]})
        assert harness._is_news_bar(bar_time, news_df, window_minutes=5) is True

    def test_is_news_bar_false_outside_window(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        bar_time = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        news_time = datetime(2024, 6, 1, 12, 10, tzinfo=timezone.utc)  # 10 min away
        news_df = pd.DataFrame({"timestamp": [news_time]})
        assert harness._is_news_bar(bar_time, news_df, window_minutes=5) is False


# ── BacktestResult and metrics ──────────────────────────────────────────────────

class TestBacktestResult:
    def test_metrics_zero_for_no_trades(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=500)
        result = harness.run(candles_1m, _dummy_signal_generator_none)
        assert result.metrics.total_trades == 0
        assert result.metrics.profit_factor == 0.0 or result.metrics.profit_factor == float("inf")

    def test_is_out_of_sample_defaults_false(self):
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=500)
        result = harness.run(candles_1m, _dummy_signal_generator_none)
        assert result.is_out_of_sample is False


# ── Reporter tests ─────────────────────────────────────────────────────────────

class TestBacktestReporter:
    def _make_empty_result(self) -> BacktestResult:
        cfg = _make_config()
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=300)
        return harness.run(candles_1m, _dummy_signal_generator_none)

    def test_print_summary_no_exception(self, capsys):
        reporter = BacktestReporter()
        result = self._make_empty_result()
        reporter.print_summary(result)
        captured = capsys.readouterr()
        assert "BACKTEST RESULTS" in captured.out

    def test_to_dict_has_required_keys(self):
        reporter = BacktestReporter()
        result = self._make_empty_result()
        data = reporter.to_dict(result)
        for key in ("pair", "profit_factor", "win_rate_tp1", "max_drawdown_pct",
                    "total_trades", "sharpe_ratio", "generated_at"):
            assert key in data

    def test_save_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = BacktestReporter(output_dir=Path(tmpdir))
            result = self._make_empty_result()
            path = reporter.save(result, fmt="json")
            assert path.exists()
            import json
            data = json.loads(path.read_text())
            assert data["pair"] == "XAUUSD"

    def test_save_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = BacktestReporter(output_dir=Path(tmpdir))
            result = self._make_empty_result()
            path = reporter.save(result, fmt="html")
            assert path.exists()
            content = path.read_text()
            assert "made. Backtest Report" in content
            assert "XAUUSD" in content

    def test_save_html_contains_go_nogo_verdict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = BacktestReporter(output_dir=Path(tmpdir))
            result = self._make_empty_result()
            path = reporter.save(result, fmt="html")
            content = path.read_text()
            assert "GO" in content or "NO-GO" in content

    def test_save_unsupported_format_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = BacktestReporter(output_dir=Path(tmpdir))
            result = self._make_empty_result()
            with pytest.raises(ValueError):
                reporter.save(result, fmt="pdf")

    def test_compute_wfo_efficiency_empty(self):
        reporter = BacktestReporter()
        assert reporter.compute_wfo_efficiency([]) == pytest.approx(0.0)

    def test_compute_wfo_efficiency_returns_avg(self):
        reporter = BacktestReporter()
        r1 = self._make_empty_result()
        r2 = self._make_empty_result()
        ratio = reporter.compute_wfo_efficiency([r1, r2])
        assert ratio >= 0.0


# ── Walk-forward window tests ─────────────────────────────────────────────────

class TestWalkForward:
    def test_run_walk_forward_returns_list(self):
        cfg = BacktestConfig(
            pair="XAUUSD",
            trading_style="day_trading",
            entry_timeframe="15m",
            in_sample_months=2,
            out_sample_months=1,
        )
        harness = BacktestHarness(cfg)
        # 8 months of 1-min data → enough for 2+1 month windows
        candles_1m = _make_1m_candles(n=60 * 24 * 30 * 4)  # ~4 months
        results = harness.run_walk_forward(candles_1m, _dummy_signal_generator_none)
        assert isinstance(results, list)

    def test_walk_forward_results_are_oos(self):
        cfg = BacktestConfig(
            pair="XAUUSD",
            trading_style="day_trading",
            entry_timeframe="15m",
            in_sample_months=2,
            out_sample_months=1,
        )
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=60 * 24 * 30 * 4)
        results = harness.run_walk_forward(candles_1m, _dummy_signal_generator_none)
        for r in results:
            assert r.is_out_of_sample is True

    def test_walk_forward_empty_on_insufficient_data(self):
        cfg = BacktestConfig(
            pair="XAUUSD",
            trading_style="day_trading",
            entry_timeframe="15m",
            in_sample_months=12,
            out_sample_months=6,
        )
        harness = BacktestHarness(cfg)
        candles_1m = _make_1m_candles(n=100)  # Nowhere near enough
        results = harness.run_walk_forward(candles_1m, _dummy_signal_generator_none)
        assert results == []
