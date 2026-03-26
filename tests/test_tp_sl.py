"""
TP/SL Engine Tests — Sprint 5 deliverable.

Covers:
    - Basic BUY: SL below entry, tp1 < tp2 < tp3 ascending
    - Basic SELL: SL above entry, tp1 > tp2 > tp3 descending
    - TP1 R:R validation: returns None when TP1 cannot achieve 1:1
    - Structural SL preferred when tighter than 1.5x ATR
    - ATR SL used when swing_invalidation is None
    - SL bounded to [1x ATR, 3x ATR]
    - SL buffer applied (further from entry than raw SL)
    - TP close_pct values: 0.40, 0.30, 0.30
    - Fib extension used for TP3 when valid
    - Fallback ATR TPs: ATR fallback TP1 always < 1:1 R:R (returns None) because
      SL = 1.5x ATR + buffer > TP1 = 1.5x ATR.  Tests verify this invariant.
    - Structural TPs used when resistance/support levels provided
    - GBPJPY SL buffer: 7 pips (0.07)
    - XAUUSD SL buffer: 0.05% of entry_price
    - calculate_lot_size sanity checks
    - _price_to_pips: XAUUSD × 10, GBPJPY × 100
    - sl_is_excessive flag
    - used_structural_sl flag
    - used_fallback_tp flag
"""

from __future__ import annotations

import pytest

from engine.signal import Direction, TPLevel
from engine.tp_sl import (
    TPSLEngine,
    TPSLResult,
    SL_DEFAULT_ATR_MULTIPLE,
    SL_BUFFER_XAUUSD_PCT,
    SL_BUFFER_GBPJPY_PIPS,
    SL_MIN_ATR_MULTIPLE,
    SL_MAX_ATR_MULTIPLE,
    TP1_CLOSE_PCT,
    TP2_CLOSE_PCT,
    TP3_CLOSE_PCT,
    TP1_ATR_FALLBACK,
    TP2_ATR_FALLBACK,
    TP3_ATR_FALLBACK,
)

# ─── Standard fixtures ────────────────────────────────────────────────────────
# Resistance/support levels placed well beyond the SL distance so TP1 achieves >= 1:1 R:R.
# With entry=2050, atr=15: SL distance ~23.5, so resistance at 2080+ ensures TP1 rr >= 1.0.

_BUY_RESISTANCES = [2080.0, 2105.0, 2140.0]   # 30, 55, 90 above entry
_SELL_SUPPORTS   = [2020.0, 1995.0, 1960.0]   # 30, 55, 90 below entry


# ─── Helpers ─────────────────────────────────────────────────────────────────

def buy_result(
    entry=2050.0,
    atr=15.0,
    support_levels=None,
    resistance_levels=None,
    fib_extensions=None,
    swing_invalidation=None,
    pair="XAUUSD",
) -> TPSLResult | None:
    """Convenience wrapper for a BUY calculation."""
    engine = TPSLEngine(pair=pair)
    return engine.calculate(
        entry_price=entry,
        direction=Direction.BUY,
        atr=atr,
        support_levels=support_levels if support_levels is not None else [],
        resistance_levels=resistance_levels if resistance_levels is not None else [],
        fib_extensions=fib_extensions or {},
        swing_invalidation=swing_invalidation,
    )


def sell_result(
    entry=2050.0,
    atr=15.0,
    support_levels=None,
    resistance_levels=None,
    fib_extensions=None,
    swing_invalidation=None,
    pair="XAUUSD",
) -> TPSLResult | None:
    """Convenience wrapper for a SELL calculation."""
    engine = TPSLEngine(pair=pair)
    return engine.calculate(
        entry_price=entry,
        direction=Direction.SELL,
        atr=atr,
        support_levels=support_levels if support_levels is not None else [],
        resistance_levels=resistance_levels if resistance_levels is not None else [],
        fib_extensions=fib_extensions or {},
        swing_invalidation=swing_invalidation,
    )


# ─── Basic BUY Direction ─────────────────────────────────────────────────────

