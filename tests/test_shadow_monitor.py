"""
Tests for live.shadow_monitor — ShadowMonitor and ShadowStats.

Run:
    pytest tests/test_shadow_monitor.py -v
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict

import pytest

from live.shadow_monitor import (
    ShadowMonitor,
    ShadowStats,
    _MIN_SIGNALS_FOR_VERDICT,
    _BACKTEST_TARGETS,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_signal(pair: str = "XAUUSD", style: str = "day_trading", idx: int = 0) -> dict:
    """Create a minimal signal record (type != 'outcome')."""
    return {
        "shadow": True,
        "pair": pair,
        "style": style,
        "signal_id": f"sig-{idx:04d}",
        "direction": "BUY",
        "entry": 2000.0,
        "sl": 1990.0,
        "tp1": 2015.0,
        "tp2": 2030.0,
        "tp3": 2050.0,
        "signal_time": "2026-03-01T09:00:00+00:00",
        # No "type" key → treated as signal emission record
    }


def _make_outcome(
    pair: str = "XAUUSD",
    style: str = "day_trading",
    outcome: str = "TP1_HIT",
    entry: float = 2000.0,
    sl: float = 1990.0,
    tp1: float = 2015.0,
    tp2: float = 2030.0,
    tp3: float = 2050.0,
    idx: int = 0,
) -> dict:
    """Create a resolved outcome record."""
    return {
        "type": "outcome",
        "pair": pair,
        "style": style,
        "signal_id": f"sig-{idx:04d}",
        "direction": "BUY",
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "outcome": outcome,
        "resolved_at": "2026-03-01T10:00:00+00:00",
    }


def _write_jsonl(records: list[dict]) -> str:
    """Write records to a temp JSONL file and return the path."""
    tf = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    )
    for r in records:
        tf.write(json.dumps(r) + "\n")
    tf.close()
    return tf.name


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestComputeStats:
    """Tests for ShadowMonitor.compute_stats."""

    def test_basic_win_rate_60_signals(self):
        """40 TP1 hits out of 60 resolved signals → win_rate = 0.667."""
        records = []
        for i in range(60):
            records.append(_make_signal(idx=i))
        for i in range(40):
            records.append(_make_outcome(outcome="TP1_HIT", idx=i))
        for i in range(40, 60):
            records.append(_make_outcome(outcome="SL_HIT", idx=i))

        monitor = ShadowMonitor()
        stats = monitor.compute_stats(records)

        assert stats.total_signals == 60
        assert stats.resolved_signals == 60
        assert stats.tp1_hits == 40
        assert stats.sl_hits == 20
        assert abs(stats.tp1_win_rate - 0.6667) < 0.001

    def test_profit_factor_calculation(self):
        """Verify profit factor = gross_profit / gross_loss."""
        # 3 TP1 hits at entry=2000, sl=1990, tp1=2030 → reward=30 each
        # 2 SL hits → risk=10 each
        records = [
            _make_signal(idx=i) for i in range(5)
        ] + [
            _make_outcome(outcome="TP1_HIT", entry=2000.0, sl=1990.0, tp1=2030.0, idx=i)
            for i in range(3)
        ] + [
            _make_outcome(outcome="SL_HIT", entry=2000.0, sl=1990.0, tp1=2030.0, idx=i)
            for i in range(3, 5)
        ]

        monitor = ShadowMonitor()
        stats = monitor.compute_stats(records)

        # gross_profit = 30 * 3 = 90 — gross_loss = 10 * 2 = 20 — PF = 4.5
        assert abs(stats.profit_factor - 4.5) < 0.01

    def test_max_consecutive_losses(self):
        """Max consecutive losses tracked correctly across outcome sequence."""
        # sequence: W W L L L L W L L
        outcomes = ["TP1_HIT", "TP1_HIT", "SL_HIT", "SL_HIT", "SL_HIT", "SL_HIT", "TP1_HIT", "SL_HIT", "SL_HIT"]
        records = [_make_signal(idx=i) for i in range(len(outcomes))] + [
            _make_outcome(outcome=o, idx=i) for i, o in enumerate(outcomes)
        ]

        monitor = ShadowMonitor()
        stats = monitor.compute_stats(records)

        assert stats.max_consecutive_losses == 4

    def test_rolling_loss_rate_last_20(self):
        """Rolling loss rate uses the last 20 resolved outcomes."""
        # First 30 are all wins, last 10 are all SL hits
        records = [_make_signal(idx=i) for i in range(40)]
        for i in range(30):
            records.append(_make_outcome(outcome="TP1_HIT", idx=i))
        for i in range(30, 40):
            records.append(_make_outcome(outcome="SL_HIT", idx=i))

        monitor = ShadowMonitor()
        stats = monitor.compute_stats(records)

        # Last 20: 10 wins (idx 20-29) + 10 SL (idx 30-39) → 10/20 = 0.5
        assert abs(stats.rolling_loss_rate - 0.5) < 0.01

    def test_pair_filter(self):
        """Filtering by pair returns only matching records."""
        records = []
        # 30 XAUUSD signals + outcomes, 30 GBPJPY signals + outcomes
        for i in range(30):
            records.append(_make_signal(pair="XAUUSD", idx=i))
            records.append(_make_outcome(pair="XAUUSD", outcome="TP1_HIT", idx=i))
        for i in range(30, 60):
            records.append(_make_signal(pair="GBPJPY", idx=i))
            records.append(_make_outcome(pair="GBPJPY", outcome="SL_HIT", idx=i))

        monitor = ShadowMonitor()
        xau_stats = monitor.compute_stats(records, pair="XAUUSD")
        gj_stats = monitor.compute_stats(records, pair="GBPJPY")

        assert xau_stats.total_signals == 30
        assert xau_stats.tp1_hits == 30
        assert xau_stats.sl_hits == 0

        assert gj_stats.total_signals == 30
        assert gj_stats.tp1_hits == 0
        assert gj_stats.sl_hits == 30

    def test_style_filter(self):
        """Filtering by style returns only matching records."""
        records = []
        for i in range(40):
            pair = "XAUUSD"
            style = "day_trading" if i < 20 else "scalping"
            records.append(_make_signal(pair=pair, style=style, idx=i))
            records.append(_make_outcome(pair=pair, style=style, outcome="TP1_HIT", idx=i))

        monitor = ShadowMonitor()
        dt_stats = monitor.compute_stats(records, style="day_trading")
        sc_stats = monitor.compute_stats(records, style="scalping")

        assert dt_stats.total_signals == 20
        assert sc_stats.total_signals == 20

    def test_insufficient_data_below_minimum(self):
        """Stats with fewer than _MIN_SIGNALS_FOR_VERDICT resolved → INSUFFICIENT_DATA."""
        records = []
        count = _MIN_SIGNALS_FOR_VERDICT - 1
        for i in range(count):
            records.append(_make_signal(idx=i))
            records.append(_make_outcome(outcome="TP1_HIT", idx=i))

        monitor = ShadowMonitor()
        stats = monitor.compute_stats(records)

        assert stats.go_no_go == "INSUFFICIENT_DATA"
        assert stats.resolved_signals == count

    def test_go_no_go_field_set_correctly_by_compute_stats(self):
        """ShadowStats.go_no_go is set correctly by compute_stats (not just check_go_no_go)."""
        # Exactly _MIN_SIGNALS_FOR_VERDICT wins → good stats → GO
        records = []
        for i in range(_MIN_SIGNALS_FOR_VERDICT):
            records.append(_make_signal(pair="XAUUSD", style="day_trading", idx=i))
            records.append(_make_outcome(
                pair="XAUUSD", style="day_trading",
                outcome="TP1_HIT",
                entry=2000.0, sl=1990.0, tp1=2030.0,
                idx=i,
            ))

        monitor = ShadowMonitor()
        stats = monitor.compute_stats(records, pair="XAUUSD", style="day_trading")

        assert stats.go_no_go == "GO"
        assert stats.tp1_win_rate == 1.0


class TestCheckGoNoGo:
    """Tests for ShadowMonitor.check_go_no_go."""

    def _make_stats(
        self,
        resolved: int = _MIN_SIGNALS_FOR_VERDICT,
        tp1_hits: int | None = None,
        sl_hits: int | None = None,
        profit_factor: float = 2.0,
        max_consecutive: int = 2,
        pair: str = "XAUUSD",
        style: str = "day_trading",
    ) -> ShadowStats:
        if tp1_hits is None:
            tp1_hits = int(resolved * 0.65)
        if sl_hits is None:
            sl_hits = resolved - tp1_hits

        stats = ShadowStats(pair=pair, style=style)
        stats.total_signals = resolved
        stats.resolved_signals = resolved
        stats.tp1_hits = tp1_hits
        stats.sl_hits = sl_hits
        stats.tp1_win_rate = tp1_hits / resolved if resolved > 0 else 0.0
        stats.profit_factor = profit_factor
        stats.max_consecutive_losses = max_consecutive
        stats.rolling_loss_rate = sl_hits / min(resolved, 20) if resolved > 0 else 0.0
        return stats

    def test_go_with_sufficient_good_stats(self):
        """Sufficient data and good stats → GO."""
        monitor = ShadowMonitor()
        stats = self._make_stats(resolved=60, tp1_hits=40)
        go, reasons = monitor.check_go_no_go(stats)
        assert go is True
        assert any("FAIL" not in r for r in reasons)

    def test_no_go_with_poor_win_rate(self):
        """Win rate below 85% of target → NO-GO."""
        monitor = ShadowMonitor()
        # XAUUSD day_trading target = 0.60; 85% of 0.60 = 0.51
        # Force win rate well below floor
        stats = self._make_stats(resolved=60, tp1_hits=20)  # 33%
        go, reasons = monitor.check_go_no_go(stats)
        assert go is False
        assert any("FAIL" in r for r in reasons)

    def test_no_go_with_poor_profit_factor(self):
        """Profit factor below 1.2 → NO-GO."""
        monitor = ShadowMonitor()
        stats = self._make_stats(resolved=60, tp1_hits=38, profit_factor=0.9)
        go, reasons = monitor.check_go_no_go(stats)
        assert go is False
        assert any("Profit factor" in r and "FAIL" in r for r in reasons)

    def test_no_go_with_catastrophic_consecutive_losses(self):
        """More than 10 consecutive losses → NO-GO."""
        monitor = ShadowMonitor()
        stats = self._make_stats(resolved=60, tp1_hits=40, max_consecutive=11)
        go, reasons = monitor.check_go_no_go(stats)
        assert go is False
        assert any("consecutive" in r.lower() and "FAIL" in r for r in reasons)

    def test_insufficient_data_returns_none(self):
        """Fewer than _MIN_SIGNALS_FOR_VERDICT resolved signals → None verdict."""
        monitor = ShadowMonitor()
        stats = self._make_stats(resolved=_MIN_SIGNALS_FOR_VERDICT - 1)
        go, reasons = monitor.check_go_no_go(stats)
        assert go is None
        assert any("insufficient" in r.lower() or "Only" in r for r in reasons)

    def test_pair_style_filter_uses_correct_target(self):
        """GBPJPY day trading uses 0.58 win rate target, not XAUUSD's 0.60."""
        monitor = ShadowMonitor()
        # Win rate 51% — just above GBPJPY threshold (0.58 * 0.85 = 0.493)
        # but would fail if using a higher threshold
        stats = self._make_stats(
            resolved=100,
            tp1_hits=51,  # 51% — above 0.493 floor for GBPJPY
            profit_factor=1.5,
            max_consecutive=2,
            pair="GBPJPY",
            style="day_trading",
        )
        go, reasons = monitor.check_go_no_go(stats)
        assert go is True, f"Expected GO for GBPJPY with 51% win rate, got reasons: {reasons}"


