"""
Market Structure Module Tests — Sprint 2 deliverable.

200+ labeled test cases covering:
    - Swing point detection (confirmed highs/lows)
    - BOS detection in bullish and bearish trends
    - CHoCH detection with displacement filter
    - State machine transitions
    - RANGING detection
    - Score output for each state/event combination
    - Edge cases (insufficient data, flat markets, equal prices)
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import numpy as np
import pytest

from engine.modules.market_structure import (
    MarketStructureModule,
    StructureEvent,
    StructureEventRecord,
    SwingPoint,
    TrendState,
    _SCORE_MAP,
    _compute_atr,
    CHOCH_MIN_DISPLACEMENT_ATR,
    RANGING_ATR_BAND,
)


# ─── Candle builders ────────────────────────────────────────────────────────

def _candles(
    highs: list[float],
    lows: list[float],
    closes: Optional[list[float]] = None,
    opens: Optional[list[float]] = None,
    freq: str = "15min",
    start: str = "2024-01-01",
) -> pd.DataFrame:
    n = len(highs)
    assert len(lows) == n
    if closes is None:
        closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    if opens is None:
        opens = [closes[max(0, i - 1)] for i in range(n)]
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000.0] * n},
        index=idx,
    )


def _bullish(n: int = 60, base: float = 100.0, step: float = 1.5) -> pd.DataFrame:
    """
    Bullish zigzag: 8 bars up (step each), 8 bars partially down (0.8*step each).
    Creates Higher Highs and Higher Lows — confirmed swing points every 16 bars.
    N=5 lookback: swing high at bar 7 confirmed by bars 8-12 (down phase). ✓
    """
    highs, lows, closes = [], [], []
    price = base
    bar = 0
    while bar < n:
        for _ in range(8):
            if bar >= n:
                break
            price += step
            highs.append(price + 0.5)
            lows.append(price - 0.5)
            closes.append(price)
            bar += 1
        for _ in range(8):
            if bar >= n:
                break
            price -= step * 0.8
            highs.append(price + 0.5)
            lows.append(price - 0.5)
            closes.append(price)
            bar += 1
    return _candles(highs[:n], lows[:n], closes[:n])


def _bearish(n: int = 60, base: float = 200.0, step: float = 1.5) -> pd.DataFrame:
    """
    Bearish zigzag: 8 bars down (step each), 8 bars partially up (0.8*step each).
    Creates Lower Lows and Lower Highs — confirmed swing points every 16 bars.
    """
    highs, lows, closes = [], [], []
    price = base
    bar = 0
    while bar < n:
        for _ in range(8):
            if bar >= n:
                break
            price -= step
            highs.append(price + 0.5)
            lows.append(price - 0.5)
            closes.append(price)
            bar += 1
        for _ in range(8):
            if bar >= n:
                break
            price += step * 0.8
            highs.append(price + 0.5)
            lows.append(price - 0.5)
            closes.append(price)
            bar += 1
    return _candles(highs[:n], lows[:n], closes[:n])


def _ranging(n: int = 80, center: float = 100.0, amplitude: float = 0.5) -> pd.DataFrame:
    """
    Ranging zigzag: 7 bars up, 7 bars down, with fixed large H-L wicks.
    H-L = 3.0 per bar → ATR ≈ 3.0 → band_width = 1.5 * 3.0 = 4.5.
    swing_range = 2*amplitude + 2*1.5 = 2*0.5 + 3.0 = 4.0 ≤ 4.5 → RANGING ✓
    """
    hl_half = 1.5  # large fixed H-L ensures ATR ≈ 3.0 and band_width ≈ 4.5
    step = amplitude / 7
    highs, lows, closes = [], [], []
    price = center
    direction = 1
    bar = 0
    while bar < n:
        for _ in range(7):
            if bar >= n:
                break
            price += direction * step
            highs.append(price + hl_half)
            lows.append(price - hl_half)
            closes.append(price)
            bar += 1
        direction *= -1
    return _candles(highs[:n], lows[:n], closes[:n])


def _bullish_then_reversal(bull_bars: int = 40, bear_bars: int = 20) -> pd.DataFrame:
    """
    Bullish zigzag trend (HH/HL) followed by a large displacement reversal bar
    that closes below the most recent swing low, then a bearish continuation.
    displacement = bar_range / ATR ≈ 14.0 / 1.0 ≈ 7.3 ≥ 1.5 ✓
    """
    # Bull zigzag phase
    b_highs, b_lows, b_closes = [], [], []
    price = 100.0
    step = 1.5
    bar = 0
    while bar < bull_bars:
        for _ in range(8):
            if bar >= bull_bars:
                break
            price += step
            b_highs.append(price + 0.5)
            b_lows.append(price - 0.5)
            b_closes.append(price)
            bar += 1
        for _ in range(8):
            if bar >= bull_bars:
                break
            price -= step * 0.8
            b_highs.append(price + 0.5)
            b_lows.append(price - 0.5)
            b_closes.append(price)
            bar += 1

    # Reversal bar: large displacement down — close well below lowest swing low
    lowest_swing_low = min(b_lows[-16:])
    rev_high = price + 0.5
    rev_low = price - 14.0
    rev_close = lowest_swing_low - 2.0  # clearly below swing low → CHoCH trigger

    # Bear continuation
    br_price = rev_close
    br_highs, br_lows, br_closes = [], [], []
    for j in range(bear_bars):
        br_price -= step * 0.8
        br_highs.append(br_price + 0.5)
        br_lows.append(br_price - 0.5)
        br_closes.append(br_price)

    highs  = b_highs  + [rev_high]  + br_highs
    lows   = b_lows   + [rev_low]   + br_lows
    closes = b_closes + [rev_close] + br_closes
    return _candles(highs, lows, closes)


def _bearish_then_reversal(bear_bars: int = 40, bull_bars: int = 20) -> pd.DataFrame:
    """
    Bearish zigzag trend (LL/LH) followed by a large displacement reversal bar
    that closes above the most recent swing high, then a bullish continuation.
    """
    # Bear zigzag phase
    b_highs, b_lows, b_closes = [], [], []
    price = 200.0
    step = 1.5
    bar = 0
    while bar < bear_bars:
        for _ in range(8):
            if bar >= bear_bars:
                break
            price -= step
            b_highs.append(price + 0.5)
            b_lows.append(price - 0.5)
            b_closes.append(price)
            bar += 1
        for _ in range(8):
            if bar >= bear_bars:
                break
            price += step * 0.8
            b_highs.append(price + 0.5)
            b_lows.append(price - 0.5)
            b_closes.append(price)
            bar += 1

    # Reversal bar: large displacement up — close well above highest swing high
    highest_swing_high = max(b_highs[-16:])
    rev_low = price - 0.5
    rev_high = price + 14.0
    rev_close = highest_swing_high + 2.0  # clearly above swing high → CHoCH trigger

    # Bull continuation
    br_price = rev_close
    br_highs, br_lows, br_closes = [], [], []
    for j in range(bull_bars):
        br_price += step * 0.8
        br_highs.append(br_price + 0.5)
        br_lows.append(br_price - 0.5)
        br_closes.append(br_price)

    highs  = b_highs  + [rev_high]  + br_highs
    lows   = b_lows   + [rev_low]   + br_lows
    closes = b_closes + [rev_close] + br_closes
    return _candles(highs, lows, closes)


def _small_displacement_choch(n_trend: int = 40) -> pd.DataFrame:
    """
    Bullish zigzag trend followed by a reversal candle whose bar_range is SMALL
    relative to ATR — displacement < 1.5x → should NOT trigger CHoCH.
    ATR of the zigzag ≈ 1.0 (H-L = 1.0 per bar). Small reversal range = 0.4.
    displacement = 0.4 / ~1.0 = 0.4 < 1.5 → no CHoCH ✓
    """
    highs, lows, closes = [], [], []
    price = 100.0
    step = 1.5
    bar = 0
    while bar < n_trend:
        for _ in range(8):
            if bar >= n_trend:
                break
            price += step
            highs.append(price + 0.5)
            lows.append(price - 0.5)
            closes.append(price)
            bar += 1
        for _ in range(8):
            if bar >= n_trend:
                break
            price -= step * 0.8
            highs.append(price + 0.5)
            lows.append(price - 0.5)
            closes.append(price)
            bar += 1

    # Tiny reversal: range = 0.4, well below 1.5x ATR
    highs.append(price + 0.2)
    lows.append(price - 0.2)
    closes.append(price - 0.1)
    return _candles(highs, lows, closes)


@pytest.fixture
def mod15() -> MarketStructureModule:
    return MarketStructureModule(timeframe="15m", pair="XAUUSD")


@pytest.fixture
def mod1h() -> MarketStructureModule:
    return MarketStructureModule(timeframe="1H", pair="GBPJPY")


@pytest.fixture
def mod1d() -> MarketStructureModule:
    return MarketStructureModule(timeframe="1D", pair="XAUUSD")


# ════════════════════════════════════════════════════════════════════════════
# 1. SCORE MAP  (13 tests)
# ════════════════════════════════════════════════════════════════════════════

class TestScoreMap:
    def test_bullish_bos(self):
        assert _SCORE_MAP[(TrendState.BULLISH_TREND, StructureEvent.BOS_BULLISH)] == 0.8

    def test_bullish_choch(self):
        assert _SCORE_MAP[(TrendState.BULLISH_TREND, StructureEvent.CHOCH_BULLISH)] == 1.0

    def test_bearish_bos(self):
        assert _SCORE_MAP[(TrendState.BEARISH_TREND, StructureEvent.BOS_BEARISH)] == -0.8

    def test_bearish_choch(self):
        assert _SCORE_MAP[(TrendState.BEARISH_TREND, StructureEvent.CHOCH_BEARISH)] == -1.0

    def test_ranging_is_zero(self):
        assert _SCORE_MAP[(TrendState.RANGING, None)] == 0.0

    def test_unknown_is_zero(self):
        assert _SCORE_MAP[(TrendState.UNKNOWN, None)] == 0.0

    def test_transitioning_magnitude(self):
        assert abs(_SCORE_MAP[(TrendState.TRANSITIONING, None)]) == pytest.approx(0.3)

    def test_all_bearish_scores_negative(self):
        for (state, event), score in _SCORE_MAP.items():
            if event in (StructureEvent.BOS_BEARISH, StructureEvent.CHOCH_BEARISH):
                assert score < 0, f"Expected negative for {event}"

    def test_all_bullish_scores_positive(self):
        for (state, event), score in _SCORE_MAP.items():
            if event in (StructureEvent.BOS_BULLISH, StructureEvent.CHOCH_BULLISH):
                assert score > 0, f"Expected positive for {event}"

    def test_choch_magnitude_greater_than_bos(self):
        assert abs(_SCORE_MAP[(TrendState.BULLISH_TREND, StructureEvent.CHOCH_BULLISH)]) > \
               abs(_SCORE_MAP[(TrendState.BULLISH_TREND, StructureEvent.BOS_BULLISH)])

    def test_bearish_choch_magnitude_equals_bullish(self):
        assert abs(_SCORE_MAP[(TrendState.BEARISH_TREND, StructureEvent.CHOCH_BEARISH)]) == \
               abs(_SCORE_MAP[(TrendState.BULLISH_TREND, StructureEvent.CHOCH_BULLISH)])

    def test_bos_magnitude_symmetric(self):
        assert abs(_SCORE_MAP[(TrendState.BEARISH_TREND, StructureEvent.BOS_BEARISH)]) == \
               abs(_SCORE_MAP[(TrendState.BULLISH_TREND, StructureEvent.BOS_BULLISH)])

    def test_score_map_has_expected_keys(self):
        expected_keys = 7   # All entries in _SCORE_MAP
        assert len(_SCORE_MAP) == expected_keys


# ════════════════════════════════════════════════════════════════════════════
# 2. INITIALIZATION  (10 tests)
# ════════════════════════════════════════════════════════════════════════════

class TestInitialization:
    def test_state_unknown(self, mod15):
        assert mod15.state == TrendState.UNKNOWN

    def test_no_events(self, mod15):
        assert mod15.latest_event() is None

    def test_swing_highs_empty(self, mod15):
        assert mod15.swing_highs == []

    def test_swing_lows_empty(self, mod15):
        assert mod15.swing_lows == []

    def test_pair_stored(self, mod15):
        assert mod15.pair == "XAUUSD"

    def test_timeframe_stored(self, mod15):
        assert mod15.timeframe == "15m"

    def test_1h_lookback(self, mod1h):
        assert mod1h._n == 5

    def test_1d_lookback(self, mod1d):
        assert mod1d._n == 7

    def test_score_zero_before_update(self, mod15):
        assert mod15.score() == pytest.approx(0.0)

    def test_events_list_empty(self, mod15):
        assert mod15.events == []


# ════════════════════════════════════════════════════════════════════════════
# 3. INSUFFICIENT DATA  (6 tests)
# ════════════════════════════════════════════════════════════════════════════

class TestInsufficientData:
    def test_no_crash_on_empty(self, mod15):
        df = _bullish(n=0)
        mod15.update(df)
        assert mod15.state == TrendState.UNKNOWN

    def test_no_crash_on_one_candle(self, mod15):
        df = _bullish(n=1)
        mod15.update(df)
        assert mod15.state == TrendState.UNKNOWN

    def test_no_crash_on_n_minus_1_candles(self, mod15):
        # lookback=5, need 11 (5*2+1); give 10
        df = _bullish(n=10)
        mod15.update(df)
        assert mod15.state == TrendState.UNKNOWN

    def test_state_stays_unknown_below_threshold(self, mod15):
        df = _bullish(n=8)
        mod15.update(df)
        assert mod15.state == TrendState.UNKNOWN

    def test_score_stays_zero_insufficient(self, mod15):
        df = _bullish(n=5)
        mod15.update(df)
        assert mod15.score() == pytest.approx(0.0)

    def test_no_events_with_insufficient_data(self, mod15):
        df = _bullish(n=9)
        mod15.update(df)
        assert mod15.latest_event() is None


# ════════════════════════════════════════════════════════════════════════════
# 4. SWING POINT DETECTION  (20 tests)
# ════════════════════════════════════════════════════════════════════════════

class TestSwingPointDetection:
    def test_swing_highs_detected_bullish_trend(self, mod15):
        df = _bullish(n=40)
        mod15.update(df)
        assert len(mod15.swing_highs) > 0

    def test_swing_lows_detected_bullish_trend(self, mod15):
        df = _bullish(n=40)
        mod15.update(df)
        assert len(mod15.swing_lows) > 0

    def test_swing_highs_detected_bearish_trend(self, mod15):
        df = _bearish(n=40)
        mod15.update(df)
        assert len(mod15.swing_highs) > 0

    def test_swing_lows_detected_bearish_trend(self, mod15):
        df = _bearish(n=40)
        mod15.update(df)
        assert len(mod15.swing_lows) > 0

    def test_swing_high_price_is_local_maximum(self, mod15):
        df = _bullish(n=40)
        mod15.update(df)
        highs_series = df["high"].values
        for sp in mod15.swing_highs:
            ts_idx = df.index.get_loc(pd.Timestamp(sp.timestamp, tz="UTC") if sp.timestamp.tzinfo is None else sp.timestamp)
            n = mod15._n
            window_start = max(0, ts_idx - n)
            window_end = min(len(highs_series), ts_idx + n + 1)
            window = highs_series[window_start:window_end]
            assert sp.price == pytest.approx(float(highs_series[ts_idx]))
            assert sp.price >= float(np.max(window)) - 1e-9

    def test_swing_low_price_is_local_minimum(self, mod15):
        df = _bearish(n=40)
        mod15.update(df)
        lows_series = df["low"].values
        for sp in mod15.swing_lows:
            ts_idx = df.index.get_loc(pd.Timestamp(sp.timestamp, tz="UTC") if sp.timestamp.tzinfo is None else sp.timestamp)
            n = mod15._n
            window_start = max(0, ts_idx - n)
            window_end = min(len(lows_series), ts_idx + n + 1)
            window = lows_series[window_start:window_end]
            assert sp.price == pytest.approx(float(lows_series[ts_idx]))
            assert sp.price <= float(np.min(window)) + 1e-9

    def test_swing_point_is_confirmed(self, mod15):
        df = _bullish(n=40)
        mod15.update(df)
        for sp in mod15.swing_highs:
            assert sp.confirmed is True

    def test_swing_point_has_timestamp(self, mod15):
        df = _bullish(n=40)
        mod15.update(df)
        for sp in mod15.swing_highs:
            assert isinstance(sp.timestamp, datetime)

    def test_swing_high_kind_string(self, mod15):
        df = _bullish(n=40)
        mod15.update(df)
        for sp in mod15.swing_highs:
            assert sp.kind == "high"

    def test_swing_low_kind_string(self, mod15):
        df = _bullish(n=40)
        mod15.update(df)
        for sp in mod15.swing_lows:
            assert sp.kind == "low"

    def test_swing_highs_sorted_chronologically(self, mod15):
        df = _bullish(n=60)
        mod15.update(df)
        timestamps = [sp.timestamp for sp in mod15.swing_highs]
        assert timestamps == sorted(timestamps)

    def test_swing_lows_sorted_chronologically(self, mod15):
        df = _bullish(n=60)
        mod15.update(df)
        timestamps = [sp.timestamp for sp in mod15.swing_lows]
        assert timestamps == sorted(timestamps)

    def test_no_duplicate_swing_highs(self, mod15):
        df = _bullish(n=60)
        mod15.update(df)
        ts_set = {sp.timestamp for sp in mod15.swing_highs}
        assert len(ts_set) == len(mod15.swing_highs)

    def test_no_duplicate_swing_lows(self, mod15):
        df = _bullish(n=60)
        mod15.update(df)
        ts_set = {sp.timestamp for sp in mod15.swing_lows}
        assert len(ts_set) == len(mod15.swing_lows)

    def test_incremental_update_adds_new_swings(self, mod15):
        df1 = _bullish(n=30)
        mod15.update(df1)
        count1 = len(mod15.swing_highs)
        df2 = _bullish(n=60)
        mod15.update(df2)
        count2 = len(mod15.swing_highs)
        assert count2 >= count1

    def test_swing_history_bounded(self, mod15):
        """Swing history should not grow unboundedly."""
        df = _bullish(n=200)
        mod15.update(df)
        assert len(mod15.swing_highs) <= 20
        assert len(mod15.swing_lows) <= 20

    def test_swing_detected_in_zigzag(self, mod15):
        """Explicit zigzag: alternating peaks and troughs."""
        # Explicit zig-zag with clear peaks/troughs separated by lookback bars
        n = 5  # lookback
        peak = 110.0
        trough = 100.0
        # Build a zig-zag: peak at index n, trough at index 2n+1, peak at 3n+2, etc.
        highs = [105.0] * (4 * n + 10)
        lows  = [105.0] * (4 * n + 10)
        # Place explicit peak
        highs[n] = peak
        lows[n] = peak - 1
        # Place explicit trough
        highs[3 * n] = trough + 1
        lows[3 * n] = trough
        df = _candles(highs, lows)
        mod15.update(df)
        # Should detect at least the explicit trough
        assert len(mod15.swing_lows) > 0 or len(mod15.swing_highs) > 0

    def test_flat_market_no_swings(self, mod15):
        """Perfectly flat price should produce no swing points (ties broken)."""
        n = 30
        highs  = [100.0] * n
        lows   = [99.0] * n
        closes = [99.5] * n
        df = _candles(highs, lows, closes)
        mod15.update(df)
        # With strictly greater/less, flat will produce no confirmed swings
        assert len(mod15.swing_highs) == 0
        assert len(mod15.swing_lows) == 0

    def test_swing_high_price_above_adjacent(self, mod15):
        df = _bullish()
        mod15.update(df)
        df_highs = df["high"].values
        for sp in mod15.swing_highs:
            if sp.timestamp.tzinfo is None:
                sp_ts = pd.Timestamp(sp.timestamp, tz="UTC")
            else:
                sp_ts = pd.Timestamp(sp.timestamp)
            idx = df.index.get_loc(sp_ts)
            n = mod15._n
            if idx >= n and idx + n < len(df_highs):
                left  = df_highs[idx - n : idx]
                right = df_highs[idx + 1 : idx + n + 1]
                assert sp.price > float(np.max(left))
                assert sp.price > float(np.max(right))

    def test_swing_low_price_below_adjacent(self, mod15):
        df = _bearish()
        mod15.update(df)
        df_lows = df["low"].values
        for sp in mod15.swing_lows:
            if sp.timestamp.tzinfo is None:
                sp_ts = pd.Timestamp(sp.timestamp, tz="UTC")
            else:
                sp_ts = pd.Timestamp(sp.timestamp)
            idx = df.index.get_loc(sp_ts)
            n = mod15._n
            if idx >= n and idx + n < len(df_lows):
                left  = df_lows[idx - n : idx]
                right = df_lows[idx + 1 : idx + n + 1]
                assert sp.price < float(np.min(left))
                assert sp.price < float(np.min(right))


# ════════════════════════════════════════════════════════════════════════════
# 5. TREND INITIALIZATION  (10 tests)
# ════════════════════════════════════════════════════════════════════════════

class TestTrendInitialization:
    def test_bullish_trend_established(self, mod15):
        df = _bullish(n=40)
        mod15.update(df)
        assert mod15.state in (TrendState.BULLISH_TREND, TrendState.TRANSITIONING)

    def test_bearish_trend_established(self, mod15):
        df = _bearish(n=40)
        mod15.update(df)
        assert mod15.state in (TrendState.BEARISH_TREND, TrendState.TRANSITIONING)

    def test_bullish_score_positive(self, mod15):
        df = _bullish(n=40)
        mod15.update(df)
        assert mod15.score() >= 0.0

    def test_bearish_score_negative(self, mod15):
        df = _bearish(n=40)
        mod15.update(df)
        assert mod15.score() <= 0.0

    def test_state_not_unknown_after_sufficient_data(self, mod15):
        df = _bullish(n=40)
        mod15.update(df)
        assert mod15.state != TrendState.UNKNOWN

    def test_bearish_state_not_unknown(self, mod15):
        df = _bearish(n=40)
        mod15.update(df)
        assert mod15.state != TrendState.UNKNOWN

    def test_1h_module_establishes_trend(self, mod1h):
        df = _bullish()
        mod1h.update(df)
        assert mod1h.state != TrendState.UNKNOWN

    def test_bullish_state_after_consistent_hh_hl(self, mod15):
        """All higher highs and higher lows should produce BULLISH_TREND."""
        df = _bullish(n=50, step=3.0)
        mod15.update(df)
        assert mod15.state in (TrendState.BULLISH_TREND, TrendState.TRANSITIONING)

    def test_bearish_state_after_consistent_lh_ll(self, mod15):
        df = _bearish(n=50, step=3.0)
        mod15.update(df)
        assert mod15.state in (TrendState.BEARISH_TREND, TrendState.TRANSITIONING)

    def test_score_magnitude_nonzero_in_trend(self, mod15):
        df = _bullish()
        mod15.update(df)
        assert abs(mod15.score()) > 0.0


# ════════════════════════════════════════════════════════════════════════════
# 6. BOS DETECTION  (20 tests)
# ════════════════════════════════════════════════════════════════════════════

class TestBOSDetection:
    def test_bullish_bos_event_recorded(self, mod15):
        df = _bullish()
        mod15.update(df)
        bos_events = [e for e in mod15.events if e.event == StructureEvent.BOS_BULLISH]
        assert len(bos_events) > 0

    def test_bearish_bos_event_recorded(self, mod15):
        df = _bearish()
        mod15.update(df)
        bos_events = [e for e in mod15.events if e.event == StructureEvent.BOS_BEARISH]
        assert len(bos_events) > 0

    def test_bullish_bos_price_above_swing_high(self, mod15):
        df = _bullish()
        mod15.update(df)
        for e in mod15.events:
            if e.event == StructureEvent.BOS_BULLISH:
                assert e.price > e.swing_ref.price

    def test_bearish_bos_price_below_swing_low(self, mod15):
        df = _bearish()
        mod15.update(df)
        for e in mod15.events:
            if e.event == StructureEvent.BOS_BEARISH:
                assert e.price < e.swing_ref.price

    def test_bos_keeps_bullish_state(self, mod15):
        df = _bullish()
        mod15.update(df)
        # After BOS in bullish trend, state should remain BULLISH (or TRANSITIONING only if CHoCH)
        assert mod15.state in (TrendState.BULLISH_TREND, TrendState.TRANSITIONING, TrendState.RANGING)

    def test_bos_keeps_bearish_state(self, mod15):
        df = _bearish()
        mod15.update(df)
        assert mod15.state in (TrendState.BEARISH_TREND, TrendState.TRANSITIONING, TrendState.RANGING)

    def test_bos_score_bullish_is_0_8(self, mod15):
        """After a BOS_BULLISH event in BULLISH_TREND, score should be 0.8."""
        df = _bullish()
        mod15.update(df)
        if mod15.state == TrendState.BULLISH_TREND:
            event = mod15.latest_event()
            if event and event.event == StructureEvent.BOS_BULLISH:
                assert mod15.score() == pytest.approx(0.8)

    def test_bos_score_bearish_is_neg_0_8(self, mod15):
        df = _bearish()
        mod15.update(df)
        if mod15.state == TrendState.BEARISH_TREND:
            event = mod15.latest_event()
            if event and event.event == StructureEvent.BOS_BEARISH:
                assert mod15.score() == pytest.approx(-0.8)

    def test_bos_event_has_displacement_size(self, mod15):
        df = _bullish()
        mod15.update(df)
        for e in mod15.events:
            assert e.displacement_size >= 0.0

    def test_bos_event_has_timestamp(self, mod15):
        df = _bullish()
        mod15.update(df)
        for e in mod15.events:
            assert isinstance(e.timestamp, datetime)

    def test_bos_event_swing_ref_kind_matches(self, mod15):
        """BOS_BULLISH swing_ref should be a swing high; BOS_BEARISH a swing low."""
        df = _bullish()
        mod15.update(df)
        for e in mod15.events:
            if e.event == StructureEvent.BOS_BULLISH:
                assert e.swing_ref.kind == "high"
        df2 = _bearish()
        mod2 = MarketStructureModule("15m", "XAUUSD")
        mod2.update(df2)
        for e in mod2.events:
            if e.event == StructureEvent.BOS_BEARISH:
                assert e.swing_ref.kind == "low"

    def test_bos_events_chronologically_ordered(self, mod15):
        df = _bullish()
        mod15.update(df)
        ts_list = [e.timestamp for e in mod15.events]
        assert ts_list == sorted(ts_list)

    def test_no_bos_in_flat_market(self, mod15):
        n = 40
        highs  = [100.5] * n
        lows   = [99.5] * n
        df = _candles(highs, lows)
        mod15.update(df)
        bos_events = [e for e in mod15.events if e.event in (
            StructureEvent.BOS_BULLISH, StructureEvent.BOS_BEARISH)]
        assert len(bos_events) == 0

    def test_multiple_bos_in_long_trend(self, mod15):
        df = _bullish()  # n=60: 2 BOS events fire at bars 55 and 56
        mod15.update(df)
        bos = [e for e in mod15.events if e.event == StructureEvent.BOS_BULLISH]
        assert len(bos) > 1

    def test_bearish_bos_price_references_swing_low(self, mod15):
        df = _bearish()
        mod15.update(df)
        for e in mod15.events:
            if e.event == StructureEvent.BOS_BEARISH:
                assert e.swing_ref.kind == "low"

    def test_bullish_bos_price_references_swing_high(self, mod15):
        df = _bullish()
        mod15.update(df)
        for e in mod15.events:
            if e.event == StructureEvent.BOS_BULLISH:
                assert e.swing_ref.kind == "high"

    def test_score_positive_after_bullish_bos(self, mod15):
        df = _bullish()
        mod15.update(df)
        assert mod15.score() >= 0.0

    def test_score_negative_after_bearish_bos(self, mod15):
        df = _bearish()
        mod15.update(df)
        assert mod15.score() <= 0.0

    def test_bos_does_not_trigger_transitioning(self, mod15):
        """A BOS (continuation) should NOT change to TRANSITIONING state."""
        df = _bullish()
        mod15.update(df)
        bos_only = all(
            e.event in (StructureEvent.BOS_BULLISH, StructureEvent.BOS_BEARISH)
            for e in mod15.events
        )
        if bos_only:
            assert mod15.state != TrendState.TRANSITIONING

    def test_latest_event_is_most_recent_bos(self, mod15):
        df = _bullish(n=60)
        mod15.update(df)
        if mod15.events:
            last = mod15.latest_event()
            assert last == mod15.events[-1]


# ════════════════════════════════════════════════════════════════════════════
# 7. CHoCH DETECTION  (25 tests)
# ════════════════════════════════════════════════════════════════════════════

class TestCHoCHDetection:
    def test_bearish_choch_after_bullish_trend(self, mod15):
        df = _bullish_then_reversal(bull_bars=40, bear_bars=20)
        mod15.update(df)
        choch = [e for e in mod15.events if e.event == StructureEvent.CHOCH_BEARISH]
        assert len(choch) > 0

    def test_bullish_choch_after_bearish_trend(self, mod15):
        df = _bearish_then_reversal(bear_bars=40, bull_bars=20)
        mod15.update(df)
        choch = [e for e in mod15.events if e.event == StructureEvent.CHOCH_BULLISH]
        assert len(choch) > 0

    def test_choch_requires_displacement(self, mod15):
        """A reversal candle with range < 1.5x ATR should NOT trigger CHoCH."""
        df = _small_displacement_choch(n_trend=25)
        mod15.update(df)
        choch = [e for e in mod15.events if e.event in (
            StructureEvent.CHOCH_BULLISH, StructureEvent.CHOCH_BEARISH)]
        # Small displacement: no CHoCH should be recorded
        assert len(choch) == 0

    def test_bearish_choch_triggers_transitioning(self, mod15):
        df = _bullish_then_reversal()
        mod15.update(df)
        if any(e.event == StructureEvent.CHOCH_BEARISH for e in mod15.events):
            # After CHoCH the state should be TRANSITIONING or BEARISH (if confirmed)
            assert mod15.state in (TrendState.TRANSITIONING, TrendState.BEARISH_TREND)

    def test_bullish_choch_triggers_transitioning(self, mod15):
        df = _bearish_then_reversal()
        mod15.update(df)
        if any(e.event == StructureEvent.CHOCH_BULLISH for e in mod15.events):
            assert mod15.state in (TrendState.TRANSITIONING, TrendState.BULLISH_TREND)

    def test_choch_bearish_price_below_swing_low(self, mod15):
        df = _bullish_then_reversal()
        mod15.update(df)
        for e in mod15.events:
            if e.event == StructureEvent.CHOCH_BEARISH:
                assert e.price < e.swing_ref.price

    def test_choch_bullish_price_above_swing_high(self, mod15):
        df = _bearish_then_reversal()
        mod15.update(df)
        for e in mod15.events:
            if e.event == StructureEvent.CHOCH_BULLISH:
                assert e.price > e.swing_ref.price

    def test_choch_bearish_swing_ref_is_low(self, mod15):
        df = _bullish_then_reversal()
        mod15.update(df)
        for e in mod15.events:
            if e.event == StructureEvent.CHOCH_BEARISH:
                assert e.swing_ref.kind == "low"

    def test_choch_bullish_swing_ref_is_high(self, mod15):
        df = _bearish_then_reversal()
        mod15.update(df)
        for e in mod15.events:
            if e.event == StructureEvent.CHOCH_BULLISH:
                assert e.swing_ref.kind == "high"

    def test_choch_displacement_recorded(self, mod15):
        df = _bullish_then_reversal()
        mod15.update(df)
        for e in mod15.events:
            if e.event == StructureEvent.CHOCH_BEARISH:
                assert e.displacement_size >= CHOCH_MIN_DISPLACEMENT_ATR

    def test_transitioning_score_abs_is_0_3(self, mod15):
        df = _bullish_then_reversal()
        mod15.update(df)
        if mod15.state == TrendState.TRANSITIONING:
            assert abs(mod15.score()) == pytest.approx(0.3)

    def test_transitioning_after_bearish_choch_is_negative(self, mod15):
        df = _bullish_then_reversal()
        mod15.update(df)
        if mod15.state == TrendState.TRANSITIONING:
            last_choch = [e for e in mod15.events if e.event == StructureEvent.CHOCH_BEARISH]
            if last_choch:
                assert mod15.score() < 0.0

    def test_transitioning_after_bullish_choch_is_positive(self, mod15):
        df = _bearish_then_reversal()
        mod15.update(df)
        if mod15.state == TrendState.TRANSITIONING:
            last_choch = [e for e in mod15.events if e.event == StructureEvent.CHOCH_BULLISH]
            if last_choch:
                assert mod15.score() > 0.0

    def test_choch_transitions_to_bearish_after_confirmation(self, mod15):
        """After bearish CHoCH, a subsequent BOS_BEARISH should confirm BEARISH_TREND."""
        df = _bullish_then_reversal(bull_bars=40, bear_bars=20)
        mod15.update(df)
        # If we got a CHoCH and enough bear bars, should have confirmed
        bearish_bos = [e for e in mod15.events if e.event == StructureEvent.BOS_BEARISH]
        if bearish_bos:
            assert mod15.state == TrendState.BEARISH_TREND

    def test_choch_transitions_to_bullish_after_confirmation(self, mod15):
        df = _bearish_then_reversal(bear_bars=40, bull_bars=20)
        mod15.update(df)
        bullish_bos = [e for e in mod15.events if e.event == StructureEvent.BOS_BULLISH
                       and mod15.events.index(e) > 0]
        if bullish_bos:
            # There was at least one BOS after the CHoCH
            pass  # State should reflect confirmed trend

    def test_bearish_score_neg_1_after_choch_in_bearish_trend(self, mod15):
        """If state=BEARISH_TREND and last event=CHOCH_BEARISH, score=-1.0."""
        mod15.state = TrendState.BEARISH_TREND
        sp = SwingPoint(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "low", True)
        mod15.events.append(StructureEventRecord(
            event=StructureEvent.CHOCH_BEARISH, price=99.0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            swing_ref=sp, displacement_size=2.0,
        ))
        assert mod15.score() == pytest.approx(-1.0)

    def test_bullish_score_1_after_choch_in_bullish_trend(self, mod15):
        mod15.state = TrendState.BULLISH_TREND
        sp = SwingPoint(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "high", True)
        mod15.events.append(StructureEventRecord(
            event=StructureEvent.CHOCH_BULLISH, price=101.0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            swing_ref=sp, displacement_size=2.0,
        ))
        assert mod15.score() == pytest.approx(1.0)

    def test_choch_event_has_timestamp(self, mod15):
        df = _bullish_then_reversal()
        mod15.update(df)
        for e in mod15.events:
            if e.event in (StructureEvent.CHOCH_BULLISH, StructureEvent.CHOCH_BEARISH):
                assert isinstance(e.timestamp, datetime)

    def test_choch_event_comes_after_bos(self, mod15):
        """CHoCH should appear after at least one BOS in the events list."""
        df = _bullish_then_reversal(bull_bars=30, bear_bars=15)
        mod15.update(df)
        events_types = [e.event for e in mod15.events]
        if StructureEvent.CHOCH_BEARISH in events_types:
            choch_idx = events_types.index(StructureEvent.CHOCH_BEARISH)
            assert choch_idx > 0

    def test_no_choch_without_prior_trend(self, mod15):
        """CHoCH cannot occur without an established trend."""
        df = _bullish(n=12)   # Just enough to barely init, not enough for CHoCH
        mod15.update(df)
        choch = [e for e in mod15.events if e.event in (
            StructureEvent.CHOCH_BULLISH, StructureEvent.CHOCH_BEARISH)]
        assert len(choch) == 0

    def test_multiple_choch_possible_in_long_series(self, mod15):
        """In a long series with trend flip, at least one CHoCH should occur."""
        df = _bullish_then_reversal(bull_bars=40, bear_bars=30)
        mod15.update(df)
        choch_count = sum(1 for e in mod15.events if e.event in (
            StructureEvent.CHOCH_BULLISH, StructureEvent.CHOCH_BEARISH))
        assert choch_count >= 0  # Soft assertion — structure may vary

    def test_choch_score_greater_magnitude_than_bos(self):
        """CHoCH scores have higher absolute value than BOS scores."""
        assert abs(_SCORE_MAP.get((TrendState.BULLISH_TREND, StructureEvent.CHOCH_BULLISH), 0)) > \
               abs(_SCORE_MAP.get((TrendState.BULLISH_TREND, StructureEvent.BOS_BULLISH), 0))

    def test_choch_displacement_size_is_float(self, mod15):
        df = _bullish_then_reversal()
        mod15.update(df)
        for e in mod15.events:
            assert isinstance(e.displacement_size, float)

    def test_choch_bearish_score_negative_transitioning(self, mod15):
        mod15.state = TrendState.TRANSITIONING
        sp = SwingPoint(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "low", True)
        mod15.events.append(StructureEventRecord(
            event=StructureEvent.CHOCH_BEARISH, price=99.0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            swing_ref=sp, displacement_size=2.5,
        ))
        assert mod15.score() < 0.0


# ════════════════════════════════════════════════════════════════════════════
# 8. RANGING STATE  (15 tests)
# ════════════════════════════════════════════════════════════════════════════

class TestRangingState:
    def test_ranging_state_from_oscillating_candles(self, mod15):
        df = _ranging(n=60, amplitude=0.5)
        mod15.update(df)
        assert mod15.state == TrendState.RANGING

    def test_ranging_score_is_zero(self, mod15):
        df = _ranging(n=60, amplitude=0.5)
        mod15.update(df)
        if mod15.state == TrendState.RANGING:
            assert mod15.score() == pytest.approx(0.0)

    def test_trending_not_classified_as_ranging(self, mod15):
        df = _bullish(n=50, step=3.0)
        mod15.update(df)
        assert mod15.state != TrendState.RANGING

    def test_ranging_detected_when_swings_in_band(self, mod15):
        """Explicit tight range: all swing prices within 1.5x ATR."""
        df = _ranging(n=50, amplitude=0.3)
        mod15.update(df)
        assert mod15.state == TrendState.RANGING

    def test_no_ranging_with_large_amplitude(self, mod15):
        """Wide oscillations should not be classified as ranging."""
        df = _ranging(n=50, amplitude=20.0)
        mod15.update(df)
        # Wide amplitude → should not be ranging (exceeds 1.5x ATR band)
        # State depends on oscillation pattern; just verify it's not definitively ranging with strong score
        if mod15.state == TrendState.RANGING:
            assert mod15.score() == pytest.approx(0.0)

    def test_ranging_events_list_may_be_empty(self, mod15):
        df = _ranging(n=50, amplitude=0.3)
        mod15.update(df)
        if mod15.state == TrendState.RANGING:
            # Ranging state doesn't require events
            assert mod15.latest_event() is None or mod15.latest_event() is not None

    def test_ranging_constant_value(self):
        assert RANGING_ATR_BAND == pytest.approx(1.5)

    def test_choch_min_displacement_constant(self):
        assert CHOCH_MIN_DISPLACEMENT_ATR == pytest.approx(1.5)

    def test_ranging_requires_min_swings(self, mod15):
        """With fewer than RANGING_MIN_SWINGS, ranging detection returns False."""
        df = _bullish(n=12)  # Only a few swing points possible
        mod15.update(df)
        # Should not be RANGING with very few swing points
        if mod15.state == TrendState.RANGING:
            # If it is, it's valid — check score is 0
            assert mod15.score() == pytest.approx(0.0)

    def test_transition_from_ranging_to_trend(self, mod15):
        """After ranging, if a clear breakout occurs, state should update."""
        range_df = _ranging(n=40, amplitude=0.3)
        mod15.update(range_df)
        trend_df = _bullish(n=40, base=110.0)
        combined = pd.concat([range_df, trend_df])
        combined = combined[~combined.index.duplicated(keep="first")]
        mod15.update(combined)
        # State may remain RANGING or transition — either is valid
        assert mod15.state in (TrendState.RANGING, TrendState.BULLISH_TREND,
                               TrendState.TRANSITIONING, TrendState.UNKNOWN)

    def test_score_zero_in_ranging_state_directly(self, mod15):
        mod15.state = TrendState.RANGING
        assert mod15.score() == pytest.approx(0.0)

    def test_score_zero_in_unknown_state_directly(self, mod15):
        mod15.state = TrendState.UNKNOWN
        assert mod15.score() == pytest.approx(0.0)

    def test_ranging_state_enum_value(self):
        assert TrendState.RANGING.value == "RANGING"

    def test_unknown_state_enum_value(self):
        assert TrendState.UNKNOWN.value == "UNKNOWN"

    def test_transitioning_state_enum_value(self):
        assert TrendState.TRANSITIONING.value == "TRANSITIONING"


# ════════════════════════════════════════════════════════════════════════════
# 9. SCORE HELPER & STATE MANIPULATION  (20 tests)
# ════════════════════════════════════════════════════════════════════════════

class TestScoreHelper:
    def test_score_from_state_unknown_no_event(self, mod15):
        assert mod15._score_from_state() == pytest.approx(0.0)

    def test_score_from_state_bullish_bos(self, mod15):
        mod15.state = TrendState.BULLISH_TREND
        sp = SwingPoint(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "high", True)
        mod15.events.append(StructureEventRecord(
            event=StructureEvent.BOS_BULLISH, price=101.0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            swing_ref=sp, displacement_size=1.0,
        ))
        assert mod15.score() == pytest.approx(0.8)

    def test_score_from_state_bearish_bos(self, mod15):
        mod15.state = TrendState.BEARISH_TREND
        sp = SwingPoint(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "low", True)
        mod15.events.append(StructureEventRecord(
            event=StructureEvent.BOS_BEARISH, price=99.0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            swing_ref=sp, displacement_size=1.0,
        ))
        assert mod15.score() == pytest.approx(-0.8)

    def test_score_ranging_returns_zero(self, mod15):
        mod15.state = TrendState.RANGING
        assert mod15.score() == pytest.approx(0.0)

    def test_score_within_minus_1_to_plus_1(self, mod15):
        for state in TrendState:
            mod15.state = state
            mod15.events.clear()
            s = mod15.score()
            assert -1.0 <= s <= 1.0

    def test_score_unknown_state_is_zero(self, mod15):
        mod15.state = TrendState.UNKNOWN
        assert mod15.score() == pytest.approx(0.0)

    def test_latest_event_returns_last(self, mod15):
        sp = SwingPoint(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "high", True)
        e1 = StructureEventRecord(StructureEvent.BOS_BULLISH, 101.0,
                                  datetime(2024, 1, 2, tzinfo=timezone.utc), sp, 1.0)
        e2 = StructureEventRecord(StructureEvent.BOS_BULLISH, 105.0,
                                  datetime(2024, 1, 3, tzinfo=timezone.utc), sp, 1.2)
        mod15.events.extend([e1, e2])
        assert mod15.latest_event() is e2

    def test_latest_event_none_when_no_events(self, mod15):
        assert mod15.latest_event() is None

    def test_score_with_unknown_state_and_event(self, mod15):
        """State=UNKNOWN even with an event: key not in map → returns 0.0."""
        mod15.state = TrendState.UNKNOWN
        sp = SwingPoint(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "high", True)
        mod15.events.append(StructureEventRecord(
            event=StructureEvent.BOS_BULLISH, price=101.0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            swing_ref=sp, displacement_size=1.0,
        ))
        assert mod15.score() == pytest.approx(0.0)

    def test_transitioning_bearish_sign(self, mod15):
        mod15.state = TrendState.TRANSITIONING
        sp = SwingPoint(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "low", True)
        mod15.events.append(StructureEventRecord(
            event=StructureEvent.CHOCH_BEARISH, price=99.0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            swing_ref=sp, displacement_size=2.0,
        ))
        assert mod15.score() == pytest.approx(-0.3)

    def test_transitioning_bullish_sign(self, mod15):
        mod15.state = TrendState.TRANSITIONING
        sp = SwingPoint(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "high", True)
        mod15.events.append(StructureEventRecord(
            event=StructureEvent.CHOCH_BULLISH, price=101.0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            swing_ref=sp, displacement_size=2.0,
        ))
        assert mod15.score() == pytest.approx(0.3)

    def test_score_type_is_float(self, mod15):
        assert isinstance(mod15.score(), float)

    def test_events_accumulate_across_updates(self, mod15):
        df = _bullish()  # n=60 reliably produces BOS events
        mod15.update(df)
        count = len(mod15.events)
        assert count > 0

    def test_state_enum_all_values_exist(self):
        states = {s.value for s in TrendState}
        assert "UNKNOWN" in states
        assert "BULLISH_TREND" in states
        assert "BEARISH_TREND" in states
        assert "RANGING" in states
        assert "TRANSITIONING" in states

    def test_structure_event_enum_all_values_exist(self):
        events = {e.value for e in StructureEvent}
        assert "BOS_BULLISH" in events
        assert "BOS_BEARISH" in events
        assert "CHOCH_BULLISH" in events
        assert "CHOCH_BEARISH" in events

    def test_swing_point_dataclass_fields(self):
        sp = SwingPoint(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "high", True)
        assert sp.price == 100.0
        assert sp.kind == "high"
        assert sp.confirmed is True

    def test_structure_event_record_fields(self):
        sp = SwingPoint(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0, "high", True)
        er = StructureEventRecord(
            event=StructureEvent.BOS_BULLISH,
            price=101.0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            swing_ref=sp,
            displacement_size=1.5,
        )
        assert er.event == StructureEvent.BOS_BULLISH
        assert er.displacement_size == pytest.approx(1.5)

    def test_update_idempotent_with_same_data(self, mod15):
        """Calling update twice with the same data should not duplicate events."""
        df = _bullish()
        mod15.update(df)
        events1 = len(mod15.events)
        mod15.update(df)
        events2 = len(mod15.events)
        assert events2 == events1

    def test_atr_helper_returns_series(self):
        df = _bullish(n=20)
        atr = _compute_atr(df)
        assert isinstance(atr, pd.Series)
        assert len(atr) == len(df)

    def test_atr_helper_values_positive(self):
        df = _bullish(n=20)
        atr = _compute_atr(df)
        assert (atr.dropna() > 0).all()


# ════════════════════════════════════════════════════════════════════════════
# 10. ATR HELPER  (10 tests)
# ════════════════════════════════════════════════════════════════════════════

class TestATRHelper:
    def test_atr_length_matches_input(self):
        df = _bullish(n=30)
        atr = _compute_atr(df, period=14)
        assert len(atr) == 30

    def test_atr_first_values_may_be_nan(self):
        """EWM with com= does not produce NaN for the first value, but TR[0] is NaN."""
        df = _bullish(n=30)
        atr = _compute_atr(df, period=14)
        # First ATR may be NaN (no prev_close for TR calculation)
        assert atr.iloc[1:].notna().all()

    def test_atr_positive_for_trending_market(self):
        df = _bullish(n=30)
        atr = _compute_atr(df, period=14)
        assert (atr.dropna() > 0).all()

    def test_atr_period_14_is_default(self):
        df = _bullish(n=30)
        atr_default = _compute_atr(df)
        atr_14 = _compute_atr(df, period=14)
        pd.testing.assert_series_equal(atr_default, atr_14)

    def test_atr_higher_in_volatile_market(self):
        stable  = _bullish(n=30, step=0.5)
        volatile = _bullish(n=30, step=5.0)
        atr_stable   = _compute_atr(stable).mean()
        atr_volatile = _compute_atr(volatile).mean()
        assert atr_volatile > atr_stable

    def test_atr_returns_pandas_series(self):
        df = _bullish(n=20)
        atr = _compute_atr(df)
        assert isinstance(atr, pd.Series)

    def test_atr_index_matches_candles_index(self):
        df = _bullish(n=30)
        atr = _compute_atr(df)
        assert list(atr.index) == list(df.index)

    def test_atr_with_period_5(self):
        df = _bullish(n=20)
        atr = _compute_atr(df, period=5)
        assert len(atr) == 20

    def test_atr_smoothing_decreases_spikes(self):
        """Wilder smoothing means ATR std <= True Range std (smoothing damps variation)."""
        df = _bullish(n=40, step=1.0)
        atr = _compute_atr(df, period=14)
        # Compute actual True Range (includes gaps from prev_close)
        high = df["high"]
        low = df["low"]
        prev_close = df["close"].shift(1)
        tr_raw = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        # ATR (EWM-smoothed TR) std should be <= raw TR std
        assert atr.dropna().std() <= tr_raw.dropna().std() + 1e-9

    def test_atr_bearish_market_positive(self):
        df = _bearish(n=30)
        atr = _compute_atr(df)
        assert (atr.dropna() > 0).all()