class TestBasicBuy:
    """Core directional correctness for BUY signals."""

    def test_buy_sl_below_entry(self):
        """SL must be below entry price for a BUY."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert r.stop_loss < r.entry_price

    def test_buy_tp1_above_entry(self):
        """TP1 must be above entry price for a BUY."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert r.tp1.price > r.entry_price

    def test_buy_tp_levels_ascending(self):
        """TP1 < TP2 < TP3 for a BUY."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert r.tp1.price < r.tp2.price < r.tp3.price

    def test_buy_entry_price_preserved(self):
        """entry_price in result must match the input."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert r.entry_price == pytest.approx(2050.0)

    def test_buy_with_resistance_farther_than_atr_uses_risk_distance_tp1(self):
        """When structural resistance is farther than ATR fallback, TP1 uses 1.0x risk distance.

        The engine picks the MORE CONSERVATIVE (closer) TP1: if structural is farther than
        the ATR fallback (1.5x ATR), it falls back to 1.0x risk_distance as TP1 and marks
        source as 'atr_fallback'. TP2/TP3 then use the structural levels.
        """
        entry = 2050.0
        atr = 15.0
        # ATR fallback TP1 distance = 1.5*15 = 22.5. Resistance at 2080 (30 away) is farther.
        # TP1 = entry + 1.0 * risk_distance (source='atr_fallback'), TP2 = 2080 (structural)
        r = buy_result(entry=entry, atr=atr, resistance_levels=[2080.0, 2105.0, 2140.0])
        assert r is not None
        assert r.tp1.source == "atr_fallback"
        assert r.tp2.source == "structural"
        # TP1 consumed valid_structural[0] (2080), TP2 uses valid_structural[1] (2105)
        assert r.tp2.price == pytest.approx(2105.0)

    def test_buy_tp_close_percentages(self):
        """TP1=40%, TP2=30%, TP3=30%."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert r.tp1.close_pct == pytest.approx(TP1_CLOSE_PCT)
        assert r.tp2.close_pct == pytest.approx(TP2_CLOSE_PCT)
        assert r.tp3.close_pct == pytest.approx(TP3_CLOSE_PCT)

    def test_buy_tp_level_numbers(self):
        """TP levels should be numbered 1, 2, 3."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert r.tp1.level == 1
        assert r.tp2.level == 2
        assert r.tp3.level == 3


# ─── Basic SELL Direction ────────────────────────────────────────────────────

class TestBasicSell:
    """Core directional correctness for SELL signals."""

    def test_sell_sl_above_entry(self):
        """SL must be above entry price for a SELL."""
        r = sell_result(entry=2050.0, atr=15.0, support_levels=_SELL_SUPPORTS)
        assert r is not None
        assert r.stop_loss > r.entry_price

    def test_sell_tp1_below_entry(self):
        """TP1 must be below entry price for a SELL."""
        r = sell_result(entry=2050.0, atr=15.0, support_levels=_SELL_SUPPORTS)
        assert r is not None
        assert r.tp1.price < r.entry_price

    def test_sell_tp_levels_descending(self):
        """TP1 > TP2 > TP3 for a SELL."""
        r = sell_result(entry=2050.0, atr=15.0, support_levels=_SELL_SUPPORTS)
        assert r is not None
        assert r.tp1.price > r.tp2.price > r.tp3.price

    def test_sell_with_support_farther_than_atr_uses_risk_distance_tp1(self):
        """When structural support is farther than ATR fallback, TP1 uses 1.0x risk distance.

        If the nearest support level is farther from entry than 1.5x ATR, the engine conservatively
        uses 1.0x risk_distance as TP1 (source='atr_fallback'), then the structural support as TP2.
        """
        entry = 2050.0
        atr = 15.0
        # ATR fallback TP1 = 22.5 below. Support at 2020 (30 away) is farther → atr_fallback TP1
        r = sell_result(entry=entry, atr=atr, support_levels=[2020.0, 1995.0, 1960.0])
        assert r is not None
        assert r.tp1.source == "atr_fallback"
        assert r.tp2.source == "structural"
        # TP1 consumed valid_structural[0] (2020), TP2 uses valid_structural[1] (1995)
        assert r.tp2.price == pytest.approx(1995.0)

    def test_sell_tp_close_percentages(self):
        """TP1=40%, TP2=30%, TP3=30% for SELL as well."""
        r = sell_result(entry=2050.0, atr=15.0, support_levels=_SELL_SUPPORTS)
        assert r is not None
        assert r.tp1.close_pct == pytest.approx(TP1_CLOSE_PCT)
        assert r.tp2.close_pct == pytest.approx(TP2_CLOSE_PCT)
        assert r.tp3.close_pct == pytest.approx(TP3_CLOSE_PCT)

    def test_sell_entry_price_preserved(self):
        """entry_price in result must match the input."""
        r = sell_result(entry=2050.0, atr=15.0, support_levels=_SELL_SUPPORTS)
        assert r is not None
        assert r.entry_price == pytest.approx(2050.0)