class TestLoadSignals:
    """Tests for ShadowMonitor.load_signals."""

    def test_load_valid_jsonl(self):
        """Loads all records from a valid JSONL file."""
        records = [_make_signal(idx=i) for i in range(10)]
        path = _write_jsonl(records)
        try:
            monitor = ShadowMonitor()
            loaded = monitor.load_signals(path)
            assert len(loaded) == 10
        finally:
            os.unlink(path)

    def test_load_missing_file_raises(self):
        """FileNotFoundError raised when log does not exist."""
        monitor = ShadowMonitor()
        with pytest.raises(FileNotFoundError, match="Shadow log not found"):
            monitor.load_signals("/nonexistent/path/shadow_log.jsonl")

    def test_load_skips_malformed_lines(self, capsys):
        """Malformed JSON lines are skipped with a warning; valid lines are loaded."""
        import tempfile
        tf = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        tf.write('{"shadow": true, "pair": "XAUUSD"}\n')
        tf.write("NOT JSON AT ALL {{{\n")
        tf.write('{"shadow": true, "pair": "GBPJPY"}\n')
        tf.close()

        try:
            monitor = ShadowMonitor()
            loaded = monitor.load_signals(tf.name)
            assert len(loaded) == 2  # only the 2 valid lines
        finally:
            os.unlink(tf.name)
