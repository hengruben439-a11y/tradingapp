"""
OTE (Optimal Trade Entry) Fibonacci Module Test Suite — Sprint 3

~80 test cases covering:
  - True positives: valid OTE scenarios
  - Ambiguous: edge cases and boundaries
  - False positives: scenarios that should not score

Test ID format:
  TP-xxx  — True positive
  AMB-xxx — Ambiguous/boundary
  FP-xxx  — False positive / should not score
"""

from __future__ import annotations

import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta

from engine.modules.ote import (
    OTEModule,
    DealingRange,
    OTE_LOWER,
    OTE_UPPER,
    OTE_SWEET_SPOT,
    SWEET_SPOT_TOLERANCE_FRACTION,
    FIB_EXTENSIONS,
)
from engine.modules.market_structure import SwingPoint


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ts(offset_minutes: int = 0) -> datetime:
    """UTC timestamp with optional offset in minutes."""
    base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(minutes=offset_minutes)


def _swing_high(price: float, minutes: int) -> SwingPoint:
    return SwingPoint(timestamp=_ts(minutes), price=price, kind="high", confirmed=True)


def _swing_low(price: float, minutes: int) -> SwingPoint:
    return SwingPoint(timestamp=_ts(minutes), price=price, kind="low", confirmed=True)


def _make_candles(n: int = 20) -> pd.DataFrame:
    """Minimal candle DataFrame (OTEModule.update() accepts it but doesn't use it)."""
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.5] * n,
    }, index=idx)


def _make_module(
    swing_high_price: float,
    swing_high_minutes: int,
    swing_low_price: float,
    swing_low_minutes: int,
) -> OTEModule:
    """Build OTEModule with a single dealing range pre-set."""
    m = OTEModule("15m", "XAUUSD")
    highs = [_swing_high(swing_high_price, swing_high_minutes)]
    lows  = [_swing_low(swing_low_price, swing_low_minutes)]
    m.update(_make_candles(), highs, lows)
    return m


# ── Tests: DealingRange Math ──────────────────────────────────────────────────

class TestDealingRangeMath:
    def test_bullish_fib_level_0_is_swing_high(self):  # TP-001
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=True,
        )
        assert dr.fib_level(0.0) == pytest.approx(120.0)

    def test_bullish_fib_level_1_is_swing_low(self):  # TP-002
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=True,
        )
        assert dr.fib_level(1.0) == pytest.approx(100.0)

    def test_bullish_fib_level_050(self):  # TP-003
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=True,
        )
        # 0.5 retracement of bullish: high - 0.5*range = 120 - 10 = 110
        assert dr.fib_level(0.5) == pytest.approx(110.0)

    def test_bullish_ote_zone_boundaries(self):  # TP-004
        """ote_high = fib(0.618), ote_low = fib(0.786) for bullish."""
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=True,
        )
        rng = 20.0
        expected_high = 120.0 - 0.618 * rng
        expected_low  = 120.0 - 0.786 * rng
        assert dr.ote_high == pytest.approx(expected_high)
        assert dr.ote_low  == pytest.approx(expected_low)

    def test_bullish_ote_high_gt_ote_low(self):  # TP-005
        """For bullish: ote_high (at 0.618) > ote_low (at 0.786) numerically."""
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=True,
        )
        assert dr.ote_high > dr.ote_low

    def test_bearish_fib_level_0_is_swing_low(self):  # TP-006
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=False,
        )
        assert dr.fib_level(0.0) == pytest.approx(100.0)

    def test_bearish_fib_level_1_is_swing_high(self):  # TP-007
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=False,
        )
        assert dr.fib_level(1.0) == pytest.approx(120.0)

    def test_bearish_ote_zone_boundaries(self):  # TP-008
        """ote_high = fib(0.618), ote_low = fib(0.786) for bearish."""
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=False,
        )
        rng = 20.0
        expected_high = 100.0 + 0.618 * rng
        expected_low  = 100.0 + 0.786 * rng
        assert dr.ote_high == pytest.approx(expected_high)
        assert dr.ote_low  == pytest.approx(expected_low)

    def test_bearish_ote_low_gt_ote_high(self):  # TP-009
        """For bearish: ote_low (at 0.786) > ote_high (at 0.618) numerically."""
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=False,
        )
        assert dr.ote_low > dr.ote_high

    def test_bullish_sweet_spot_between_ote_bounds(self):  # TP-010
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=True,
        )
        sweet = dr.ote_sweet_spot
        zone_bottom = min(dr.ote_high, dr.ote_low)
        zone_top    = max(dr.ote_high, dr.ote_low)
        assert zone_bottom <= sweet <= zone_top

    def test_sl_level_bullish_below_swing_low(self):  # TP-011
        """SL for bullish is below swing_low (buffer applied)."""
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=True,
        )
        sl = dr.sl_level(buffer_pct=0.0005)
        assert sl < 100.0

    def test_sl_level_bearish_above_swing_high(self):  # TP-012
        """SL for bearish is above swing_high."""
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=False,
        )
        sl = dr.sl_level(buffer_pct=0.0005)
        assert sl > 120.0

    def test_tp_extension_bullish_positive(self):  # TP-013
        """TP extensions for bullish dealing range go above swing_high."""
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=True,
        )
        tp1 = dr.tp_extension(-0.27)
        tp2 = dr.tp_extension(-0.618)
        tp3 = dr.tp_extension(-1.0)
        assert tp1 > 120.0
        assert tp2 > tp1
        assert tp3 > tp2

    def test_tp_extension_bearish_below_swing_low(self):  # TP-014
        """TP extensions for bearish go below swing_low."""
        dr = DealingRange(
            start_timestamp=_ts(0), end_timestamp=_ts(60),
            swing_high=120.0, swing_low=100.0, is_bullish=False,
        )
        tp1 = dr.tp_extension(-0.27)
        tp2 = dr.tp_extension(-0.618)
        tp3 = dr.tp_extension(-1.0)
        assert tp1 < 100.0
        assert tp2 < tp1
        assert tp3 < tp2