# ─── Stop Loss Calculation ───────────────────────────────────────────────────

class TestStopLossCalculation:
    """Structural vs ATR SL selection and bounding."""

    def test_structural_sl_used_when_tighter(self):
        """Structural SL preferred when it is tighter (closer to entry) than 1.5x ATR."""
        # ATR = 20, 1.5x ATR SL distance = 30. swing_invalidation at 2035 (15 below) is tighter.
        r = buy_result(
            entry=2050.0, atr=20.0,
            resistance_levels=[2090.0, 2120.0, 2160.0],
            swing_invalidation=2035.0,
        )
        assert r is not None
        assert r.used_structural_sl is True

    def test_atr_sl_used_when_no_swing_invalidation(self):
        """When swing_invalidation is None, ATR-based SL is always used."""
        r = buy_result(
            entry=2050.0, atr=15.0,
            resistance_levels=_BUY_RESISTANCES,
            swing_invalidation=None,
        )
        assert r is not None
        assert r.used_structural_sl is False

    def test_atr_sl_used_when_structural_is_wider(self):
        """ATR SL used when structural level is farther from entry than 1.5x ATR."""
        # ATR = 20, 1.5x ATR = 30. swing_invalidation at 2010 (40 below) is wider → use ATR.
        r = buy_result(
            entry=2050.0, atr=20.0,
            resistance_levels=_BUY_RESISTANCES,
            swing_invalidation=2010.0,
        )
        assert r is not None
        assert r.used_structural_sl is False

    def test_sl_capped_at_3x_atr_for_extreme_swing(self):
        """SL is capped at 3x ATR from entry even if structural level is far beyond it."""
        # swing_invalidation very far (100 below entry), ATR = 10 → raw cap = 30 from entry.
        r = buy_result(
            entry=2050.0, atr=10.0,
            resistance_levels=_BUY_RESISTANCES,
            swing_invalidation=1950.0,
        )
        assert r is not None
        # SL should be no more than 3x ATR + buffer below entry
        max_sl_dist = SL_MAX_ATR_MULTIPLE * 10.0 + 2050.0 * SL_BUFFER_XAUUSD_PCT
        assert (r.entry_price - r.stop_loss) <= max_sl_dist + 0.01

    def test_sl_at_least_1x_atr_from_entry(self):
        """SL is never closer to entry than 1x ATR (plus buffer)."""
        # swing_invalidation very close (0.5 below entry), ATR = 10 → min = 10.
        r = buy_result(
            entry=2050.0, atr=10.0,
            resistance_levels=_BUY_RESISTANCES,
            swing_invalidation=2049.5,
        )
        assert r is not None
        min_sl_dist = SL_MIN_ATR_MULTIPLE * 10.0  # 10.0 minimum from entry
        assert (r.entry_price - r.stop_loss) >= min_sl_dist - 0.01

    def test_sl_is_excessive_false_for_normal_sl(self):
        """sl_is_excessive should be False when SL is within 3x ATR."""
        r = buy_result(
            entry=2050.0, atr=15.0,
            resistance_levels=_BUY_RESISTANCES,
            swing_invalidation=2035.0,
        )
        assert r is not None
        assert r.sl_is_excessive is False

    def test_sell_structural_sl_used_when_tighter(self):
        """Structural SL tighter than ATR for SELL: used_structural_sl is True."""
        # ATR = 20, ATR SL = 1.5*20 = 30 above entry. swing_invalidation at 2065 (15 above) is tighter.
        r = sell_result(
            entry=2050.0, atr=20.0,
            support_levels=_SELL_SUPPORTS,
            swing_invalidation=2065.0,
        )
        assert r is not None
        assert r.used_structural_sl is True


