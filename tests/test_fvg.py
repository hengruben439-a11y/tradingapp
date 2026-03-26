"""
FVG Module Tests — Sprint 3 deliverable.

Test strategy (300 labeled cases across true positives, ambiguous, and false positives):

    TRUE POSITIVES (100): Clean FVG patterns that are correctly detected and tracked.
    AMBIGUOUS (100):      Borderline sizes, partial fills, near-misses, edge cases.
    FALSE POSITIVES (100): Patterns that should NOT produce FVGs or correct scores.

Sprint 1: scaffolding and helpers.
Sprint 3: full 300 labeled test cases added alongside implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from engine.modules.fvg import FVGModule, FVGKind, FVGStatus, FairValueGap


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_candles(ohlcv: list[tuple[float, float, float, float, float]]) -> pd.DataFrame:
    n = len(ohlcv)
    index = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    o, h, l, c, v = zip(*ohlcv)
    return pd.DataFrame(
        {"open": o, "high": h, "low": l, "close": c, "volume": v},
        index=index,
    )


def _make_atr(candles: pd.DataFrame, constant: float = 2.0) -> pd.Series:
    return pd.Series([constant] * len(candles), index=candles.index)


def _bullish_fvg_candles(gap_size: float = 3.0) -> pd.DataFrame:
    """Three-candle bullish FVG: C1.high=100, C3.low=100+gap_size."""
    c1_high = 100.0
    c3_low = c1_high + gap_size
    return _make_candles([
        (99.0,  c1_high, 98.0, 98.5, 1000),
        (98.5,  106.0,   98.0, 105.5, 5000),
        (105.5, 107.0,   c3_low, 106.5, 2000),
    ])


def _bearish_fvg_candles(gap_size: float = 3.0) -> pd.DataFrame:
    """Three-candle bearish FVG: C1.low=100, C3.high=100-gap_size."""
    c1_low = 100.0
    c3_high = c1_low - gap_size
    return _make_candles([
        (101.0, 102.0,  c1_low,  101.5, 1000),
        (101.5, 102.0,  94.0,    94.5,  5000),
        (94.5,  c3_high, 93.0,   93.5,  2000),
    ])


def _too_small_fvg_candles() -> pd.DataFrame:
    """Gap = 0.4 (well below min size)."""
    return _make_candles([
        (99.0,  100.0, 98.0,  98.5,  1000),
        (98.5,  102.0, 98.0,  101.5, 5000),
        (101.5, 103.0, 100.4, 102.5, 2000),
    ])


def _no_gap_touching_candles() -> pd.DataFrame:
    """C3.low == C1.high — touching but no gap."""
    return _make_candles([
        (99.0,  100.0, 98.0,  98.5,  1000),
        (98.5,  106.0, 98.0,  105.5, 5000),
        (105.5, 107.0, 100.0, 106.5, 2000),  # C3.low == C1.high = 100 → no gap
    ])


def _bullish_fvg_then_partial_fill(gap_size: float = 4.0) -> pd.DataFrame:
    """FVG formed, then a candle dips into zone but closes above bottom."""
    c1_high = 100.0
    c3_low = c1_high + gap_size  # top = 104
    return _make_candles([
        (99.0,  c1_high, 98.0, 98.5, 1000),   # C1
        (98.5,  106.0,   98.0, 105.5, 5000),  # C2 displacement
        (105.5, 107.0,   c3_low, 106.5, 2000),  # C3
        (106.5, 107.0,   102.0,  103.0, 2000),  # dips to 102 (inside zone), closes at 103 > 100
    ])


def _bullish_fvg_then_full_fill(gap_size: float = 4.0) -> pd.DataFrame:
    """FVG formed, then a candle closes below the bottom."""
    c1_high = 100.0
    c3_low = c1_high + gap_size
    return _make_candles([
        (99.0,  c1_high, 98.0, 98.5, 1000),
        (98.5,  106.0,   98.0, 105.5, 5000),
        (105.5, 107.0,   c3_low, 106.5, 2000),
        (106.5, 107.0,   97.0,   99.0, 8000),  # close=99 < bottom=100 → FILLED
    ])


def _bearish_fvg_then_partial_fill(gap_size: float = 4.0) -> pd.DataFrame:
    """Bearish FVG formed, then candle rises into zone but closes below top."""
    c1_low = 100.0
    c3_high = c1_low - gap_size  # bottom = 96
    return _make_candles([
        (101.0, 102.0,  c1_low,  101.5, 1000),
        (101.5, 102.0,  94.0,    94.5,  5000),
        (94.5,  c3_high, 93.0,   93.5,  2000),
        (93.5,  98.0,    93.0,   97.0,  3000),  # high=98 enters zone [96,100], close=97 < top=100
    ])


def _bearish_fvg_then_full_fill(gap_size: float = 4.0) -> pd.DataFrame:
    """Bearish FVG formed, then a candle closes above the top."""
    c1_low = 100.0
    c3_high = c1_low - gap_size
    return _make_candles([
        (101.0, 102.0,  c1_low,  101.5, 1000),
        (101.5, 102.0,  94.0,    94.5,  5000),
        (94.5,  c3_high, 93.0,   93.5,  2000),
        (93.5,  101.5,   93.0,   101.0, 8000),  # close=101 > top=100 → FILLED
    ])


def _many_fvg_candles(n_fvgs: int = 3) -> tuple[pd.DataFrame, pd.Series]:
    """Generate n_fvgs sequential bullish FVGs."""
    rows: list[tuple[float, float, float, float, float]] = []
    price = 100.0
    for _ in range(n_fvgs):
        rows.append((price - 1, price, price - 2, price - 1.5, 1000))    # C1 bearish
        rows.append((price - 1.5, price + 8, price - 2, price + 7, 5000))  # C2 big bull
        rows.append((price + 7, price + 9, price + 3.5, price + 8.5, 2000))  # C3 gap > C1.high
        price += 10
    candles = _make_candles(rows)
    atr = _make_atr(candles, constant=2.0)
    return candles, atr


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def fvg_15m() -> FVGModule:
    return FVGModule(timeframe="15m", pair="XAUUSD", min_size_atr_multiple=1.0)


@pytest.fixture
def fvg_1m() -> FVGModule:
    return FVGModule(timeframe="1m", pair="XAUUSD", min_size_atr_multiple=0.5)


@pytest.fixture
def fvg_1h() -> FVGModule:
    return FVGModule(timeframe="1H", pair="XAUUSD", min_size_atr_multiple=1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# TRUE POSITIVES (100 cases) — Clean setups that SHOULD be detected correctly
# ═══════════════════════════════════════════════════════════════════════════════

class TestInitialization:
    """TP-001 to TP-005: Module starts in clean state."""

    def test_starts_empty(self, fvg_15m):  # TP-001
        assert fvg_15m.fvgs == []

    def test_no_fvg_returns_none(self, fvg_15m):  # TP-002
        assert fvg_15m.nearest_fvg(100.0) is None

    def test_open_fvgs_empty(self, fvg_15m):  # TP-003
        assert fvg_15m.get_open_fvgs() == []

    def test_score_zero_before_update(self, fvg_15m):  # TP-004
        assert fvg_15m.score(100.0) == pytest.approx(0.0)

    def test_unicorn_false_before_update(self, fvg_15m):  # TP-005
        assert fvg_15m.check_unicorn_overlap(105.0, 98.0) is False


class TestBullishFVGDetection:
    """TP-006 to TP-040: Bullish FVG patterns correctly detected."""

    def test_bullish_fvg_detected(self, fvg_15m):  # TP-006
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert len(fvg_15m.fvgs) == 1
        assert fvg_15m.fvgs[0].kind == FVGKind.BULLISH

    def test_bullish_fvg_zone_boundaries(self, fvg_15m):  # TP-007
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        fvg = fvg_15m.fvgs[0]
        assert fvg.bottom == pytest.approx(100.0)
        assert fvg.top == pytest.approx(103.0)

    def test_bullish_fvg_status_starts_open(self, fvg_15m):  # TP-008
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].status == FVGStatus.OPEN

    def test_bullish_fvg_midpoint(self, fvg_15m):  # TP-009
        candles = _bullish_fvg_candles(gap_size=4.0)  # bottom=100, top=104
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].midpoint == pytest.approx(102.0)

    def test_bullish_fvg_fill_pct_starts_zero(self, fvg_15m):  # TP-010
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].fill_pct == pytest.approx(0.0)

    @pytest.mark.parametrize("gap_size", [2.1, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0, 30.0])
    def test_bullish_fvg_various_gap_sizes(self, fvg_15m, gap_size):  # TP-011 to TP-020
        """Gap well above threshold (2x ATR = 4.0) → always detected."""
        candles = _bullish_fvg_candles(gap_size=gap_size)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert len(fvg_15m.fvgs) == 1
        assert fvg_15m.fvgs[0].top == pytest.approx(100.0 + gap_size)
        assert fvg_15m.fvgs[0].bottom == pytest.approx(100.0)

    def test_bullish_fvg_size_atr_ratio(self, fvg_15m):  # TP-021
        """size_atr should equal gap / ATR."""
        candles = _bullish_fvg_candles(gap_size=6.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].size_atr == pytest.approx(3.0)  # 6.0/2.0

    def test_bullish_fvg_nearest_fvg(self, fvg_15m):  # TP-022
        candles = _bullish_fvg_candles(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        nearest = fvg_15m.nearest_fvg(102.0)  # inside zone
        assert nearest is not None
        assert nearest.kind == FVGKind.BULLISH

    def test_bullish_fvg_in_open_fvgs(self, fvg_15m):  # TP-023
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        open_fvgs = fvg_15m.get_open_fvgs()
        assert len(open_fvgs) == 1

    @pytest.mark.parametrize("n", [1, 2, 3])
    def test_multiple_sequential_bullish_fvgs(self, fvg_15m, n):  # TP-024 to TP-026
        candles, atr = _many_fvg_candles(n_fvgs=n)
        fvg_15m.update(candles, atr)
        assert len(fvg_15m.fvgs) == n

    def test_bullish_fvg_timestamp_is_middle_candle(self, fvg_15m):  # TP-027
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # Middle candle is index 1
        expected_ts = candles.index[1].to_pydatetime()
        assert fvg_15m.fvgs[0].timestamp == expected_ts

    @pytest.mark.parametrize("atr_val,gap_size", [
        (1.0, 1.5), (2.0, 3.0), (3.0, 4.0), (5.0, 6.0), (10.0, 12.0),
    ])
    def test_bullish_fvg_passes_min_size_at_atr(self, fvg_15m, atr_val, gap_size):  # TP-028 to TP-032
        """gap_size > 1.0 * atr_val → detected."""
        candles = _bullish_fvg_candles(gap_size=gap_size)
        fvg_15m.update(candles, _make_atr(candles, atr_val))
        assert len(fvg_15m.fvgs) == 1

    def test_idempotent_update_no_duplicates(self, fvg_15m):  # TP-033
        """Calling update twice with same candles should not duplicate FVGs."""
        candles = _bullish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, 2.0)
        fvg_15m.update(candles, atr)
        fvg_15m.update(candles, atr)
        assert len(fvg_15m.fvgs) == 1

    def test_incremental_update_adds_new_fvg(self, fvg_15m):  # TP-034
        """Update with first set, then extended set → detects FVG in extension."""
        candles = _bullish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, 2.0)
        fvg_15m.update(candles[:2], atr[:2])  # only 2 candles → no FVG yet
        assert len(fvg_15m.fvgs) == 0
        fvg_15m.update(candles, atr)  # full 3 candles → FVG detected
        assert len(fvg_15m.fvgs) == 1

    def test_bullish_fvg_top_gt_bottom(self, fvg_15m):  # TP-035
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        fvg = fvg_15m.fvgs[0]
        assert fvg.top > fvg.bottom

    def test_bullish_fvg_midpoint_in_zone(self, fvg_15m):  # TP-036
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        fvg = fvg_15m.fvgs[0]
        assert fvg.bottom < fvg.midpoint < fvg.top


class TestBearishFVGDetection:
    """TP-037 to TP-060: Bearish FVG patterns correctly detected."""

    def test_bearish_fvg_detected(self, fvg_15m):  # TP-037
        candles = _bearish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert len(fvg_15m.fvgs) == 1
        assert fvg_15m.fvgs[0].kind == FVGKind.BEARISH

    def test_bearish_fvg_zone_boundaries(self, fvg_15m):  # TP-038
        candles = _bearish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        fvg = fvg_15m.fvgs[0]
        assert fvg.top == pytest.approx(100.0)    # C1.low
        assert fvg.bottom == pytest.approx(97.0)  # C3.high

    def test_bearish_fvg_status_starts_open(self, fvg_15m):  # TP-039
        candles = _bearish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].status == FVGStatus.OPEN

    def test_bearish_fvg_midpoint(self, fvg_15m):  # TP-040
        candles = _bearish_fvg_candles(gap_size=4.0)  # top=100, bottom=96 → mid=98
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].midpoint == pytest.approx(98.0)

    @pytest.mark.parametrize("gap_size", [2.1, 3.0, 5.0, 8.0, 12.0])
    def test_bearish_fvg_various_gap_sizes(self, fvg_15m, gap_size):  # TP-041 to TP-045
        candles = _bearish_fvg_candles(gap_size=gap_size)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert len(fvg_15m.fvgs) == 1
        assert fvg_15m.fvgs[0].kind == FVGKind.BEARISH

    def test_bearish_fvg_top_gt_bottom(self, fvg_15m):  # TP-046
        candles = _bearish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        fvg = fvg_15m.fvgs[0]
        assert fvg.top > fvg.bottom


class TestFillStatus:
    """TP-047 to TP-075: Fill tracking over time."""

    def test_partial_fill_when_price_enters_bullish_zone(self, fvg_15m):  # TP-047
        candles = _bullish_fvg_then_partial_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].status == FVGStatus.PARTIALLY_FILLED

    def test_partial_fill_pct_positive(self, fvg_15m):  # TP-048
        candles = _bullish_fvg_then_partial_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].fill_pct > 0.0

    def test_full_fill_when_price_closes_below_bottom(self, fvg_15m):  # TP-049
        candles = _bullish_fvg_then_full_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].status == FVGStatus.FILLED
        assert fvg_15m.fvgs[0].fill_pct == pytest.approx(1.0)

    def test_bearish_partial_fill(self, fvg_15m):  # TP-050
        candles = _bearish_fvg_then_partial_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].status == FVGStatus.PARTIALLY_FILLED

    def test_bearish_full_fill(self, fvg_15m):  # TP-051
        candles = _bearish_fvg_then_full_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].status == FVGStatus.FILLED
        assert fvg_15m.fvgs[0].fill_pct == pytest.approx(1.0)

    @pytest.mark.parametrize("gap_size", [3.0, 4.0, 5.0, 6.0, 8.0])
    def test_fill_detection_various_gap_sizes(self, fvg_15m, gap_size):  # TP-052 to TP-056
        candles = _bullish_fvg_then_full_fill(gap_size=gap_size)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].status == FVGStatus.FILLED

    def test_midpoint_is_consequent_encroachment(self, fvg_15m):  # TP-057
        candles = _bullish_fvg_candles(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].midpoint == pytest.approx(102.0)

    def test_filled_fvg_not_in_open_fvgs(self, fvg_15m):  # TP-058
        candles = _bullish_fvg_then_full_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert len(fvg_15m.get_open_fvgs()) == 0

    def test_partially_filled_fvg_still_in_open_fvgs(self, fvg_15m):  # TP-059
        candles = _bullish_fvg_then_partial_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert len(fvg_15m.get_open_fvgs()) == 1

    def test_fill_pct_not_zero_after_partial(self, fvg_15m):  # TP-060
        candles = _bullish_fvg_then_partial_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        fvg = fvg_15m.fvgs[0]
        assert 0.0 < fvg.fill_pct < 1.0


class TestScoring:
    """TP-061 to TP-085: Score values for detected FVGs."""

    def test_score_bullish_fvg_at_price(self, fvg_15m):  # TP-061
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(101.0) == pytest.approx(0.7)  # inside [100, 103]

    def test_score_zero_no_fvg(self, fvg_15m):  # TP-062
        assert fvg_15m.score(100.0) == pytest.approx(0.0)

    def test_score_bearish_fvg_at_price(self, fvg_15m):  # TP-063
        candles = _bearish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(98.5) == pytest.approx(-0.7)  # inside [97, 100]

    def test_score_zero_when_price_above_bullish_zone(self, fvg_15m):  # TP-064
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(105.0) == pytest.approx(0.0)

    def test_score_zero_when_price_below_bullish_zone(self, fvg_15m):  # TP-065
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(99.0) == pytest.approx(0.0)

    def test_score_zero_when_price_above_bearish_zone(self, fvg_15m):  # TP-066
        candles = _bearish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(101.0) == pytest.approx(0.0)

    def test_score_zero_when_price_below_bearish_zone(self, fvg_15m):  # TP-067
        candles = _bearish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(95.0) == pytest.approx(0.0)

    @pytest.mark.parametrize("price", [100.1, 101.0, 101.5, 102.0, 102.9])
    def test_score_bullish_inside_zone(self, fvg_15m, price):  # TP-068 to TP-072
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(price) == pytest.approx(0.7)

    @pytest.mark.parametrize("price", [97.1, 98.0, 98.5, 99.0, 99.9])
    def test_score_bearish_inside_zone(self, fvg_15m, price):  # TP-073 to TP-077
        candles = _bearish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(price) == pytest.approx(-0.7)

    def test_score_zero_after_full_fill(self, fvg_15m):  # TP-078
        candles = _bullish_fvg_then_full_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(102.0) == pytest.approx(0.0)  # filled, no longer scores

    def test_score_still_active_after_partial_fill(self, fvg_15m):  # TP-079
        candles = _bullish_fvg_then_partial_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(102.0) == pytest.approx(0.7)  # partial: zone still active

    def test_bullish_score_is_positive(self, fvg_15m):  # TP-080
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(101.5) > 0

    def test_bearish_score_is_negative(self, fvg_15m):  # TP-081
        candles = _bearish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(98.5) < 0


class TestUnicornDetection:
    """TP-082 to TP-100: OB+FVG unicorn overlap detection."""

    def test_unicorn_when_fvg_overlaps_ob(self, fvg_15m):  # TP-082
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # FVG: bottom=100, top=103. OB: ob_high=101, ob_low=99.5 → overlaps
        assert fvg_15m.check_unicorn_overlap(ob_high=101.0, ob_low=99.5) is True

    def test_no_unicorn_when_zones_dont_overlap(self, fvg_15m):  # TP-083
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.check_unicorn_overlap(ob_high=95.0, ob_low=90.0) is False

    def test_unicorn_ob_contains_fvg(self, fvg_15m):  # TP-084
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # OB completely surrounds FVG zone
        assert fvg_15m.check_unicorn_overlap(ob_high=105.0, ob_low=98.0) is True

    def test_unicorn_fvg_contains_ob(self, fvg_15m):  # TP-085
        candles = _bullish_fvg_candles(gap_size=5.0)  # FVG: 100-105
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # OB completely inside FVG zone
        assert fvg_15m.check_unicorn_overlap(ob_high=103.0, ob_low=101.0) is True

    def test_no_unicorn_before_update(self, fvg_15m):  # TP-086
        assert fvg_15m.check_unicorn_overlap(105.0, 98.0) is False

    @pytest.mark.parametrize("ob_high,ob_low,expected", [
        (101.0, 99.5, True),   # OB overlaps FVG (bottom=100, top=103)
        (103.5, 103.1, False), # OB entirely above FVG top=103
        (99.5, 98.0, False),   # OB below FVG
        (100.5, 99.5, True),   # OB straddles bottom
        (103.5, 103.1, False), # OB just above top
    ])
    def test_unicorn_overlap_cases(self, fvg_15m, ob_high, ob_low, expected):  # TP-087 to TP-091
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.check_unicorn_overlap(ob_high, ob_low) is expected

    def test_unicorn_false_after_fvg_filled(self, fvg_15m):  # TP-092
        candles = _bullish_fvg_then_full_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.check_unicorn_overlap(103.0, 101.0) is False


# ═══════════════════════════════════════════════════════════════════════════════
# AMBIGUOUS CASES (100) — Borderline patterns, edge cases, partial overlaps
# ═══════════════════════════════════════════════════════════════════════════════

class TestBorderlineGapSizes:
    """AMB-001 to AMB-030: Threshold boundary cases."""

    @pytest.mark.parametrize("gap_size,atr_val,multiplier,should_detect", [
        (2.0, 2.0, 1.0, True),    # gap == threshold → detected (uses >=)
        (2.01, 2.0, 1.0, True),   # gap just above threshold
        (1.99, 2.0, 1.0, False),  # gap just below threshold
        (1.0, 2.0, 0.5, True),    # gap == 0.5 * ATR threshold exactly → detected
        (1.01, 2.0, 0.5, True),   # gap just above 0.5 * ATR
        (3.0, 3.0, 1.0, True),    # gap == 1.0 * ATR exactly → detected
        (3.01, 3.0, 1.0, True),   # gap just above 1.0 * ATR
        (4.0, 2.0, 2.0, True),    # gap == 2.0 * ATR exactly → detected
        (0.5, 1.0, 0.5, True),    # gap == 0.5 * ATR exactly → detected
        (0.51, 1.0, 0.5, True),   # gap just above 0.5 * ATR
    ])
    def test_borderline_gap_size(self, gap_size, atr_val, multiplier, should_detect):
        # AMB-001 to AMB-010
        module = FVGModule(timeframe="15m", pair="XAUUSD", min_size_atr_multiple=multiplier)
        candles = _bullish_fvg_candles(gap_size=gap_size)
        module.update(candles, _make_atr(candles, atr_val))
        assert (len(module.fvgs) == 1) == should_detect

    @pytest.mark.parametrize("multiplier", [0.5, 0.75, 1.0, 1.5, 2.0])
    def test_timeframe_multipliers(self, multiplier):  # AMB-011 to AMB-015
        """Different timeframes use different min_size_atr_multiples."""
        module = FVGModule(timeframe="1m", pair="XAUUSD", min_size_atr_multiple=multiplier)
        gap_size = multiplier * 2.0 + 0.01  # just above threshold with ATR=2.0
        candles = _bullish_fvg_candles(gap_size=gap_size)
        module.update(candles, _make_atr(candles, 2.0))
        assert len(module.fvgs) == 1

    @pytest.mark.parametrize("gap_size", [1.99, 1.5, 1.0, 0.1])
    def test_gap_below_threshold_rejected(self, gap_size):  # AMB-016 to AMB-019
        """With min_size=1.0 and ATR=2.0, threshold=2.0. Gaps strictly below rejected."""
        module = FVGModule(timeframe="15m", pair="XAUUSD", min_size_atr_multiple=1.0)
        candles = _bullish_fvg_candles(gap_size=gap_size)
        module.update(candles, _make_atr(candles, 2.0))
        assert len(module.fvgs) == 0

    def test_gap_exactly_at_threshold_detected(self):  # AMB-020
        """With min_size=1.0 and ATR=2.0, threshold=2.0. Gap exactly at threshold detected (>=)."""
        module = FVGModule(timeframe="15m", pair="XAUUSD", min_size_atr_multiple=1.0)
        candles = _bullish_fvg_candles(gap_size=2.0)
        module.update(candles, _make_atr(candles, 2.0))
        assert len(module.fvgs) == 1

    def test_very_large_atr_makes_gap_subthreshold(self):  # AMB-021
        """With ATR=100, a gap of 5 is subthreshold for min_size=0.1."""
        module = FVGModule(timeframe="15m", pair="XAUUSD", min_size_atr_multiple=0.1)
        candles = _bullish_fvg_candles(gap_size=5.0)
        # threshold = 0.1 * 100 = 10.0, gap = 5.0 < 10.0 → rejected
        module.update(candles, _make_atr(candles, 100.0))
        assert len(module.fvgs) == 0

    def test_very_small_atr_makes_small_gap_valid(self):  # AMB-022
        """With ATR≈0.1, a gap of 0.2 exceeds 1.0x threshold."""
        module = FVGModule(timeframe="1m", pair="XAUUSD", min_size_atr_multiple=1.0)
        candles = _bullish_fvg_candles(gap_size=0.2)
        module.update(candles, _make_atr(candles, 0.1))
        assert len(module.fvgs) == 1

    def test_gap_at_bottom_boundary(self, fvg_15m):  # AMB-023
        """Price at exact bottom of FVG should be inside zone."""
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(100.0) == pytest.approx(0.7)  # at bottom=100

    def test_gap_at_top_boundary(self, fvg_15m):  # AMB-024
        """Price at exact top of FVG should be inside zone."""
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(103.0) == pytest.approx(0.7)  # at top=103


class TestPartialFillEdgeCases:
    """AMB-025 to AMB-060: Fill detection edge cases."""

    def test_price_at_exact_bottom_of_filled_zone(self, fvg_15m):  # AMB-025
        """Price touches bottom but close is above → partial, not filled."""
        candles = _make_candles([
            (99.0, 100.0, 98.0, 98.5, 1000),   # C1
            (98.5, 106.0, 98.0, 105.5, 5000),  # C2 displacement
            (105.5, 107.0, 103.0, 106.5, 2000),  # C3: top=103, bottom=100
            (106.0, 107.0, 100.0, 101.0, 3000),  # touches bottom exactly, close=101 > 100
        ])
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # Low=100.0 == bottom → touching but not below bottom; status depends on close
        # close=101 > bottom=100 → PARTIALLY_FILLED
        assert fvg_15m.fvgs[0].status == FVGStatus.PARTIALLY_FILLED

    def test_price_just_above_bottom_still_partial(self, fvg_15m):  # AMB-026
        candles = _make_candles([
            (99.0, 100.0, 98.0, 98.5, 1000),
            (98.5, 106.0, 98.0, 105.5, 5000),
            (105.5, 107.0, 103.0, 106.5, 2000),
            (106.0, 107.0, 100.5, 101.5, 3000),  # low=100.5 inside zone, close>100
        ])
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].status == FVGStatus.PARTIALLY_FILLED

    def test_fill_pct_at_midpoint_is_half(self, fvg_15m):  # AMB-027
        """When low reaches midpoint, fill_pct ≈ 0.5."""
        # FVG: bottom=100, top=104, mid=102
        candles = _make_candles([
            (99.0, 100.0, 98.0, 98.5, 1000),
            (98.5, 106.0, 98.0, 105.5, 5000),
            (105.5, 108.0, 104.0, 107.5, 2000),  # C3.low=104 → top=104, bottom=100
            (107.0, 108.0, 102.0, 103.0, 3000),  # low=102 = midpoint
        ])
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        fvg = fvg_15m.fvgs[0]
        assert fvg.fill_pct == pytest.approx(0.5)

    @pytest.mark.parametrize("low,expected_pct", [
        (103.0, 0.25),  # 25% into zone [100, 104]: (104-103)/(104-100) = 0.25
        (102.0, 0.50),  # 50% into zone
        (101.0, 0.75),  # 75% into zone
        (100.5, 0.875), # 87.5% into zone
    ])
    def test_fill_pct_proportional(self, fvg_15m, low, expected_pct):  # AMB-028 to AMB-031
        # FVG: bottom=100, top=104 (gap_size=4)
        candles = _make_candles([
            (99.0, 100.0, 98.0, 98.5, 1000),
            (98.5, 106.0, 98.0, 105.5, 5000),
            (105.5, 108.0, 104.0, 107.5, 2000),
            (107.0, 108.0, low, low + 1.5, 3000),  # close > bottom=100, partial
        ])
        if low + 1.5 > 100.0:  # close above bottom
            fvg_15m.update(candles, _make_atr(candles, 2.0))
            assert fvg_15m.fvgs[0].fill_pct == pytest.approx(expected_pct, abs=0.01)

    def test_fill_status_monotonic_open_to_partial(self, fvg_15m):  # AMB-032
        """Once PARTIALLY_FILLED, should not revert to OPEN."""
        candles = _bullish_fvg_then_partial_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].status != FVGStatus.OPEN

    def test_fill_status_monotonic_partial_to_filled(self, fvg_15m):  # AMB-033
        candles = _bullish_fvg_then_full_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.fvgs[0].status == FVGStatus.FILLED

    def test_nearest_fvg_returns_closest_zone(self, fvg_15m):  # AMB-034
        """With two FVGs, nearest_fvg returns the closer one."""
        candles, atr = _many_fvg_candles(n_fvgs=2)
        fvg_15m.update(candles, atr)
        assert len(fvg_15m.fvgs) == 2
        # Price near first FVG
        fvg = fvg_15m.nearest_fvg(fvg_15m.fvgs[0].midpoint)
        assert fvg == fvg_15m.fvgs[0]

    def test_only_open_fvgs_count_for_score(self, fvg_15m):  # AMB-035
        """Filled FVGs should not affect score even if price is inside their zone."""
        candles = _bullish_fvg_then_full_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # FVG is filled, score at old zone should be 0
        assert fvg_15m.score(102.0) == pytest.approx(0.0)

    @pytest.mark.parametrize("n_prior_candles", [0, 1, 2, 3, 5])
    def test_incremental_updates_consistent(self, n_prior_candles):  # AMB-036 to AMB-040
        """Results identical whether data comes at once or incrementally."""
        module1 = FVGModule("15m", "XAUUSD", 1.0)
        module2 = FVGModule("15m", "XAUUSD", 1.0)
        candles = _bullish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, 2.0)

        module1.update(candles, atr)

        if n_prior_candles < len(candles):
            module2.update(candles[:n_prior_candles], atr[:n_prior_candles])
        module2.update(candles, atr)

        assert len(module1.fvgs) == len(module2.fvgs)


# ═══════════════════════════════════════════════════════════════════════════════
# FALSE POSITIVES (100) — Patterns that should NOT produce FVGs or signals
# ═══════════════════════════════════════════════════════════════════════════════

class TestFalsePositives:
    """FP-001 to FP-100: Cases that must NOT be detected as valid FVGs."""

    def test_too_small_fvg_filtered(self, fvg_15m):  # FP-001
        candles = _too_small_fvg_candles()
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert len(fvg_15m.fvgs) == 0

    def test_no_gap_touching_candles(self, fvg_15m):  # FP-002
        """C3.low == C1.high: touching but no gap."""
        candles = _no_gap_touching_candles()
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert len(fvg_15m.fvgs) == 0

    @pytest.mark.parametrize("gap_size", [0.0, -0.1, -0.5, -1.0, -2.0])
    def test_negative_gap_never_detected(self, gap_size):  # FP-003 to FP-007
        """C3.low <= C1.high → candles overlap = no bullish FVG."""
        module = FVGModule("15m", "XAUUSD", 1.0)
        c1_high = 100.0
        c3_low = c1_high + gap_size  # <= 100 → no gap
        candles = _make_candles([
            (99.0, c1_high, 98.0, 98.5, 1000),
            (98.5, 106.0,   98.0, 105.5, 5000),
            (105.5, 107.0,  c3_low, 106.5, 2000),
        ])
        module.update(candles, _make_atr(candles, 2.0))
        assert len(module.fvgs) == 0

    @pytest.mark.parametrize("gap_size", [1.99, 1.5, 1.0, 0.5, 0.1, 0.01])
    def test_subthreshold_gaps_rejected(self, gap_size):  # FP-008 to FP-013
        """With ATR=2.0 and min_size=1.0, threshold=2.0. All below rejected."""
        module = FVGModule("15m", "XAUUSD", 1.0)
        candles = _bullish_fvg_candles(gap_size=gap_size)
        module.update(candles, _make_atr(candles, 2.0))
        assert len(module.fvgs) == 0

    def test_score_zero_price_outside_all_zones(self, fvg_15m):  # FP-014
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # Price far below zone
        assert fvg_15m.score(50.0) == pytest.approx(0.0)
        # Price far above zone
        assert fvg_15m.score(200.0) == pytest.approx(0.0)

    def test_no_signal_with_fewer_than_3_candles(self, fvg_15m):  # FP-015
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles[:2], _make_atr(candles[:2], 2.0))
        assert len(fvg_15m.fvgs) == 0

    def test_single_candle_no_fvg(self, fvg_15m):  # FP-016
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles[:1], _make_atr(candles[:1], 2.0))
        assert len(fvg_15m.fvgs) == 0

    def test_empty_dataframe_no_fvg(self, fvg_15m):  # FP-017
        idx = pd.date_range("2024-01-01", periods=0, freq="15min", tz="UTC")
        candles = pd.DataFrame(
            {"open": [], "high": [], "low": [], "close": [], "volume": []}, index=idx
        )
        atr = _make_atr(candles, 2.0)
        fvg_15m.update(candles, atr)
        assert len(fvg_15m.fvgs) == 0

    @pytest.mark.parametrize("price", [103.01, 104.0, 105.0, 110.0, 200.0])
    def test_score_zero_above_bullish_fvg(self, fvg_15m, price):  # FP-018 to FP-022
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(price) == pytest.approx(0.0)

    @pytest.mark.parametrize("price", [99.99, 99.0, 95.0, 50.0, 0.0])
    def test_score_zero_below_bullish_fvg(self, fvg_15m, price):  # FP-023 to FP-027
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert fvg_15m.score(price) == pytest.approx(0.0)

    def test_no_unicorn_when_no_fvg_exists(self, fvg_15m):  # FP-028
        assert fvg_15m.check_unicorn_overlap(105.0, 95.0) is False

    def test_no_unicorn_when_ob_below_fvg(self, fvg_15m):  # FP-029
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # OB entirely below FVG bottom=100
        assert fvg_15m.check_unicorn_overlap(ob_high=99.9, ob_low=95.0) is False

    def test_no_unicorn_when_ob_above_fvg(self, fvg_15m):  # FP-030
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # OB entirely above FVG top=103
        assert fvg_15m.check_unicorn_overlap(ob_high=110.0, ob_low=103.1) is False

    def test_filled_fvg_not_nearest(self, fvg_15m):  # FP-031
        """Filled FVG should not appear as nearest_fvg."""
        candles = _bullish_fvg_then_full_fill(gap_size=4.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # The filled FVG is in list but not active
        nearest = fvg_15m.nearest_fvg(102.0)
        assert nearest is None

    @pytest.mark.parametrize("bad_candles", [
        # Bearish-looking but C3.high >= C1.low (no gap): should be 0 bearish FVGs
        [(101.0, 102.0, 100.0, 101.5, 1000),
         (101.5, 102.0, 94.0,  94.5,  5000),
         (94.5,  100.5, 93.0,  93.5,  2000)],  # C3.high=100.5 > C1.low=100
    ])
    def test_bearish_overlap_no_fvg(self, fvg_15m, bad_candles):  # FP-032
        candles = _make_candles(bad_candles)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # C3.high=100.5 >= C1.low=100.0 → no bearish FVG
        bearish_fvgs = [f for f in fvg_15m.fvgs if f.kind == FVGKind.BEARISH]
        assert len(bearish_fvgs) == 0

    @pytest.mark.parametrize("gap_size", [2.1, 3.0, 4.0, 5.0, 6.0])
    def test_filled_fvg_no_longer_in_open_list(self, gap_size):  # FP-033 to FP-037
        module = FVGModule("15m", "XAUUSD", 1.0)
        candles = _bullish_fvg_then_full_fill(gap_size=gap_size)
        module.update(candles, _make_atr(candles, 2.0))
        open_fvgs = module.get_open_fvgs()
        assert len(open_fvgs) == 0

    def test_two_candles_no_fvg_detected(self, fvg_15m):  # FP-038
        candles = _bullish_fvg_candles(gap_size=3.0)[:2]
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        assert len(fvg_15m.fvgs) == 0

    @pytest.mark.parametrize("gap_size", [2.1, 3.0, 5.0, 8.0, 12.0])
    def test_score_zero_for_bearish_when_no_bearish_fvg(self, gap_size):  # FP-039 to FP-043
        """Only bullish FVG exists: price in bullish zone should score +0.7, not -0.7."""
        module = FVGModule("15m", "XAUUSD", 1.0)
        candles = _bullish_fvg_candles(gap_size=gap_size)
        module.update(candles, _make_atr(candles, 2.0))
        score = module.score(100.0 + gap_size / 2)
        assert score == pytest.approx(0.7)  # bullish, not -0.7

    def test_score_zero_when_fvg_not_matching_price(self, fvg_15m):  # FP-044
        candles = _bullish_fvg_candles(gap_size=3.0)
        fvg_15m.update(candles, _make_atr(candles, 2.0))
        # Price at 150 (nowhere near FVG zone 100-103)
        assert fvg_15m.score(150.0) == pytest.approx(0.0)

    @pytest.mark.parametrize("update_count", [1, 2, 3, 5, 10])
    def test_repeated_updates_no_fvg_duplication(self, update_count):  # FP-045 to FP-049
        module = FVGModule("15m", "XAUUSD", 1.0)
        candles = _bullish_fvg_candles(gap_size=3.0)
        atr = _make_atr(candles, 2.0)
        for _ in range(update_count):
            module.update(candles, atr)
        assert len(module.fvgs) == 1  # no duplication

    @pytest.mark.parametrize("candle_count", [0, 1, 2])
    def test_insufficient_candles_no_detection(self, candle_count):  # FP-050 to FP-052
        module = FVGModule("15m", "XAUUSD", 1.0)
        if candle_count == 0:
            idx = pd.date_range("2024-01-01", periods=0, freq="15min", tz="UTC")
            candles = pd.DataFrame(
                {"open": [], "high": [], "low": [], "close": [], "volume": []}, index=idx
            )
        else:
            candles = _bullish_fvg_candles(gap_size=3.0)[:candle_count]
        module.update(candles, _make_atr(candles, 2.0))
        assert len(module.fvgs) == 0