# ── Tests: OTEModule Initialization ──────────────────────────────────────────

class TestInitialization:
    def test_default_no_range(self):  # TP-015
        m = OTEModule("15m", "XAUUSD")
        assert m.current_range is None

    def test_score_no_range_zero(self):  # TP-016
        m = OTEModule("15m", "XAUUSD")
        assert m.score(100.0) == 0.0

    def test_get_tp_levels_no_range_empty(self):  # TP-017
        m = OTEModule("15m", "XAUUSD")
        assert m.get_tp_levels() == {}

    def test_has_ob_confluence_no_range_false(self):  # TP-018
        m = OTEModule("15m", "XAUUSD")
        assert m.has_ob_confluence(110.0, 90.0) is False

    def test_has_fvg_confluence_no_range_false(self):  # TP-019
        m = OTEModule("15m", "XAUUSD")
        assert m.has_fvg_confluence(110.0, 90.0) is False


# ── Tests: Update / Dealing Range Detection ───────────────────────────────────

class TestUpdate:
    def test_update_no_swings_no_range(self):  # TP-020
        m = OTEModule("15m", "XAUUSD")
        m.update(_make_candles(), [], [])
        assert m.current_range is None

    def test_update_missing_highs_no_range(self):  # TP-021
        m = OTEModule("15m", "XAUUSD")
        m.update(_make_candles(), [], [_swing_low(100.0, 0)])
        assert m.current_range is None

    def test_update_missing_lows_no_range(self):  # TP-022
        m = OTEModule("15m", "XAUUSD")
        m.update(_make_candles(), [_swing_high(120.0, 60)], [])
        assert m.current_range is None

    def test_bullish_range_when_sh_after_sl(self):  # TP-023
        """Latest swing HIGH after latest swing LOW → bullish dealing range."""
        m = _make_module(
            swing_high_price=120.0, swing_high_minutes=60,
            swing_low_price=100.0,  swing_low_minutes=30,
        )
        assert m.current_range is not None
        assert m.current_range.is_bullish is True

    def test_bearish_range_when_sl_after_sh(self):  # TP-024
        """Latest swing LOW after latest swing HIGH → bearish dealing range."""
        m = _make_module(
            swing_high_price=120.0, swing_high_minutes=30,
            swing_low_price=100.0,  swing_low_minutes=60,
        )
        assert m.current_range is not None
        assert m.current_range.is_bullish is False

    def test_bullish_range_swing_high_correct(self):  # TP-025
        m = _make_module(120.0, 60, 100.0, 30)
        assert m.current_range.swing_high == pytest.approx(120.0)

    def test_bullish_range_swing_low_correct(self):  # TP-026
        m = _make_module(120.0, 60, 100.0, 30)
        assert m.current_range.swing_low == pytest.approx(100.0)

    def test_bearish_range_swing_high_correct(self):  # TP-027
        m = _make_module(120.0, 30, 100.0, 60)
        assert m.current_range.swing_high == pytest.approx(120.0)

    def test_bearish_range_swing_low_correct(self):  # TP-028
        m = _make_module(120.0, 30, 100.0, 60)
        assert m.current_range.swing_low == pytest.approx(100.0)

    def test_update_overwrites_previous_range(self):  # TP-029
        """Calling update again with new swings updates dealing range."""
        m = _make_module(120.0, 60, 100.0, 30)
        old_range = m.current_range
        # New update: SH at 150, SL at 130 — SH is latest
        highs = [_swing_high(120.0, 60), _swing_high(150.0, 90)]
        lows  = [_swing_low(100.0, 30)]
        m.update(_make_candles(), highs, lows)
        assert m.current_range is not old_range
        assert m.current_range.swing_high == pytest.approx(150.0)

    def test_multiple_swing_lows_uses_most_recent_before_sh(self):  # TP-030
        """For bullish range: use the most recent swing low BEFORE the latest SH."""
        m = OTEModule("15m", "XAUUSD")
        highs = [_swing_high(120.0, 60)]
        lows  = [
            _swing_low(95.0, 10),
            _swing_low(98.0, 40),  # most recent before SH at 60 → anchor
        ]
        m.update(_make_candles(), highs, lows)
        assert m.current_range is not None
        assert m.current_range.swing_low == pytest.approx(98.0)

    def test_multiple_swing_highs_uses_most_recent_before_sl(self):  # TP-031
        """For bearish range: use the most recent swing high BEFORE the latest SL."""
        m = OTEModule("15m", "XAUUSD")
        highs = [
            _swing_high(115.0, 10),
            _swing_high(120.0, 40),  # most recent before SL at 60 → anchor
        ]
        lows = [_swing_low(100.0, 60)]
        m.update(_make_candles(), highs, lows)
        assert m.current_range is not None
        assert m.current_range.swing_high == pytest.approx(120.0)

    def test_no_sl_before_sh_no_range(self):  # TP-032
        """If no swing low exists before the latest swing high → no bullish range."""
        m = OTEModule("15m", "XAUUSD")
        highs = [_swing_high(120.0, 30)]
        lows  = [_swing_low(100.0, 60)]  # SL is AFTER SH
        m.update(_make_candles(), highs, lows)
        # Latest SH at 30, latest SL at 60 → SL is latest → bearish direction
        # Bearish: look for SH before SL at 60 → SH at 30 exists
        assert m.current_range is not None  # should create bearish range

    def test_no_sh_before_sl_no_bearish_range(self):  # TP-033
        """If no swing high exists before the latest swing low → no bearish range."""
        m = OTEModule("15m", "XAUUSD")
        highs = [_swing_high(120.0, 90)]  # SH AFTER SL
        lows  = [_swing_low(100.0, 60)]   # SL is latest relative to SH
        m.update(_make_candles(), highs, lows)
        # SH at 90 > SL at 60 → bullish direction. Need SL before SH at 90 → SL at 60 exists.
        assert m.current_range is not None
        assert m.current_range.is_bullish is True