# ─── SL Buffer ───────────────────────────────────────────────────────────────

class TestSLBuffer:
    """Stop hunt buffer is added beyond the raw SL level."""

    def test_xauusd_buffer_percentage_based(self):
        """XAUUSD buffer = 0.05% of entry_price, pushes SL further below for BUY."""
        entry = 2000.0
        atr = 20.0
        buffer = entry * SL_BUFFER_XAUUSD_PCT   # 0.05% of 2000 = 1.0
        raw_sl = entry - SL_DEFAULT_ATR_MULTIPLE * atr   # 2000 - 30 = 1970
        expected_sl = raw_sl - buffer   # 1969.0
        r = buy_result(entry=entry, atr=atr, pair="XAUUSD",
                       resistance_levels=[2040.0, 2065.0, 2090.0])
        assert r is not None
        assert r.stop_loss == pytest.approx(expected_sl, abs=0.01)

    def test_gbpjpy_buffer_fixed_pips(self):
        """GBPJPY buffer = 7 pips = 0.07, added below raw SL for BUY."""
        entry = 190.0
        atr = 0.5
        buffer = SL_BUFFER_GBPJPY_PIPS * 0.01   # 7 * 0.01 = 0.07
        raw_sl = entry - SL_DEFAULT_ATR_MULTIPLE * atr   # 189.25
        expected_sl = raw_sl - buffer   # 189.18
        r = buy_result(entry=entry, atr=atr, pair="GBPJPY",
                       resistance_levels=[191.0, 191.8, 192.5])
        assert r is not None
        assert r.stop_loss == pytest.approx(expected_sl, abs=0.001)

    def test_sell_xauusd_buffer_adds_above_raw_sl(self):
        """For a SELL, XAUUSD buffer pushes SL above the raw level."""
        entry = 2000.0
        atr = 20.0
        buffer = entry * SL_BUFFER_XAUUSD_PCT
        raw_sl = entry + SL_DEFAULT_ATR_MULTIPLE * atr   # 2030.0
        expected_sl = raw_sl + buffer   # 2031.0
        r = sell_result(entry=entry, atr=atr, pair="XAUUSD",
                        support_levels=[1960.0, 1935.0, 1900.0])
        assert r is not None
        assert r.stop_loss == pytest.approx(expected_sl, abs=0.01)

    def test_sell_gbpjpy_buffer_adds_above_raw_sl(self):
        """For a SELL, GBPJPY buffer pushes SL above the raw level."""
        entry = 190.0
        atr = 0.5
        buffer = SL_BUFFER_GBPJPY_PIPS * 0.01
        raw_sl = entry + SL_DEFAULT_ATR_MULTIPLE * atr   # 190.75
        expected_sl = raw_sl + buffer   # 190.82
        r = sell_result(entry=entry, atr=atr, pair="GBPJPY",
                        support_levels=[189.0, 188.2, 187.5])
        assert r is not None
        assert r.stop_loss == pytest.approx(expected_sl, abs=0.001)

    def test_sl_is_below_entry_after_buffer_for_buy(self):
        """After adding buffer, SL is still below entry for BUY."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert r.stop_loss < r.entry_price

    def test_sl_is_above_entry_after_buffer_for_sell(self):
        """After adding buffer, SL is still above entry for SELL."""
        r = sell_result(entry=2050.0, atr=15.0, support_levels=_SELL_SUPPORTS)
        assert r is not None
        assert r.stop_loss > r.entry_price


# ─── TP1 R:R Suppression ─────────────────────────────────────────────────────

class TestTP1RRSuppression:
    """Signal is suppressed (returns None) when TP1 cannot achieve 1:1 R:R."""

    def test_returns_none_when_no_structural_levels(self):
        """ATR fallback TP1 = 1.5x ATR, but SL = 1.5x ATR + buffer, so rr < 1.0 → None."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=[])
        assert r is None

    def test_returns_none_when_resistance_too_close(self):
        """Resistance closer than risk distance gives TP1 rr < 1.0 → suppressed."""
        # SL dist ≈ 23.5. Resistance at 2052 (only 2 above entry): rr ≈ 0.085 → None
        r = buy_result(
            entry=2050.0, atr=15.0,
            resistance_levels=[2052.0],
        )
        assert r is None

    def test_returns_result_with_far_enough_resistance(self):
        """Resistance placed beyond SL distance ensures TP1 rr >= 1.0."""
        # SL dist ≈ 23.5. Resistance at 2080 (30 above) → rr ≈ 1.27 ✓
        r = buy_result(
            entry=2050.0, atr=15.0,
            resistance_levels=[2080.0, 2105.0, 2140.0],
        )
        assert r is not None

    def test_tp1_rr_at_least_1_when_result_not_none(self):
        """When a result is returned, TP1 rr_ratio must be >= 1.0."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert r.tp1.rr_ratio >= 1.0

    def test_sell_returns_none_when_no_structural_levels(self):
        """ATR fallback for SELL also produces rr < 1.0 → None."""
        r = sell_result(entry=2050.0, atr=15.0, support_levels=[])
        assert r is None


# ─── Fallback vs Structural TP Labels ───────────────────────────────────────

class TestTPSourceLabels:
    """Source labels on TP levels indicate whether structural or fallback was used."""

    def test_structural_levels_sets_used_fallback_false(self):
        """used_fallback_tp is False when structural levels are provided."""
        r = buy_result(
            entry=2050.0, atr=15.0,
            resistance_levels=_BUY_RESISTANCES,
        )
        assert r is not None
        assert r.used_fallback_tp is False

    def test_tp1_is_atr_fallback_when_structural_is_farther(self):
        """TP1 source is 'atr_fallback' when the nearest resistance is farther than ATR fallback.

        The engine takes the MORE CONSERVATIVE (closer) TP1. When structural is farther, it uses
        1.0x risk_distance instead, marking source as 'atr_fallback'.
        """
        # ATR = 15, fallback TP1 dist = 22.5. Resistance at 2080 (30 away) is farther.
        r = buy_result(
            entry=2050.0, atr=15.0,
            resistance_levels=[2080.0, 2105.0, 2140.0],
        )
        assert r is not None
        assert r.tp1.source == "atr_fallback"

    def test_three_structural_levels_tp2_tp3_use_structural(self):
        """When 3+ structural resistance levels are provided, TP2 and TP3 use structural source."""
        # TP1 may use atr_fallback (if structural is farther), but TP2/TP3 use the next levels.
        r = buy_result(
            entry=2050.0, atr=15.0,
            resistance_levels=[2080.0, 2105.0, 2140.0],
        )
        assert r is not None
        assert r.tp2.source == "structural"
        assert r.tp3.source == "structural"


# ─── Fibonacci Extension for TP3 ─────────────────────────────────────────────

class TestFibonacciExtension:
    """Fib extension key 'tp_ext_0.618' used for TP3 when valid direction."""

    def test_fib_extension_used_for_tp3_buy(self):
        """For BUY, fib extension above entry price is used as TP3."""
        r = buy_result(
            entry=2050.0, atr=15.0,
            resistance_levels=_BUY_RESISTANCES,
            fib_extensions={"tp_ext_0.618": 2130.0},
        )
        assert r is not None
        assert r.tp3.price == pytest.approx(2130.0)
        assert r.tp3.source == "fibonacci_extension"

    def test_fib_extension_used_for_tp3_sell(self):
        """For SELL, fib extension below entry price is used as TP3."""
        r = sell_result(
            entry=2050.0, atr=15.0,
            support_levels=_SELL_SUPPORTS,
            fib_extensions={"tp_ext_0.618": 1980.0},
        )
        assert r is not None
        assert r.tp3.price == pytest.approx(1980.0)
        assert r.tp3.source == "fibonacci_extension"

    def test_fib_extension_ignored_wrong_direction_for_buy(self):
        """For BUY, fib extension below entry is invalid — falls back to structural or ATR."""
        # Fib extension below entry is on the wrong side → ignored
        r = buy_result(
            entry=2050.0, atr=15.0,
            resistance_levels=_BUY_RESISTANCES,
            fib_extensions={"tp_ext_0.618": 2020.0},
        )
        assert r is not None
        assert r.tp3.source != "fibonacci_extension"

    def test_fib_extension_ignored_wrong_direction_for_sell(self):
        """For SELL, fib extension above entry is invalid — not used."""
        r = sell_result(
            entry=2050.0, atr=15.0,
            support_levels=_SELL_SUPPORTS,
            fib_extensions={"tp_ext_0.618": 2090.0},  # Above entry, invalid for SELL
        )
        assert r is not None
        assert r.tp3.source != "fibonacci_extension"

    def test_no_fib_extension_uses_structural_tp3(self):
        """When fib_extensions is empty and 3 structural levels exist, TP3 uses structural."""
        r = buy_result(
            entry=2050.0, atr=10.0,
            resistance_levels=[2065.0, 2080.0, 2110.0],
            fib_extensions={},
        )
        assert r is not None
        assert r.tp3.price == pytest.approx(2110.0)
        assert r.tp3.source == "structural"


# ─── SL Distance Metadata ────────────────────────────────────────────────────

class TestSLDistanceMetadata:
    """Validate sl_distance_pips and sl_distance_atr_multiple fields."""

    def test_sl_distance_pips_xauusd(self):
        """For XAUUSD, sl_distance_pips = risk_distance * 10."""
        entry = 2000.0
        atr = 20.0
        buffer = entry * SL_BUFFER_XAUUSD_PCT   # 1.0
        raw_sl = entry - SL_DEFAULT_ATR_MULTIPLE * atr   # 1970.0
        sl_price = raw_sl - buffer   # 1969.0
        risk_distance = entry - sl_price   # 31.0
        expected_pips = round(risk_distance * 10.0, 1)
        r = buy_result(entry=entry, atr=atr, pair="XAUUSD",
                       resistance_levels=[2040.0, 2065.0, 2090.0])
        assert r is not None
        assert r.sl_distance_pips == pytest.approx(expected_pips, abs=0.2)

    def test_sl_distance_pips_gbpjpy(self):
        """For GBPJPY, sl_distance_pips = risk_distance * 100."""
        entry = 190.0
        atr = 0.3
        buffer = SL_BUFFER_GBPJPY_PIPS * 0.01
        raw_sl = entry - SL_DEFAULT_ATR_MULTIPLE * atr
        sl_price = raw_sl - buffer
        risk_distance = entry - sl_price
        expected_pips = round(risk_distance * 100.0, 1)
        r = buy_result(entry=entry, atr=atr, pair="GBPJPY",
                       resistance_levels=[190.5, 191.0, 191.5])
        assert r is not None
        assert r.sl_distance_pips == pytest.approx(expected_pips, abs=0.2)

    def test_sl_atr_multiple_reasonable(self):
        """sl_distance_atr_multiple should be between 1.0 and ~3.1 for normal inputs."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert SL_MIN_ATR_MULTIPLE <= r.sl_distance_atr_multiple <= SL_MAX_ATR_MULTIPLE + 0.5

    def test_sl_atr_multiple_reflects_atr_distance(self):
        """sl_distance_atr_multiple ≈ (SL_DEFAULT_ATR_MULTIPLE) + tiny buffer fraction."""
        entry = 2000.0
        atr = 20.0
        r = buy_result(entry=entry, atr=atr, pair="XAUUSD",
                       resistance_levels=[2040.0, 2065.0, 2090.0])
        assert r is not None
        # Expected: (30 + 1) / 20 ≈ 1.55
        assert r.sl_distance_atr_multiple == pytest.approx(
            SL_DEFAULT_ATR_MULTIPLE + (entry * SL_BUFFER_XAUUSD_PCT) / atr, abs=0.05
        )


