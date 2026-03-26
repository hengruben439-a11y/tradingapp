"""
Market Structure Module Tests — Sprint 2 deliverable.

Requires 200+ labeled test cases covering:
    - Swing point detection (confirmed highs and lows)
    - BOS detection in bullish and bearish trends
    - CHoCH detection with and without displacement filter
    - State machine transitions
    - RANGING detection
    - Score output for each state/event combination

Sprint 1: scaffolding and helpers.
Sprint 2: full 200+ test cases added alongside implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import pytest

from engine.modules.market_structure import (
    MarketStructureModule,
    StructureEvent,
    SwingPoint,
    TrendState,
    _SCORE_MAP,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_candles(
    highs: list[float],
    lows: list[float],
    closes: Optional[list[float]] = None,
    opens: Optional[list[float]] = None,
    start: str = "2024-01-01",
    freq: str = "15min",
) -> pd.DataFrame:
    """
    Build a minimal OHLCV DataFrame from high/low arrays.
    Closes default to midpoint. Opens default to previous close.
    """
    n = len(highs)
    assert len(lows) == n

    if closes is None:
        closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    if opens is None:
        opens = [closes[max(0, i - 1)] for i in range(n)]

    index = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open":   opens,
            "high":   highs,
            "low":    lows,
            "close":  closes,
            "volume": [1000.0] * n,
        },
        index=index,
    )


def _bullish_trend_candles(n: int = 20) -> pd.DataFrame:
    """Generate a clear bullish trend: consistently higher highs and higher lows."""
    highs = [100.0 + i * 1.5 for i in range(n)]
    lows = [99.0 + i * 1.5 for i in range(n)]
    return _make_candles(highs, lows)


def _bearish_trend_candles(n: int = 20) -> pd.DataFrame:
    """Generate a clear bearish trend: consistently lower highs and lower lows."""
    highs = [120.0 - i * 1.5 for i in range(n)]
    lows = [119.0 - i * 1.5 for i in range(n)]
    return _make_candles(highs, lows)


def _ranging_candles(n: int = 20, center: float = 100.0, width: float = 2.0) -> pd.DataFrame:
    """Generate ranging candles oscillating within a band."""
    import math
    highs = [center + width * abs(math.sin(i * 0.7)) for i in range(n)]
    lows = [center - width * abs(math.sin(i * 0.7 + 0.5)) for i in range(n)]
    return _make_candles(highs, lows)


@pytest.fixture
def module_15m() -> MarketStructureModule:
    return MarketStructureModule(timeframe="15m", pair="XAUUSD")


@pytest.fixture
def module_1h() -> MarketStructureModule:
    return MarketStructureModule(timeframe="1H", pair="GBPJPY")


# ─── Score Map Tests (no implementation needed) ──────────────────────────────

class TestScoreMap:
    def test_bullish_trend_bos_score(self):
        assert _SCORE_MAP[(TrendState.BULLISH_TREND, StructureEvent.BOS_BULLISH)] == 0.8

    def test_bullish_trend_choch_score(self):
        assert _SCORE_MAP[(TrendState.BULLISH_TREND, StructureEvent.CHOCH_BULLISH)] == 1.0

    def test_bearish_trend_bos_score(self):
        assert _SCORE_MAP[(TrendState.BEARISH_TREND, StructureEvent.BOS_BEARISH)] == -0.8

    def test_bearish_trend_choch_score(self):
        assert _SCORE_MAP[(TrendState.BEARISH_TREND, StructureEvent.CHOCH_BEARISH)] == -1.0

    def test_ranging_score(self):
        assert _SCORE_MAP[(TrendState.RANGING, None)] == 0.0

    def test_unknown_score(self):
        assert _SCORE_MAP[(TrendState.UNKNOWN, None)] == 0.0

    def test_transitioning_score_magnitude(self):
        assert abs(_SCORE_MAP[(TrendState.TRANSITIONING, None)]) == pytest.approx(0.3)


# ─── Initialization Tests ─────────────────────────────────────────────────────

class TestInitialization:
    def test_initial_state_unknown(self, module_15m):
        assert module_15m.state == TrendState.UNKNOWN

    def test_initial_no_events(self, module_15m):
        assert module_15m.latest_event() is None

    def test_initial_swing_lists_empty(self, module_15m):
        assert module_15m.swing_highs == []
        assert module_15m.swing_lows == []

    def test_pair_stored(self, module_15m):
        assert module_15m.pair == "XAUUSD"

    def test_timeframe_stored(self, module_15m):
        assert module_15m.timeframe == "15m"


# ─── Update / Swing Point Tests (Sprint 2) ───────────────────────────────────

class TestSwingPointDetection:
    """Sprint 2: requires implementation of _detect_swing_points."""

    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_swing_high_detected_in_bullish_trend(self, module_15m):
        candles = _bullish_trend_candles(30)
        module_15m.update(candles)
        assert len(module_15m.swing_highs) > 0

    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_swing_low_detected_in_bearish_trend(self, module_15m):
        candles = _bearish_trend_candles(30)
        module_15m.update(candles)
        assert len(module_15m.swing_lows) > 0

    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_swing_point_has_required_fields(self, module_15m):
        candles = _bullish_trend_candles(30)
        module_15m.update(candles)
        if module_15m.swing_highs:
            sp = module_15m.swing_highs[0]
            assert isinstance(sp.price, float)
            assert isinstance(sp.timestamp, datetime)
            assert sp.kind == "high"

    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_minimum_candles_required(self, module_15m):
        """update() should not crash with fewer than lookback*2+1 candles."""
        candles = _bullish_trend_candles(5)
        module_15m.update(candles)  # Should not raise; state stays UNKNOWN
        assert module_15m.state == TrendState.UNKNOWN


# ─── BOS Detection Tests (Sprint 2) ──────────────────────────────────────────

class TestBOSDetection:
    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_bullish_bos_detected(self, module_15m):
        """In established bullish trend, closing above recent swing high = BOS."""
        candles = _bullish_trend_candles(40)
        module_15m.update(candles)
        events = [e for e in module_15m.events if e.event == StructureEvent.BOS_BULLISH]
        assert len(events) > 0

    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_bearish_bos_detected(self, module_15m):
        candles = _bearish_trend_candles(40)
        module_15m.update(candles)
        events = [e for e in module_15m.events if e.event == StructureEvent.BOS_BEARISH]
        assert len(events) > 0

    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_bos_score_positive_bullish(self, module_15m):
        candles = _bullish_trend_candles(40)
        module_15m.update(candles)
        score = module_15m.score()
        assert score > 0.0


# ─── CHoCH Detection Tests (Sprint 2) ────────────────────────────────────────

class TestCHoCHDetection:
    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_choch_requires_displacement(self, module_15m):
        """CHoCH with displacement < 1.5x ATR should be filtered as noise."""
        pass  # Sprint 2: build specific candle sequence and verify

    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_bearish_choch_from_bullish_trend(self, module_15m):
        """After bullish trend, price breaks below swing low = bearish CHoCH."""
        pass  # Sprint 2: build specific candle sequence

    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_choch_triggers_transitioning_state(self, module_15m):
        """First CHoCH should put module in TRANSITIONING state."""
        pass

    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_second_choch_confirms_new_trend(self, module_15m):
        """Second CHoCH in same direction confirms trend reversal."""
        pass


# ─── State Machine Tests (Sprint 2) ──────────────────────────────────────────

class TestStateMachine:
    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_ranging_state_from_oscillating_candles(self, module_15m):
        candles = _ranging_candles(40)
        module_15m.update(candles)
        assert module_15m.state == TrendState.RANGING

    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_score_zero_in_ranging(self, module_15m):
        candles = _ranging_candles(40)
        module_15m.update(candles)
        assert module_15m.score() == pytest.approx(0.0)

    @pytest.mark.skip(reason="Implement in Sprint 2")
    def test_transitioning_score_abs_value(self, module_15m):
        """TRANSITIONING state score should be ±0.3."""
        pass


# ─── Score Helper Tests ───────────────────────────────────────────────────────

class TestScoreHelper:
    def test_score_from_state_unknown_returns_zero(self, module_15m):
        """_score_from_state() with UNKNOWN state and no events = 0.0."""
        assert module_15m._score_from_state() == pytest.approx(0.0)

    def test_latest_event_none_initially(self, module_15m):
        assert module_15m.latest_event() is None