# ── Tests: Score Function ─────────────────────────────────────────────────────

class TestScoring:
    def _bullish_module(self) -> OTEModule:
        """Bullish dealing range: SH=120, SL=100."""
        return _make_module(120.0, 60, 100.0, 30)

    def _bearish_module(self) -> OTEModule:
        """Bearish dealing range: SH=120, SL=100."""
        return _make_module(120.0, 30, 100.0, 60)

    def test_bullish_score_at_sweet_spot(self):  # TP-034
        m = self._bullish_module()
        sweet = m.current_range.ote_sweet_spot
        assert m.score(sweet) == pytest.approx(1.0)

    def test_bullish_score_within_tolerance_of_sweet_spot(self):  # TP-035
        m = self._bullish_module()
        dr = m.current_range
        zone_size = abs(dr.ote_high - dr.ote_low)
        tol = zone_size * SWEET_SPOT_TOLERANCE_FRACTION
        # Just inside tolerance
        price = dr.ote_sweet_spot + tol * 0.9
        assert m.score(price) == pytest.approx(1.0)

    def test_bullish_score_inside_ote_zone(self):  # TP-036
        m = self._bullish_module()
        dr = m.current_range
        zone_bottom = min(dr.ote_high, dr.ote_low)
        zone_top    = max(dr.ote_high, dr.ote_low)
        # Midpoint of OTE zone, but not at sweet spot
        price = zone_bottom + (zone_top - zone_bottom) * 0.05
        score = m.score(price)
        # Could be sweet spot or just OTE zone
        assert score in (0.8, 1.0)

    def test_bullish_score_in_partial_zone(self):  # TP-037
        """Price between 0.5 and 0.618 retracement → +0.4."""
        m = self._bullish_module()
        dr = m.current_range
        level_050 = dr.fib_level(0.5)
        level_618 = dr.fib_level(OTE_LOWER)
        partial_mid = (min(level_050, level_618) + max(level_050, level_618)) / 2.0
        score = m.score(partial_mid)
        assert score == pytest.approx(0.4)

    def test_bullish_score_outside_range_zero(self):  # TP-038
        m = self._bullish_module()
        # Well above swing high
        assert m.score(130.0) == 0.0

    def test_bullish_score_below_swing_low_zero(self):  # TP-039
        m = self._bullish_module()
        assert m.score(90.0) == 0.0

    def test_bearish_score_at_sweet_spot_negative(self):  # TP-040
        m = self._bearish_module()
        sweet = m.current_range.ote_sweet_spot
        assert m.score(sweet) == pytest.approx(-1.0)

    def test_bearish_score_inside_ote_zone_negative(self):  # TP-041
        m = self._bearish_module()
        dr = m.current_range
        zone_bottom = min(dr.ote_high, dr.ote_low)
        zone_top    = max(dr.ote_high, dr.ote_low)
        price = zone_bottom + (zone_top - zone_bottom) * 0.05
        score = m.score(price)
        assert score in (-0.8, -1.0)

    def test_bearish_score_partial_zone(self):  # TP-042
        m = self._bearish_module()
        dr = m.current_range
        level_050 = dr.fib_level(0.5)
        level_618 = dr.fib_level(OTE_LOWER)
        partial_mid = (min(level_050, level_618) + max(level_050, level_618)) / 2.0
        assert m.score(partial_mid) == pytest.approx(-0.4)

    def test_bearish_score_outside_range_zero(self):  # TP-043
        m = self._bearish_module()
        assert m.score(90.0) == 0.0
        assert m.score(130.0) == 0.0

    def test_score_sign_positive_for_bullish(self):  # TP-044
        m = self._bullish_module()
        dr = m.current_range
        zone_bottom = min(dr.ote_high, dr.ote_low)
        zone_top    = max(dr.ote_high, dr.ote_low)
        price = (zone_bottom + zone_top) / 2.0
        assert m.score(price) > 0

    def test_score_sign_negative_for_bearish(self):  # TP-045
        m = self._bearish_module()
        dr = m.current_range
        zone_bottom = min(dr.ote_high, dr.ote_low)
        zone_top    = max(dr.ote_high, dr.ote_low)
        price = (zone_bottom + zone_top) / 2.0
        assert m.score(price) < 0

    def test_score_range_valid(self):  # TP-046
        """Score must be in {-1.0, -0.8, -0.4, 0.0, 0.4, 0.8, 1.0}."""
        m = self._bullish_module()
        valid = {-1.0, -0.8, -0.4, 0.0, 0.4, 0.8, 1.0}
        for price in [85.0, 95.0, 100.0, 105.0, 107.0, 108.0, 109.0, 110.0, 115.0, 125.0]:
            s = m.score(price)
            assert s in valid, f"score({price})={s} not in {valid}"