# ─── calculate_lot_size ───────────────────────────────────────────────────────

class TestCalculateLotSize:
    """Lot size calculation from account balance, risk %, and SL pips."""

    def test_basic_lot_size_xauusd(self):
        """$10,000 account, 1% risk, 100 pips SL on XAUUSD."""
        engine = TPSLEngine(pair="XAUUSD")
        lot_size, dollar_risk = engine.calculate_lot_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            sl_distance_pips=100.0,
        )
        # dollar_risk = 10000 * 0.01 = 100
        # pip_value XAUUSD = 1.0
        # lot_size = 100 / (100 * 1.0) = 1.0
        assert dollar_risk == pytest.approx(100.0)
        assert lot_size == pytest.approx(1.0)

    def test_dollar_risk_is_balance_times_risk_pct(self):
        """Dollar risk = balance × risk_pct / 100."""
        engine = TPSLEngine(pair="XAUUSD")
        _, dollar_risk = engine.calculate_lot_size(
            account_balance=5_000.0,
            risk_pct=2.0,
            sl_distance_pips=50.0,
        )
        assert dollar_risk == pytest.approx(100.0)

    def test_zero_sl_pips_returns_zero_lots(self):
        """With sl_distance_pips=0, lot_size should be 0 to avoid division by zero."""
        engine = TPSLEngine(pair="GBPJPY")
        lot_size, _ = engine.calculate_lot_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            sl_distance_pips=0.0,
        )
        assert lot_size == 0.0

    def test_lot_size_scales_with_balance(self):
        """Double the balance → double the lot size (all else equal)."""
        engine = TPSLEngine(pair="XAUUSD")
        lot1, _ = engine.calculate_lot_size(10_000.0, 1.0, 50.0)
        lot2, _ = engine.calculate_lot_size(20_000.0, 1.0, 50.0)
        assert lot2 == pytest.approx(lot1 * 2, rel=0.01)

    def test_lot_size_gbpjpy_larger_than_xauusd_for_same_inputs(self):
        """GBPJPY pip value (0.70) < XAUUSD (1.0) → same dollar risk yields larger lot for GJ."""
        engine_xau = TPSLEngine(pair="XAUUSD")
        engine_gj = TPSLEngine(pair="GBPJPY")
        lot_xau, _ = engine_xau.calculate_lot_size(10_000.0, 1.0, 100.0)
        lot_gj, _ = engine_gj.calculate_lot_size(10_000.0, 1.0, 100.0)
        # GJ: 100 / (100 * 0.70) ≈ 1.43, XAU: 100 / (100 * 1.0) = 1.00
        assert lot_gj > lot_xau

    def test_lot_size_inverse_of_sl_pips(self):
        """Halving SL pips doubles the lot size."""
        engine = TPSLEngine(pair="XAUUSD")
        lot1, _ = engine.calculate_lot_size(10_000.0, 1.0, 100.0)
        lot2, _ = engine.calculate_lot_size(10_000.0, 1.0, 50.0)
        assert lot2 == pytest.approx(lot1 * 2, rel=0.01)


