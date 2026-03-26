"""
SupportResistanceModule Tests — engine/modules/support_resistance.py

Covers:
    - Empty swing points → no levels
    - Single swing high creates a resistance level
    - Single swing low creates a support level
    - Cluster (3+ swing points within 0.5x ATR) → strength counted correctly
    - Level status defaults to INTACT
    - Price breaks through resistance → BROKEN
    - Price near resistance → TESTED
    - Score +0.7 bullish + strong support (strength >= 3)
    - Score +0.5 bullish + weaker support (strength < 3)
    - Score -0.7 bearish + strong resistance
    - Score -0.5 bearish + weaker resistance
    - Score 0.0 when no levels near price
    - Equal highs detection → LIQUIDITY_POOL_HIGH
    - Equal lows detection → LIQUIDITY_POOL_LOW
    - XAUUSD equal highs tolerance: 0.03% of price
    - GBPJPY equal highs tolerance: 5 pips
    - nearest_support: closest intact support below price
    - nearest_resistance: closest intact resistance above price
    - get_liquidity_pools: returns only pool levels
    - Empty ATR series → early return, no crash
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import pytest

from engine.modules.support_resistance import (
    SupportResistanceModule,
    SRKind,
    SRStatus,
    SRLevel,
    EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT,
    EQUAL_HIGHS_TOLERANCE_GBPJPY_PIPS,
)
from engine.modules.market_structure import SwingPoint


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _ts(n: int = 0) -> datetime:
    """Return a deterministic timestamp offset by n days."""
    return datetime(2024, 1, 1 + n % 28)


def _sp(price: float, kind: str, n: int = 0) -> SwingPoint:
    return SwingPoint(timestamp=_ts(n), price=price, kind=kind, confirmed=True)


def _candles(close: float, n: int = 10) -> pd.DataFrame:
    """Minimal OHLCV candle DataFrame with a specific close price."""
    closes = np.full(n, close)
    return pd.DataFrame(
        {
            "open": closes - 0.5,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": np.ones(n) * 500,
        }
    )


def _atr(value: float = 10.0, n: int = 100) -> pd.Series:
    return pd.Series([value] * n)


def _module(pair: str = "XAUUSD") -> SupportResistanceModule:
    return SupportResistanceModule(timeframe="15m", pair=pair)


# ─── 1. Empty inputs ─────────────────────────────────────────────────────────

class TestEmptyInputs:
    def test_no_swing_points_no_levels(self):
        m = _module()
        m.update(_candles(2000.0), [], [], _atr())
        assert m.levels == []

    def test_empty_atr_returns_early_no_crash(self):
        m = _module()
        m.update(_candles(2000.0), [_sp(2100.0, "high")], [], pd.Series([], dtype=float))
        assert m.levels == []

    def test_score_zero_when_no_levels(self):
        m = _module()
        assert m.score(2000.0, is_bullish_trend=True) == 0.0

    def test_nearest_support_none_when_no_levels(self):
        m = _module()
        m.update(_candles(2000.0), [], [], _atr())
        assert m.nearest_support(2000.0) is None

    def test_nearest_resistance_none_when_no_levels(self):
        m = _module()
        m.update(_candles(2000.0), [], [], _atr())
        assert m.nearest_resistance(2000.0) is None

    def test_get_liquidity_pools_empty_when_no_levels(self):
        m = _module()
        m.update(_candles(2000.0), [], [], _atr())
        assert m.get_liquidity_pools() == []

    def test_atr_series_all_nan_no_crash(self):
        m = _module()
        atr = pd.Series([float("nan")] * 50)
        m.update(_candles(2000.0), [_sp(2100.0, "high")], [], atr)
        assert m.levels == []


# ─── 2. Single swing point creates a level ───────────────────────────────────

class TestSingleSwingPoint:
    def test_single_high_creates_resistance(self):
        m = _module()
        m.update(_candles(2050.0), [_sp(2100.0, "high")], [], _atr())
        resistances = [l for l in m.levels if l.kind == SRKind.RESISTANCE]
        assert len(resistances) == 1

    def test_single_low_creates_support(self):
        m = _module()
        m.update(_candles(2050.0), [], [_sp(2000.0, "low")], _atr())
        supports = [l for l in m.levels if l.kind == SRKind.SUPPORT]
        assert len(supports) == 1

    def test_single_high_resistance_price_correct(self):
        m = _module()
        m.update(_candles(2050.0), [_sp(2100.0, "high")], [], _atr())
        res = [l for l in m.levels if l.kind == SRKind.RESISTANCE][0]
        assert res.price == 2100.0

    def test_single_swing_level_strength_is_one(self):
        m = _module()
        m.update(_candles(2050.0), [_sp(2100.0, "high")], [], _atr())
        res = [l for l in m.levels if l.kind == SRKind.RESISTANCE][0]
        assert res.strength == 1

    def test_single_level_initial_status_intact(self):
        m = _module()
        m.update(_candles(2050.0), [_sp(2100.0, "high")], [], _atr())
        res = [l for l in m.levels if l.kind == SRKind.RESISTANCE][0]
        assert res.status == SRStatus.INTACT

    def test_single_low_support_strength_is_one(self):
        m = _module()
        m.update(_candles(2050.0), [], [_sp(2000.0, "low")], _atr())
        sup = [l for l in m.levels if l.kind == SRKind.SUPPORT][0]
        assert sup.strength == 1


# ─── 3. Cluster detection ────────────────────────────────────────────────────

class TestClusterDetection:
    def _three_highs_within_atr(self) -> list[SwingPoint]:
        """Three swing highs within 0.5 * 10 = 5.0 units of each other → one cluster."""
        return [
            _sp(2100.0, "high", 0),
            _sp(2102.0, "high", 1),
            _sp(2104.0, "high", 2),
        ]

    def test_three_highs_within_tolerance_form_one_level(self):
        m = _module()
        m.update(_candles(2050.0), self._three_highs_within_atr(), [], _atr(10.0))
        resistances = [l for l in m.levels if l.kind == SRKind.RESISTANCE]
        assert len(resistances) == 1

    def test_cluster_strength_equals_three(self):
        m = _module()
        m.update(_candles(2050.0), self._three_highs_within_atr(), [], _atr(10.0))
        res = [l for l in m.levels if l.kind == SRKind.RESISTANCE][0]
        assert res.strength == 3

    def test_two_separate_clusters_produce_two_levels(self):
        """Two groups of highs far apart → two resistance levels."""
        highs = [
            _sp(2100.0, "high", 0),
            _sp(2102.0, "high", 1),
            _sp(2200.0, "high", 2),  # far away
            _sp(2202.0, "high", 3),
        ]
        m = _module()
        m.update(_candles(2050.0), highs, [], _atr(10.0))
        resistances = [l for l in m.levels if l.kind == SRKind.RESISTANCE]
        assert len(resistances) == 2

    def test_cluster_price_is_average_of_members(self):
        """Average of 2100 and 2102 = 2101."""
        highs = [_sp(2100.0, "high", 0), _sp(2102.0, "high", 1)]
        m = _module()
        m.update(_candles(2050.0), highs, [], _atr(10.0))
        res = [l for l in m.levels if l.kind == SRKind.RESISTANCE][0]
        assert abs(res.price - 2101.0) < 1e-9

    def test_highs_beyond_tolerance_form_separate_levels(self):
        """Highs 100 units apart with ATR=10 → 2 levels (tolerance = 5)."""
        highs = [_sp(2100.0, "high", 0), _sp(2200.0, "high", 1)]
        m = _module()
        m.update(_candles(2050.0), highs, [], _atr(10.0))
        resistances = [l for l in m.levels if l.kind == SRKind.RESISTANCE]
        assert len(resistances) == 2

    def test_strength_three_lows_cluster(self):
        lows = [_sp(2000.0, "low", 0), _sp(2002.0, "low", 1), _sp(2004.0, "low", 2)]
        m = _module()
        m.update(_candles(2050.0), [], lows, _atr(10.0))
        sup = [l for l in m.levels if l.kind == SRKind.SUPPORT][0]
        assert sup.strength == 3


# ─── 4. Level status transitions ─────────────────────────────────────────────

class TestLevelStatus:
    def test_resistance_broken_when_close_above_level(self):
        """Current close above resistance price → BROKEN."""
        m = _module()
        # Resistance at 2100; current close at 2150 (well above)
        m.update(_candles(2150.0), [_sp(2100.0, "high")], [], _atr(10.0))
        res = [l for l in m.levels if l.kind == SRKind.RESISTANCE][0]
        assert res.status == SRStatus.BROKEN

    def test_resistance_tested_when_close_near_level(self):
        """Close within 0.5 * ATR of resistance → TESTED."""
        atr_val = 10.0
        res_price = 2100.0
        # Close just within tolerance: res_price - 0.5 * atr = 2100 - 5 = 2095
        close = res_price - 4.0
        m = _module()
        m.update(_candles(close), [_sp(res_price, "high")], [], _atr(atr_val))
        res = [l for l in m.levels if l.kind == SRKind.RESISTANCE][0]
        assert res.status == SRStatus.TESTED

    def test_resistance_intact_when_far_below_level(self):
        """Close well below resistance → INTACT."""
        m = _module()
        m.update(_candles(1900.0), [_sp(2100.0, "high")], [], _atr(10.0))
        res = [l for l in m.levels if l.kind == SRKind.RESISTANCE][0]
        assert res.status == SRStatus.INTACT

    def test_support_broken_when_close_below_level(self):
        """Close below support price → BROKEN."""
        m = _module()
        m.update(_candles(1950.0), [], [_sp(2000.0, "low")], _atr(10.0))
        sup = [l for l in m.levels if l.kind == SRKind.SUPPORT][0]
        assert sup.status == SRStatus.BROKEN

    def test_support_intact_when_far_above_level(self):
        m = _module()
        m.update(_candles(2100.0), [], [_sp(2000.0, "low")], _atr(10.0))
        sup = [l for l in m.levels if l.kind == SRKind.SUPPORT][0]
        assert sup.status == SRStatus.INTACT


# ─── 5. Score logic ──────────────────────────────────────────────────────────

class TestScoreLogic:
    def _module_with_strong_support(self) -> SupportResistanceModule:
        """Three lows clustered near 2002 → strength=3 support.

        update() is called with close=2050 so the support stays INTACT.
        score() is then called with a price near 2002 (within 0.5 * ATR = 5).
        """
        m = _module()
        lows = [
            _sp(2000.0, "low", 0),
            _sp(2002.0, "low", 1),
            _sp(2004.0, "low", 2),
        ]
        # Use a close well above the cluster so the level status stays INTACT
        m.update(_candles(2050.0), [], lows, _atr(10.0))
        return m

    def _module_with_weak_support(self) -> SupportResistanceModule:
        """Single low at 2000 = strength 1; close kept at 2050 so level is INTACT."""
        m = _module()
        m.update(_candles(2050.0), [], [_sp(2000.0, "low")], _atr(10.0))
        return m

    def _module_with_strong_resistance(self) -> SupportResistanceModule:
        """Three highs near 2102 → strength=3 resistance.

        update() uses close=2050 so resistance stays INTACT.
        """
        m = _module()
        highs = [
            _sp(2100.0, "high", 0),
            _sp(2102.0, "high", 1),
            _sp(2104.0, "high", 2),
        ]
        m.update(_candles(2050.0), highs, [], _atr(10.0))
        return m

    def test_score_positive_07_bullish_strong_support_near(self):
        """Price within 0.5*ATR of strong support (strength=3), bullish → +0.7."""
        # Support cluster averages to 2002. ATR=10 → tolerance=5.
        # Score price 2006: abs(2006 - 2002) = 4 <= 5 → near.
        m = self._module_with_strong_support()
        sc = m.score(2006.0, is_bullish_trend=True)
        assert sc == pytest.approx(0.7)

    def test_score_positive_05_bullish_weak_support_near(self):
        """Price near weak support (strength=1) in bullish trend → +0.5."""
        # Support at 2000, ATR=10 → tolerance=5. Score price 2004: near.
        m = self._module_with_weak_support()
        sc = m.score(2004.0, is_bullish_trend=True)
        assert sc == pytest.approx(0.5)

    def test_score_negative_07_bearish_strong_resistance_near(self):
        """Price within 0.5*ATR of strong resistance (strength=3), bearish → -0.7."""
        # Resistance at 2102. ATR=10 → tolerance=5. Score price 2098: near.
        m = self._module_with_strong_resistance()
        sc = m.score(2098.0, is_bullish_trend=False)
        assert sc == pytest.approx(-0.7)

    def test_score_negative_05_bearish_weak_resistance_near(self):
        """Price near weak resistance (strength=1) in bearish trend → -0.5."""
        # Resistance at 2100. Update with close=2050 so it stays INTACT.
        m = _module()
        m.update(_candles(2050.0), [_sp(2100.0, "high")], [], _atr(10.0))
        # Score near that resistance
        sc = m.score(2096.0, is_bullish_trend=False)
        assert sc == pytest.approx(-0.5)

    def test_score_zero_no_levels_near(self):
        """Price far from any level → 0.0."""
        m = _module()
        m.update(_candles(2050.0), [_sp(2200.0, "high")], [_sp(1800.0, "low")], _atr(10.0))
        sc = m.score(2050.0, is_bullish_trend=True)
        assert sc == 0.0

    def test_score_zero_no_levels_at_all(self):
        m = _module()
        assert m.score(2000.0, is_bullish_trend=True) == 0.0

    def test_score_zero_no_levels_bearish(self):
        m = _module()
        assert m.score(2000.0, is_bullish_trend=False) == 0.0

    def test_score_in_range_minus_one_to_plus_one(self):
        m = self._module_with_strong_support()
        sc = m.score(2006.0, is_bullish_trend=True)
        assert -1.0 <= sc <= 1.0


# ─── 6. Equal highs / lows (liquidity pools) ─────────────────────────────────

class TestLiquidityPools:
    def _xauusd_equal_highs(self, price: float = 2000.0) -> list[SwingPoint]:
        """Two highs within 0.03% of each other → equal highs."""
        tol = price * EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT
        return [
            _sp(price, "high", 0),
            _sp(price + tol * 0.5, "high", 1),  # within tolerance
        ]

    def _xauusd_unequal_highs(self, price: float = 2000.0) -> list[SwingPoint]:
        """Two highs well outside 0.03% tolerance."""
        tol = price * EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT
        return [
            _sp(price, "high", 0),
            _sp(price + tol * 5, "high", 1),  # well outside tolerance
        ]

    def test_equal_highs_xauusd_creates_liquidity_pool_high(self):
        m = _module("XAUUSD")
        highs = self._xauusd_equal_highs(2000.0)
        m.update(_candles(1990.0), highs, [], _atr(10.0))
        pools = [l for l in m.levels if l.kind == SRKind.LIQUIDITY_POOL_HIGH]
        assert len(pools) >= 1

    def test_unequal_highs_xauusd_no_pool_created(self):
        m = _module("XAUUSD")
        highs = self._xauusd_unequal_highs(2000.0)
        m.update(_candles(1990.0), highs, [], _atr(10.0))
        pools = [l for l in m.levels if l.kind == SRKind.LIQUIDITY_POOL_HIGH]
        assert len(pools) == 0

    def test_equal_lows_xauusd_creates_liquidity_pool_low(self):
        price = 2000.0
        tol = price * EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT
        lows = [
            _sp(price, "low", 0),
            _sp(price + tol * 0.5, "low", 1),
        ]
        m = _module("XAUUSD")
        m.update(_candles(2050.0), [], lows, _atr(10.0))
        pools = [l for l in m.levels if l.kind == SRKind.LIQUIDITY_POOL_LOW]
        assert len(pools) >= 1

    def test_equal_highs_gbpjpy_within_5_pips(self):
        """5 pips = 0.05 for GBPJPY → highs within 0.05."""
        pips = EQUAL_HIGHS_TOLERANCE_GBPJPY_PIPS * 0.01  # 0.05
        highs = [
            _sp(195.00, "high", 0),
            _sp(195.00 + pips * 0.5, "high", 1),  # within 5 pips
        ]
        m = _module("GBPJPY")
        m.update(_candles(194.0), highs, [], _atr(0.5))
        pools = [l for l in m.levels if l.kind == SRKind.LIQUIDITY_POOL_HIGH]
        assert len(pools) >= 1

    def test_equal_highs_gbpjpy_beyond_5_pips_no_pool(self):
        pips = EQUAL_HIGHS_TOLERANCE_GBPJPY_PIPS * 0.01  # 0.05
        highs = [
            _sp(195.00, "high", 0),
            _sp(195.00 + pips * 5, "high", 1),  # 25 pips apart — too far
        ]
        m = _module("GBPJPY")
        m.update(_candles(194.0), highs, [], _atr(0.5))
        pools = [l for l in m.levels if l.kind == SRKind.LIQUIDITY_POOL_HIGH]
        assert len(pools) == 0

    def test_get_liquidity_pools_returns_only_pool_kinds(self):
        m = _module("XAUUSD")
        highs = self._xauusd_equal_highs(2000.0) + [_sp(2100.0, "high", 5)]
        lows = [_sp(1900.0, "low", 6)]
        m.update(_candles(1990.0), highs, lows, _atr(10.0))
        pools = m.get_liquidity_pools()
        for pool in pools:
            assert pool.kind in (SRKind.LIQUIDITY_POOL_HIGH, SRKind.LIQUIDITY_POOL_LOW)

    def test_get_liquidity_pools_excludes_support_and_resistance(self):
        m = _module("XAUUSD")
        # Single high = resistance, single low = support — no pools expected
        m.update(_candles(2050.0), [_sp(2100.0, "high")], [_sp(2000.0, "low")], _atr(10.0))
        pools = m.get_liquidity_pools()
        assert pools == []

    def test_single_swing_high_no_equal_highs_pool(self):
        m = _module("XAUUSD")
        m.update(_candles(2050.0), [_sp(2100.0, "high")], [], _atr(10.0))
        pools = [l for l in m.levels if l.kind == SRKind.LIQUIDITY_POOL_HIGH]
        assert pools == []

    def test_xauusd_tolerance_constant_value(self):
        assert EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT == pytest.approx(0.0003)

    def test_gbpjpy_tolerance_constant_value(self):
        assert EQUAL_HIGHS_TOLERANCE_GBPJPY_PIPS == 5

    def test_liquidity_pool_price_is_average_of_equal_highs(self):
        price = 2000.0
        tol = price * EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT
        p1 = price
        p2 = price + tol * 0.5
        highs = [_sp(p1, "high", 0), _sp(p2, "high", 1)]
        m = _module("XAUUSD")
        m.update(_candles(1990.0), highs, [], _atr(10.0))
        pools = [l for l in m.levels if l.kind == SRKind.LIQUIDITY_POOL_HIGH]
        assert len(pools) >= 1
        assert abs(pools[0].price - (p1 + p2) / 2) < 1e-9


# ─── 7. nearest_support and nearest_resistance ───────────────────────────────

class TestNearestLevels:
    def _setup_multi_level(self) -> SupportResistanceModule:
        """Two support levels at 1980 and 1990, one resistance at 2100."""
        m = _module()
        lows = [_sp(1980.0, "low", 0), _sp(1990.0, "low", 1)]
        highs = [_sp(2100.0, "high", 2)]
        m.update(_candles(2050.0), highs, lows, _atr(10.0))
        return m

    def test_nearest_support_returns_closest_below_price(self):
        m = self._setup_multi_level()
        sup = m.nearest_support(2050.0)
        assert sup is not None
        # 1990 is closer to 2050 than 1980
        assert sup.price > 1980.0

    def test_nearest_support_returns_none_when_none_below(self):
        m = _module()
        m.update(_candles(2050.0), [], [_sp(2100.0, "low")], _atr(10.0))
        # Support at 2100 is above current price 2050
        result = m.nearest_support(2050.0)
        assert result is None

    def test_nearest_resistance_returns_closest_above_price(self):
        m = _module()
        highs = [_sp(2100.0, "high", 0), _sp(2200.0, "high", 1)]
        m.update(_candles(2050.0), highs, [], _atr(10.0))
        res = m.nearest_resistance(2050.0)
        assert res is not None
        assert res.price == pytest.approx(2100.0)

    def test_nearest_resistance_returns_none_when_none_above(self):
        m = _module()
        m.update(_candles(2050.0), [_sp(2000.0, "high")], [], _atr(10.0))
        result = m.nearest_resistance(2050.0)
        # Resistance at 2000 is below current price 2050
        assert result is None

    def test_nearest_support_excludes_broken_levels(self):
        """A support whose status is BROKEN should not be returned."""
        m = _module()
        # Close below support → support gets BROKEN status
        m.update(_candles(1950.0), [], [_sp(2000.0, "low")], _atr(10.0))
        result = m.nearest_support(1950.0)
        assert result is None

    def test_nearest_resistance_excludes_broken_levels(self):
        """Resistance that has been broken should not be returned."""
        m = _module()
        # Close above resistance → resistance gets BROKEN status
        m.update(_candles(2150.0), [_sp(2100.0, "high")], [], _atr(10.0))
        result = m.nearest_resistance(2150.0)
        assert result is None


# ─── 8. Liquidity pool score interaction ─────────────────────────────────────

class TestLiquidityPoolScore:
    def test_score_04_bullish_near_equal_lows(self):
        """Bullish trend with equal lows nearby → +0.4 (risky liquidity grab)."""
        price = 2000.0
        tol = price * EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT
        lows = [_sp(price, "low", 0), _sp(price + tol * 0.5, "low", 1)]
        m = _module("XAUUSD")
        # Place current close just above the equal lows so it's "near"
        current = price + 4.0  # within 0.5 * ATR(10) = 5.0 of pool level
        m.update(_candles(current), [], lows, _atr(10.0))
        sc = m.score(current, is_bullish_trend=True)
        assert sc == pytest.approx(0.4)

    def test_score_negative_04_bearish_near_equal_highs(self):
        """Bearish trend with equal highs nearby → -0.4."""
        price = 2000.0
        tol = price * EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT
        highs = [_sp(price, "high", 0), _sp(price + tol * 0.5, "high", 1)]
        m = _module("XAUUSD")
        current = price - 4.0  # within tolerance of pool level
        m.update(_candles(current), highs, [], _atr(10.0))
        sc = m.score(current, is_bullish_trend=False)
        assert sc == pytest.approx(-0.4)


# ─── 9. SRLevel dataclass integrity ──────────────────────────────────────────

class TestSRLevelDataclass:
    def test_sr_level_kind_enum_values(self):
        assert SRKind.SUPPORT
        assert SRKind.RESISTANCE
        assert SRKind.LIQUIDITY_POOL_HIGH
        assert SRKind.LIQUIDITY_POOL_LOW

    def test_sr_status_enum_values(self):
        assert SRStatus.INTACT
        assert SRStatus.TESTED
        assert SRStatus.BROKEN
        assert SRStatus.FLIPPED

    def test_sr_level_creation(self):
        level = SRLevel(
            price=2100.0,
            kind=SRKind.RESISTANCE,
            status=SRStatus.INTACT,
            strength=3,
            first_seen=_ts(),
        )
        assert level.price == 2100.0
        assert level.strength == 3
        assert level.status == SRStatus.INTACT

    def test_tolerance_atr_defaults_to_half(self):
        level = SRLevel(
            price=2000.0,
            kind=SRKind.SUPPORT,
            status=SRStatus.INTACT,
            strength=1,
            first_seen=_ts(),
        )
        assert level.tolerance_atr == 0.5