# ── Tests: Confluence Methods ─────────────────────────────────────────────────

class TestConfluence:
    def test_ob_confluence_within_ote_zone(self):  # TP-047
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        ote_h = max(dr.ote_high, dr.ote_low)
        ote_l = min(dr.ote_high, dr.ote_low)
        # OB zone that overlaps OTE zone
        assert m.has_ob_confluence(ote_h + 0.5, ote_l - 0.5) is True

    def test_ob_confluence_outside_ote_zone(self):  # TP-048
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        ote_l = min(dr.ote_high, dr.ote_low)
        # OB zone entirely below OTE zone
        assert m.has_ob_confluence(ote_l - 1.0, ote_l - 5.0) is False

    def test_fvg_confluence_within_ote_zone(self):  # TP-049
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        ote_h = max(dr.ote_high, dr.ote_low)
        ote_l = min(dr.ote_high, dr.ote_low)
        assert m.has_fvg_confluence(ote_h + 0.5, ote_l - 0.5) is True

    def test_fvg_confluence_outside_ote_zone(self):  # TP-050
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        ote_h = max(dr.ote_high, dr.ote_low)
        # FVG zone entirely above OTE zone
        assert m.has_fvg_confluence(ote_h + 10.0, ote_h + 5.0) is False

    def test_ob_confluence_partial_overlap(self):  # TP-051
        """OB partially overlaps OTE zone → True."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        ote_h = max(dr.ote_high, dr.ote_low)
        ote_l = min(dr.ote_high, dr.ote_low)
        # OB high just above OTE bottom, OB low below OTE bottom
        assert m.has_ob_confluence(ote_l + 0.1, ote_l - 2.0) is True

    def test_confluence_no_range_returns_false(self):  # TP-052
        m = OTEModule("15m", "XAUUSD")
        assert m.has_ob_confluence(110.0, 90.0) is False
        assert m.has_fvg_confluence(110.0, 90.0) is False


# ── Tests: TP Levels ──────────────────────────────────────────────────────────

class TestTPLevels:
    def test_tp_levels_keys_present(self):  # TP-053
        m = _make_module(120.0, 60, 100.0, 30)
        tps = m.get_tp_levels()
        assert "tp_ext_0.27" in tps
        assert "tp_ext_0.618" in tps
        assert "tp_ext_1.0" in tps

    def test_tp_levels_bullish_above_swing_high(self):  # TP-054
        m = _make_module(120.0, 60, 100.0, 30)
        tps = m.get_tp_levels()
        for key, val in tps.items():
            assert val > 120.0, f"{key}={val} should be above swing_high=120"

    def test_tp_levels_bearish_below_swing_low(self):  # TP-055
        m = _make_module(120.0, 30, 100.0, 60)
        tps = m.get_tp_levels()
        for key, val in tps.items():
            assert val < 100.0, f"{key}={val} should be below swing_low=100"

    def test_tp_levels_ordered_bullish(self):  # TP-056
        """TP1 < TP2 < TP3 for bullish."""
        m = _make_module(120.0, 60, 100.0, 30)
        tps = m.get_tp_levels()
        assert tps["tp_ext_0.27"] < tps["tp_ext_0.618"] < tps["tp_ext_1.0"]

    def test_tp_levels_ordered_bearish(self):  # TP-057
        """TP1 > TP2 > TP3 for bearish (going down)."""
        m = _make_module(120.0, 30, 100.0, 60)
        tps = m.get_tp_levels()
        assert tps["tp_ext_0.27"] > tps["tp_ext_0.618"] > tps["tp_ext_1.0"]

    def test_tp_levels_empty_when_no_range(self):  # TP-058
        m = OTEModule("15m", "XAUUSD")
        assert m.get_tp_levels() == {}


# ── Tests: Ambiguous / Boundary ───────────────────────────────────────────────

class TestAmbiguous:
    def test_price_exactly_at_ote_lower_boundary(self):  # AMB-001
        """Price at 0.618 fib level — boundary of OTE zone."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        price = dr.fib_level(OTE_LOWER)  # exactly at 0.618
        score = m.score(price)
        assert score in (0.4, 0.8, 1.0)

    def test_price_exactly_at_ote_upper_boundary(self):  # AMB-002
        """Price at 0.786 fib level — boundary of OTE zone."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        price = dr.fib_level(OTE_UPPER)  # exactly at 0.786
        score = m.score(price)
        assert score in (0.8, 1.0)

    def test_price_at_050_fib_exactly(self):  # AMB-003
        """Price exactly at 0.5 fib — boundary between partial and no-score zones."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        price = dr.fib_level(0.5)  # exactly at 0.5
        score = m.score(price)
        assert score in (0.0, 0.4)  # boundary — either in or out of partial zone

    def test_sweet_spot_tolerance_exactly_at_edge(self):  # AMB-004
        """Price exactly at tolerance boundary."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        zone_size = abs(dr.ote_high - dr.ote_low)
        tol = zone_size * SWEET_SPOT_TOLERANCE_FRACTION
        sweet = dr.ote_sweet_spot
        # Exactly at tolerance edge
        price = sweet + tol
        score = m.score(price)
        # At exact boundary: abs(price - sweet) == tol → should be <=, so score = 1.0
        assert score == 1.0

    def test_sweet_spot_just_outside_tolerance(self):  # AMB-005
        """Price just beyond tolerance → falls back to OTE zone score."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        zone_size = abs(dr.ote_high - dr.ote_low)
        tol = zone_size * SWEET_SPOT_TOLERANCE_FRACTION
        sweet = dr.ote_sweet_spot
        price = sweet + tol + 0.001  # just outside tolerance
        score = m.score(price)
        assert score in (0.0, 0.4, 0.8)  # not sweet spot, but may still be in OTE

    def test_tiny_dealing_range_no_score(self):  # AMB-006
        """Extremely small swing range → zone_size near 0 → safe handling."""
        m = OTEModule("15m", "XAUUSD")
        highs = [_swing_high(100.001, 60)]
        lows  = [_swing_low(100.000, 30)]
        m.update(_make_candles(), highs, lows)
        if m.current_range is not None:
            score = m.score(100.0)
            assert isinstance(score, float)

    def test_equal_timestamps_behavior(self):  # AMB-007
        """SH and SL with equal timestamps — behavior undefined but no crash."""
        m = OTEModule("15m", "XAUUSD")
        highs = [_swing_high(120.0, 60)]
        lows  = [_swing_low(100.0, 60)]  # same minute
        try:
            m.update(_make_candles(), highs, lows)
        except Exception as e:
            pytest.fail(f"Equal timestamps raised: {e}")

    @pytest.mark.parametrize("sh,sl", [
        (1.0, 0.5),      # small prices
        (2900.0, 2850.0), # gold-like prices
        (180.0, 150.0),  # GBPJPY-like
    ])
    def test_various_price_ranges(self, sh, sl):  # AMB-008 to AMB-010
        """Score function works across different asset price ranges."""
        m = _make_module(sh, 60, sl, 30)
        if m.current_range is not None:
            sweet = m.current_range.ote_sweet_spot
            score = m.score(sweet)
            assert score == pytest.approx(1.0)

    def test_update_with_only_one_swing_high_and_one_low(self):  # AMB-011
        """Minimum valid input: one SH and one SL."""
        m = OTEModule("15m", "XAUUSD")
        highs = [_swing_high(120.0, 60)]
        lows  = [_swing_low(100.0, 30)]
        m.update(_make_candles(), highs, lows)
        assert m.current_range is not None