# ─── _price_to_pips Internal Conversion ──────────────────────────────────────

class TestPriceToPips:
    """Internal _price_to_pips converts price distance to pips correctly."""

    def test_xauusd_distance_to_pips(self):
        """XAUUSD: price distance × 10 = pips."""
        engine = TPSLEngine(pair="XAUUSD")
        assert engine._price_to_pips(1.0) == pytest.approx(10.0)

    def test_gbpjpy_distance_to_pips(self):
        """GBPJPY: price distance × 100 = pips."""
        engine = TPSLEngine(pair="GBPJPY")
        assert engine._price_to_pips(1.0) == pytest.approx(100.0)

    def test_xauusd_half_point_is_5_pips(self):
        """XAUUSD: 0.5 price distance = 5 pips."""
        engine = TPSLEngine(pair="XAUUSD")
        assert engine._price_to_pips(0.5) == pytest.approx(5.0)

    def test_gbpjpy_one_pip_distance(self):
        """GBPJPY: 0.01 price distance = 1 pip."""
        engine = TPSLEngine(pair="GBPJPY")
        assert engine._price_to_pips(0.01) == pytest.approx(1.0)

    def test_xauusd_large_distance(self):
        """XAUUSD: 10.0 price distance = 100 pips."""
        engine = TPSLEngine(pair="XAUUSD")
        assert engine._price_to_pips(10.0) == pytest.approx(100.0)


