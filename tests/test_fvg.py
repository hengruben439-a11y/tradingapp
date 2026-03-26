"""
FVG Module Tests — Sprint 3 deliverable.

Test strategy (from Sprint 3 spec):
    100 clear textbook setups (true positives — clean FVGs that held)
    100 ambiguous/borderline cases (messy data, tiny FVGs, borderline size)
    100 false positive cases (FVGs that looked valid but price blew through)

Sprint 1: scaffolding and helpers.
Sprint 3: full 300 labeled test cases added alongside implementation.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from engine.modules.fvg import FVGModule, FVGKind, FVGStatus, FairValueGap


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_candles(ohlcv: list[tuple[float, float, float, float, float]]) -> pd.DataFrame:
    """
    Build candles from (open, high, low, close, volume) tuples.
    Index is UTC-aware minute bars.
    """
    n = len(ohlcv)
    index = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    o, h, l, c, v = zip(*ohlcv)
    return pd.DataFrame(
        {"open": o, "high": h, "low": l, "close": c, "volume": v},
        index=index,
    )


def _make_atr(candles: pd.DataFrame, constant: float = 2.0) -> pd.Series:
    """Return a constant ATR series aligned to candles index."""
    return pd.Series([constant] * len(candles), index=candles.index)


def _bullish_fvg_candles(gap_size: float = 3.0) -> pd.DataFrame:
    """
    Three-candle bullish FVG:
        Candle 1: bearish, high=100
        Candle 2: large bullish (displacement)
        Candle 3: bullish, low > Candle1.high  (gap = FVG zone)
    """
    c1_high = 100.0
    c3_low = c1_high + gap_size   # gap_size above c1 high = FVG
    candles = [
        (99.0, c1_high, 98.0, 98.5, 1000),       # Candle 1: bearish
        (98.5, 106.0, 98.0, 105.5, 5000),         # Candle 2: big bullish
        (105.5, 107.0, c3_low, 106.5, 2000),      # Candle 3: bullish (gap above c1.high)
    ]
    return _make_candles(candles)


def _bearish_fvg_candles(gap_size: float = 3.0) -> pd.DataFrame:
    """
    Three-candle bearish FVG:
        Candle 1: bullish, low=100
        Candle 2: large bearish displacement
        Candle 3: bearish, high < Candle1.low
    """
    c1_low = 100.0
    c3_high = c1_low - gap_size
    candles = [
        (101.0, 102.0, c1_low, 101.5, 1000),     # Candle 1: bullish
        (101.5, 102.0, 94.0, 94.5, 5000),         # Candle 2: big bearish
        (94.5, c3_high, 93.0, 93.5, 2000),        # Candle 3: bearish (gap below c1.low)
    ]
    return _make_candles(candles)


def _too_small_fvg_candles() -> pd.DataFrame:
    """FVG where gap size < min_size_atr_multiple * ATR (should be filtered)."""
    candles = [
        (99.0, 100.0, 98.0, 98.5, 1000),
        (98.5, 102.0, 98.0, 101.5, 5000),
        (101.5, 103.0, 100.4, 102.5, 2000),  # gap = 0.4 (tiny)
    ]
    return _make_candles(candles)


@pytest.fixture
def fvg_15m() -> FVGModule:
    return FVGModule(timeframe="15m", pair="XAUUSD", min_size_atr_multiple=1.0)


@pytest.fixture
def fvg_1m() -> FVGModule:
    return FVGModule(timeframe="1m", pair="XAUUSD", min_size_atr_multiple=0.5)


# ─── Initialization Tests ─────────────────────────────────────────────────────

class TestInitialization:
    def test_starts_empty(self, fvg_15m):
        assert fvg_15m.fvgs == []

    def test_no_fvg_returns_none(self, fvg_15m):
        assert fvg_15m.nearest_fvg(100.0) is None

    def test_open_fvgs_empty(self, fvg_15m):
        assert fvg_15m.get_open_fvgs() == []


# ─── Bullish FVG Detection Tests (Sprint 3) ──────────────────────────────────

class TestBullishFVGDetection:
    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_bullish_fvg_detected(self, fvg_15m):
        candles = _bullish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, constant=2.0)  # gap=3.0 >= 1.0*ATR=2.0 ✓
        fvg_15m.update(candles, atr)
        assert len(fvg_15m.fvgs) == 1
        assert fvg_15m.fvgs[0].kind == FVGKind.BULLISH

    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_bullish_fvg_zone_boundaries(self, fvg_15m):
        """FVG top = Candle3.low, FVG bottom = Candle1.high."""
        candles = _bullish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, constant=2.0)
        fvg_15m.update(candles, atr)
        fvg = fvg_15m.fvgs[0]
        assert fvg.bottom == pytest.approx(100.0)   # Candle1.high
        assert fvg.top == pytest.approx(103.0)       # Candle3.low

    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_too_small_fvg_filtered(self, fvg_15m):
        """FVG smaller than min_size_atr_multiple * ATR should not be stored."""
        candles = _too_small_fvg_candles()
        atr = _make_atr(candles, constant=2.0)  # gap=0.4 < 1.0*2.0=2.0 → filtered
        fvg_15m.update(candles, atr)
        assert len(fvg_15m.fvgs) == 0

    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_fvg_status_starts_open(self, fvg_15m):
        candles = _bullish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, constant=2.0)
        fvg_15m.update(candles, atr)
        assert fvg_15m.fvgs[0].status == FVGStatus.OPEN


# ─── Bearish FVG Detection Tests (Sprint 3) ──────────────────────────────────

class TestBearishFVGDetection:
    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_bearish_fvg_detected(self, fvg_15m):
        candles = _bearish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, constant=2.0)
        fvg_15m.update(candles, atr)
        assert len(fvg_15m.fvgs) == 1
        assert fvg_15m.fvgs[0].kind == FVGKind.BEARISH

    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_bearish_fvg_zone_boundaries(self, fvg_15m):
        """FVG top = Candle1.low, FVG bottom = Candle3.high."""
        candles = _bearish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, constant=2.0)
        fvg_15m.update(candles, atr)
        fvg = fvg_15m.fvgs[0]
        assert fvg.top == pytest.approx(100.0)      # Candle1.low
        assert fvg.bottom == pytest.approx(97.0)    # Candle3.high


# ─── Fill Status Tests (Sprint 3) ────────────────────────────────────────────

class TestFillStatus:
    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_partial_fill_when_price_enters_zone(self, fvg_15m):
        """Price entering (but not exiting) the FVG marks it PARTIALLY_FILLED."""
        pass

    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_full_fill_when_price_closes_through(self, fvg_15m):
        """Price closing through entire FVG marks it FILLED."""
        pass

    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_midpoint_is_consequent_encroachment(self, fvg_15m):
        """Midpoint should be exactly (top + bottom) / 2."""
        candles = _bullish_fvg_candles(gap_size=4.0)  # bottom=100, top=104, mid=102
        atr = _make_atr(candles, constant=2.0)
        fvg_15m.update(candles, atr)
        assert fvg_15m.fvgs[0].midpoint == pytest.approx(102.0)


# ─── Unicorn Detection Tests (Sprint 3) ──────────────────────────────────────

class TestUnicornDetection:
    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_unicorn_when_fvg_overlaps_ob(self, fvg_15m):
        """check_unicorn_overlap returns True when OB and FVG zones intersect."""
        candles = _bullish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, constant=2.0)
        fvg_15m.update(candles, atr)
        # OB zone: 99.5–101.0 overlaps FVG bottom=100 top=103
        assert fvg_15m.check_unicorn_overlap(ob_high=101.0, ob_low=99.5) is True

    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_no_unicorn_when_zones_dont_overlap(self, fvg_15m):
        candles = _bullish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, constant=2.0)
        fvg_15m.update(candles, atr)
        # OB zone: 90–95, well below FVG bottom=100
        assert fvg_15m.check_unicorn_overlap(ob_high=95.0, ob_low=90.0) is False


# ─── Score Tests (Sprint 3) ──────────────────────────────────────────────────

class TestScoring:
    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_score_bullish_fvg_at_price(self, fvg_15m):
        """Price inside open bullish FVG should score +0.7."""
        candles = _bullish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, constant=2.0)
        fvg_15m.update(candles, atr)
        # FVG zone: 100–103; price=101 is inside
        score = fvg_15m.score(current_price=101.0)
        assert score == pytest.approx(0.7)

    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_score_zero_no_fvg(self, fvg_15m):
        assert fvg_15m.score(current_price=100.0) == pytest.approx(0.0)

    @pytest.mark.skip(reason="Implement in Sprint 3")
    def test_score_inverted_fvg_negative(self, fvg_15m):
        """Inverted FVG (resistance) should score negative."""
        pass