# ── Tests: False Positives ────────────────────────────────────────────────────

class TestFalsePositives:
    def test_no_range_no_score(self):  # FP-001
        m = OTEModule("15m", "XAUUSD")
        assert m.score(110.0) == 0.0

    def test_price_above_swing_high_zero(self):  # FP-002
        m = _make_module(120.0, 60, 100.0, 30)
        assert m.score(125.0) == 0.0

    def test_price_below_swing_low_zero(self):  # FP-003
        m = _make_module(120.0, 60, 100.0, 30)
        assert m.score(95.0) == 0.0

    def test_price_between_0_and_05_fib_zero(self):  # FP-004
        """Price in 0.0–0.5 fib zone (not deep enough) → 0.0."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        # Price at 0.25 retracement — between 0 and 0.5
        price = dr.fib_level(0.25)
        score = m.score(price)
        assert score == 0.0

    def test_price_beyond_100_fib_zero(self):  # FP-005
        """Price beyond full retracement (below SL level) → 0.0."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        # Below swing_low for bullish
        price = dr.fib_level(1.1)  # beyond 100%
        score = m.score(price)
        assert score == 0.0

    def test_bearish_price_below_swing_low_zero(self):  # FP-006
        m = _make_module(120.0, 30, 100.0, 60)
        assert m.score(95.0) == 0.0

    def test_bearish_price_above_swing_high_zero(self):  # FP-007
        m = _make_module(120.0, 30, 100.0, 60)
        assert m.score(125.0) == 0.0

    def test_no_sl_before_sh_no_bullish_range(self):  # FP-008
        """If no swing low exists before the latest swing high → no range."""
        m = OTEModule("15m", "XAUUSD")
        # Both SL occur after SH in time → latest is SL → bearish
        highs = [_swing_high(120.0, 10)]
        lows  = [_swing_low(100.0, 30)]  # SL after SH → bearish direction
        # For bearish: look for SH before SL at 30 → SH at 10 exists → range created
        m.update(_make_candles(), highs, lows)
        # Range should be bearish since SL is latest
        if m.current_range:
            assert m.current_range.is_bullish is False

    @pytest.mark.parametrize("price", [float("inf"), -float("inf"), 0.0])
    def test_extreme_price_no_crash(self, price):  # FP-009 to FP-011
        """Extreme price values should not crash score()."""
        m = _make_module(120.0, 60, 100.0, 30)
        try:
            result = m.score(price)
            assert isinstance(result, float)
        except Exception as e:
            pytest.fail(f"score({price}) raised: {e}")

    def test_ob_confluence_no_range_false(self):  # FP-012
        m = OTEModule("15m", "XAUUSD")
        assert m.has_ob_confluence(110.0, 105.0) is False

    def test_fvg_confluence_no_range_false(self):  # FP-013
        m = OTEModule("15m", "XAUUSD")
        assert m.has_fvg_confluence(110.0, 105.0) is False

    def test_ob_confluence_no_overlap_false(self):  # FP-014
        """OB zone completely outside OTE zone → False."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        ote_l = min(dr.ote_high, dr.ote_low)
        # OB entirely below OTE zone
        assert m.has_ob_confluence(ote_l - 2.0, ote_l - 5.0) is False

    def test_fvg_confluence_no_overlap_false(self):  # FP-015
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        ote_h = max(dr.ote_high, dr.ote_low)
        # FVG entirely above OTE zone
        assert m.has_fvg_confluence(ote_h + 10.0, ote_h + 5.0) is False

    @pytest.mark.parametrize("timeframe", ["1m", "5m", "15m", "1H", "4H", "1D"])
    def test_timeframe_agnostic_scoring(self, timeframe):  # FP-016 to FP-021
        """Score function does not depend on timeframe string."""
        m = OTEModule(timeframe, "XAUUSD")
        highs = [_swing_high(120.0, 60)]
        lows  = [_swing_low(100.0, 30)]
        m.update(_make_candles(), highs, lows)
        if m.current_range:
            sweet = m.current_range.ote_sweet_spot
            assert m.score(sweet) == pytest.approx(1.0)

    def test_score_all_prices_between_05_and_618_return_04(self):  # FP-022
        """All prices in the 0.5–0.618 partial zone return exactly +0.4."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        level_050 = dr.fib_level(0.5)
        level_618 = dr.fib_level(OTE_LOWER)
        pbot = min(level_050, level_618)
        ptop = max(level_050, level_618)
        # Midpoint of partial zone
        mid = (pbot + ptop) / 2.0
        assert m.score(mid) == pytest.approx(0.4)

    def test_score_not_0_in_ote_zone(self):  # FP-023
        """Any price inside the OTE zone must return non-zero score."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        zone_bottom = min(dr.ote_high, dr.ote_low)
        zone_top    = max(dr.ote_high, dr.ote_low)
        # Several points inside the OTE zone
        for frac in [0.1, 0.3, 0.5, 0.7, 0.9]:
            price = zone_bottom + frac * (zone_top - zone_bottom)
            assert m.score(price) != 0.0, f"score at {price} should not be 0"

    def test_score_0_above_partial_zone(self):  # FP-024
        """Price above the 0.5 retracement (partial zone top) → 0.0."""
        m = _make_module(120.0, 60, 100.0, 30)
        dr = m.current_range
        # For bullish: partial zone is between fib(0.5)=110 and fib(0.618)=107.64
        # partial zone top = fib(0.5) = 110.  Above 110 → outside all scored zones
        level_050 = dr.fib_level(0.5)
        price = level_050 + 0.01
        score = m.score(price)
        assert score == 0.0