# ─── Constant Values ─────────────────────────────────────────────────────────

class TestConstants:
    """Verify exported constants match PRD specification."""

    def test_sl_default_atr_multiple(self):
        assert SL_DEFAULT_ATR_MULTIPLE == pytest.approx(1.5)

    def test_sl_buffer_xauusd_pct(self):
        assert SL_BUFFER_XAUUSD_PCT == pytest.approx(0.0005)

    def test_sl_buffer_gbpjpy_pips(self):
        assert SL_BUFFER_GBPJPY_PIPS == 7

    def test_tp_close_percentages_sum_to_one(self):
        """TP1 + TP2 + TP3 close percentages must sum to 1.0."""
        assert TP1_CLOSE_PCT + TP2_CLOSE_PCT + TP3_CLOSE_PCT == pytest.approx(1.0)

    def test_tp1_close_pct_is_40pct(self):
        assert TP1_CLOSE_PCT == pytest.approx(0.40)

    def test_tp2_close_pct_is_30pct(self):
        assert TP2_CLOSE_PCT == pytest.approx(0.30)

    def test_tp3_close_pct_is_30pct(self):
        assert TP3_CLOSE_PCT == pytest.approx(0.30)

    def test_sl_min_atr_multiple(self):
        assert SL_MIN_ATR_MULTIPLE == pytest.approx(1.0)

    def test_sl_max_atr_multiple(self):
        assert SL_MAX_ATR_MULTIPLE == pytest.approx(3.0)


# ─── RR Ratio Field ──────────────────────────────────────────────────────────

class TestRRRatioField:
    """rr_ratio fields on TPLevel should reflect actual R:R achieved."""

    def test_tp1_rr_ratio_at_least_1(self):
        """TP1 rr_ratio must be >= 1.0 (enforced by suppression logic)."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert r.tp1.rr_ratio >= 1.0

    def test_tp2_rr_ratio_greater_than_tp1(self):
        """TP2 rr_ratio should exceed TP1 rr_ratio for a valid setup."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert r.tp2.rr_ratio > r.tp1.rr_ratio

    def test_tp3_rr_ratio_greater_than_tp2(self):
        """TP3 rr_ratio should exceed TP2 rr_ratio."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        assert r.tp3.rr_ratio > r.tp2.rr_ratio

    def test_rr_ratio_reflects_price_distance(self):
        """rr_ratio should equal price distance from entry / risk distance."""
        r = buy_result(entry=2050.0, atr=15.0, resistance_levels=_BUY_RESISTANCES)
        assert r is not None
        risk_distance = abs(r.entry_price - r.stop_loss)
        expected_tp1_rr = abs(r.tp1.price - r.entry_price) / risk_distance
        assert r.tp1.rr_ratio == pytest.approx(expected_tp1_rr, abs=0.01)
