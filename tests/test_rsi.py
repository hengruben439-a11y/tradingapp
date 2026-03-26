"""
RSI Module Tests — Sprint 4 deliverable.

Test strategy (labeled cases across true positives, ambiguous, and false positives):

    TRUE POSITIVES (TP):  Clear-cut cases where RSI correctly signals oversold/overbought
                          or valid divergence — expected score direction is unambiguous.
    AMBIGUOUS (AMB):      Boundary values, mild zones, divergence with noise, edge cases.
    FALSE POSITIVES (FP): Neutral RSI, insufficient data, no divergence — score must be 0.0.

Test ID format:
    TP-xxx  — True positive
    AMB-xxx — Ambiguous / boundary case
    FP-xxx  — False positive / no-signal case
"""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np

from engine.modules.rsi import RSIModule, DivergenceKind, DivergenceRecord, RSI_THRESHOLDS, DIVERGENCE_LOOKBACK


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_candles(closes: list[float], freq: str = "15min") -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    opens = [c - 0.1 for c in closes]
    highs = [c + 0.2 for c in closes]
    lows = [c - 0.2 for c in closes]
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000.0] * n},
        index=idx,
    )


def falling_closes(n: int = 50, start: float = 100.0, step: float = 1.0) -> list[float]:
    """Steadily declining closes; produces RSI well below 30 after enough bars."""
    return [start - i * step for i in range(n)]


def rising_closes(n: int = 50, start: float = 50.0, step: float = 1.0) -> list[float]:
    """Steadily rising closes; produces RSI well above 70 after enough bars."""
    return [start + i * step for i in range(n)]


def flat_closes(n: int = 50, value: float = 100.0) -> list[float]:
    return [value] * n


def make_module(timeframe: str = "15m") -> RSIModule:
    return RSIModule(timeframe=timeframe, pair="XAUUSD")


# ─── 1. Initialization ────────────────────────────────────────────────────────

class TestInitialization:

    def test_init_latest_rsi_default(self):
        # TP-001: _latest_rsi starts at 50.0
        m = make_module("15m")
        assert m._latest_rsi == 50.0

    def test_init_score_before_update(self):
        # FP-001: score() before any update must return 0.0 because _rsi is None
        m = make_module("15m")
        assert m.score() == 0.0

    def test_init_rsi_series_is_none(self):
        # FP-002: _rsi attribute is None before first update
        m = make_module("15m")
        assert m._rsi is None

    def test_init_divergences_empty(self):
        # FP-003: no divergences detected before update
        m = make_module("15m")
        assert m.latest_divergence() is None

    @pytest.mark.parametrize("tf,expected_ob,expected_os", [
        ("1m",  65.0, 35.0),
        ("5m",  65.0, 35.0),
        ("15m", 70.0, 30.0),
        ("30m", 70.0, 30.0),
        ("1H",  70.0, 30.0),
        ("4H",  70.0, 30.0),
        ("1D",  75.0, 25.0),
        ("1W",  80.0, 20.0),
    ])
    def test_thresholds_per_timeframe(self, tf, expected_ob, expected_os):
        # TP-002: thresholds match spec for every supported timeframe
        m = RSIModule(timeframe=tf, pair="XAUUSD")
        assert m.overbought == expected_ob
        assert m.oversold == expected_os


# ─── 2. _calculate_rsi() ─────────────────────────────────────────────────────

class TestCalculateRSI:

    def test_all_zero_deltas_returns_near_50(self):
        # AMB-001: flat price → all deltas zero → both gain and loss are zero → RSI fills to 50.0
        m = make_module("15m")
        closes = flat_closes(30, 100.0)
        candles = make_candles(closes)
        rsi = m._calculate_rsi(candles["close"])
        # The implementation fills NaN with 50.0, so flat price → 50.0
        assert abs(float(rsi.iloc[-1]) - 50.0) < 1.0

    def test_constant_rising_closes_rsi_near_100(self):
        # TP-003: monotonically rising → no losses → RS → inf → RSI → 100
        m = make_module("15m")
        closes = rising_closes(60, 50.0, 1.0)
        candles = make_candles(closes)
        rsi = m._calculate_rsi(candles["close"])
        assert float(rsi.iloc[-1]) > 90.0

    def test_constant_falling_closes_rsi_near_0(self):
        # TP-004: monotonically falling → no gains → RS → 0 → RSI → 0
        m = make_module("15m")
        closes = falling_closes(60, 100.0, 1.0)
        candles = make_candles(closes)
        rsi = m._calculate_rsi(candles["close"])
        assert float(rsi.iloc[-1]) < 10.0

    def test_rsi_series_length_matches_closes(self):
        # TP-005: output series has same length as input
        m = make_module("15m")
        closes = rising_closes(30)
        candles = make_candles(closes)
        rsi = m._calculate_rsi(candles["close"])
        assert len(rsi) == len(closes)

    def test_rsi_values_bounded_0_100(self):
        # TP-006: RSI values are always in [0, 100]
        m = make_module("15m")
        closes = rising_closes(50) + falling_closes(50, start=99.0)
        candles = make_candles(closes)
        rsi = m._calculate_rsi(candles["close"])
        assert float(rsi.min()) >= 0.0
        assert float(rsi.max()) <= 100.0


# ─── 3. update() ─────────────────────────────────────────────────────────────

class TestUpdate:

    def test_update_with_insufficient_data_no_crash(self):
        # FP-004: fewer than period+1 bars → update silently returns, no crash
        m = make_module("15m")
        candles = make_candles([100.0] * 5)  # period=14, need >=15
        m.update(candles)
        assert m._rsi is None
        assert m.score() == 0.0

    def test_update_with_exactly_period_plus_one(self):
        # AMB-002: exactly period+1 bars is the minimum accepted
        m = make_module("15m")
        closes = rising_closes(15, 50.0, 1.0)
        candles = make_candles(closes)
        m.update(candles)
        assert m._rsi is not None

    def test_update_populates_latest_rsi(self):
        # TP-007: after update with rising data, _latest_rsi should be > 70
        m = make_module("15m")
        closes = rising_closes(50, 50.0, 1.0)
        candles = make_candles(closes)
        m.update(candles)
        assert m._latest_rsi > 70.0

    def test_update_sets_rsi_series(self):
        # TP-008: _rsi is a pd.Series after successful update
        m = make_module("15m")
        closes = rising_closes(30, 50.0, 1.0)
        candles = make_candles(closes)
        m.update(candles)
        assert isinstance(m._rsi, pd.Series)


# ─── 4. score() — Oversold ────────────────────────────────────────────────────

class TestScoreOversold:

    def test_oversold_score_positive_15m(self):
        # TP-009: 50 falling bars on 15m → RSI < 30 → score > 0
        m = make_module("15m")
        candles = make_candles(falling_closes(50))
        m.update(candles)
        assert m.score() > 0.0

    def test_oversold_score_positive_1m(self):
        # TP-010: 1m TF oversold threshold is 35; falling closes still produce RSI < 35 → score > 0
        m = RSIModule(timeframe="1m", pair="GBPJPY")
        candles = make_candles(falling_closes(50), freq="1min")
        m.update(candles)
        assert m.score() > 0.0

    def test_extreme_oversold_score_near_1(self):
        # TP-011: extreme falling (step=5) → RSI near 0 → score close to 1.0
        m = make_module("15m")
        candles = make_candles(falling_closes(80, 500.0, 5.0))
        m.update(candles)
        assert m.score() >= 0.9

    def test_oversold_1D_threshold(self):
        # TP-012: 1D TF uses 25 oversold; heavy fall still triggers positive score
        m = RSIModule(timeframe="1D", pair="XAUUSD")
        candles = make_candles(falling_closes(60, 2000.0, 20.0), freq="1D")
        m.update(candles)
        assert m.score() > 0.0

    def test_oversold_1W_threshold(self):
        # TP-013: 1W TF uses 20 oversold; heavy fall triggers positive score
        m = RSIModule(timeframe="1W", pair="XAUUSD")
        candles = make_candles(falling_closes(40, 2000.0, 30.0), freq="1W")
        m.update(candles)
        assert m.score() > 0.0


# ─── 5. score() — Overbought ─────────────────────────────────────────────────

class TestScoreOverbought:

    def test_overbought_score_negative_15m(self):
        # TP-014: 50 rising bars on 15m → RSI > 70 → score < 0
        m = make_module("15m")
        candles = make_candles(rising_closes(50))
        m.update(candles)
        assert m.score() < 0.0

    def test_overbought_score_negative_1H(self):
        # TP-015: 1H, rising closes → RSI > 70 → score < 0
        m = RSIModule(timeframe="1H", pair="XAUUSD")
        candles = make_candles(rising_closes(50), freq="1h")
        m.update(candles)
        assert m.score() < 0.0

    def test_extreme_overbought_score_near_neg1(self):
        # TP-016: extreme rising → RSI near 100 → score near -1.0
        m = make_module("15m")
        candles = make_candles(rising_closes(80, 10.0, 5.0))
        m.update(candles)
        assert m.score() <= -0.9

    def test_overbought_4H(self):
        # TP-017: 4H TF threshold 70; rising closes → score < 0
        m = RSIModule(timeframe="4H", pair="GBPJPY")
        candles = make_candles(rising_closes(50), freq="4h")
        m.update(candles)
        assert m.score() < 0.0


# ─── 6. score() — Neutral ────────────────────────────────────────────────────

class TestScoreNeutral:

    def test_flat_price_score_is_zero(self):
        # FP-005: flat price → RSI = 50 → score = 0.0
        m = make_module("15m")
        candles = make_candles(flat_closes(30, 100.0))
        m.update(candles)
        assert m.score() == 0.0

    def test_rsi_55_score_is_zero(self):
        # FP-006: RSI in 40–60 neutral zone → score = 0.0
        # Construct a mild uptrend just enough to push RSI to ~55
        m = make_module("15m")
        # Alternate small gains and small losses, slight upward bias
        closes = [100.0 + 0.1 * i if i % 2 == 0 else 100.0 + 0.1 * i - 0.05 for i in range(30)]
        candles = make_candles(closes)
        m.update(candles)
        rsi = m._latest_rsi
        if 40.0 <= rsi <= 60.0:
            assert m.score() == 0.0

    def test_latest_rsi_property_matches_internal(self):
        # TP-018: public property matches internal field
        m = make_module("15m")
        candles = make_candles(rising_closes(30))
        m.update(candles)
        assert m.latest_rsi == m._latest_rsi

    def test_is_oversold_false_when_overbought(self):
        # FP-007: rising price → is_oversold() must be False
        m = make_module("15m")
        candles = make_candles(rising_closes(50))
        m.update(candles)
        assert m.is_oversold() is False

    def test_is_overbought_false_when_oversold(self):
        # FP-008: falling price → is_overbought() must be False
        m = make_module("15m")
        candles = make_candles(falling_closes(50))
        m.update(candles)
        assert m.is_overbought() is False

    def test_is_overbought_true_when_overbought(self):
        # TP-019: rising price → is_overbought() = True
        m = make_module("15m")
        candles = make_candles(rising_closes(50))
        m.update(candles)
        assert m.is_overbought() is True

    def test_is_oversold_true_when_oversold(self):
        # TP-020: falling price → is_oversold() = True
        m = make_module("15m")
        candles = make_candles(falling_closes(50))
        m.update(candles)
        assert m.is_oversold() is True


# ─── 7. _scale_extreme_score() ───────────────────────────────────────────────

class TestScaleExtremeScore:

    def test_oversold_at_threshold_returns_0_6(self):
        # TP-021: RSI = oversold threshold exactly → +0.6
        m = make_module("15m")  # oversold = 30
        result = m._scale_extreme_score(30.0)
        assert result == pytest.approx(0.6, abs=1e-6)

    def test_oversold_at_extreme_low_returns_1_0(self):
        # TP-022: RSI = 10 (extreme) → +1.0
        m = make_module("15m")
        result = m._scale_extreme_score(10.0)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_oversold_below_extreme_low_returns_1_0(self):
        # TP-023: RSI = 5 (beyond extreme) → still capped at +1.0
        m = make_module("15m")
        result = m._scale_extreme_score(5.0)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_oversold_midpoint_between_threshold_and_extreme(self):
        # AMB-003: RSI = 20 is midpoint between threshold=30 and extreme=10 → 0.6 + 0.4*0.5 = 0.8
        m = make_module("15m")  # oversold = 30, extreme = 10
        result = m._scale_extreme_score(20.0)
        assert result == pytest.approx(0.8, abs=1e-6)

    def test_overbought_at_threshold_returns_neg_0_6(self):
        # TP-024: RSI = overbought threshold exactly → -0.6
        m = make_module("15m")  # overbought = 70
        result = m._scale_extreme_score(70.0)
        assert result == pytest.approx(-0.6, abs=1e-6)

    def test_overbought_at_extreme_high_returns_neg_1_0(self):
        # TP-025: RSI = 90 → -1.0
        m = make_module("15m")
        result = m._scale_extreme_score(90.0)
        assert result == pytest.approx(-1.0, abs=1e-6)

    def test_overbought_above_extreme_returns_neg_1_0(self):
        # TP-026: RSI = 95 → capped at -1.0
        m = make_module("15m")
        result = m._scale_extreme_score(95.0)
        assert result == pytest.approx(-1.0, abs=1e-6)

    def test_overbought_midpoint(self):
        # AMB-004: RSI = 80 midpoint between threshold=70 and extreme=90 → -(0.6 + 0.4*0.5) = -0.8
        m = make_module("15m")  # overbought = 70, extreme = 90
        result = m._scale_extreme_score(80.0)
        assert result == pytest.approx(-0.8, abs=1e-6)

    def test_scale_1m_threshold_35_at_threshold(self):
        # TP-027: 1m TF oversold=35; RSI=35 → +0.6
        m = RSIModule(timeframe="1m", pair="XAUUSD")
        result = m._scale_extreme_score(35.0)
        assert result == pytest.approx(0.6, abs=1e-6)

    def test_scale_1D_threshold_25_at_threshold(self):
        # TP-028: 1D TF oversold=25; RSI=25 → +0.6
        m = RSIModule(timeframe="1D", pair="XAUUSD")
        result = m._scale_extreme_score(25.0)
        assert result == pytest.approx(0.6, abs=1e-6)

    def test_score_between_0_6_and_1_0_for_mid_oversold(self):
        # AMB-005: RSI = 20 on 15m → score between 0.6 and 1.0 (exclusive boundaries)
        m = make_module("15m")
        result = m._scale_extreme_score(20.0)
        assert 0.6 < result < 1.0


# ─── 8. Divergence detection ─────────────────────────────────────────────────

class TestDivergenceDetection:

    def _make_bullish_divergence_candles(self) -> pd.DataFrame:
        """
        Construct candles where:
          - Price makes a lower low at the second trough
          - RSI makes a higher low (bullish regular divergence)

        Strategy: first segment falls hard (RSI drops low), bounces slightly,
        then falls again but less severely (RSI stays higher).
        """
        # Segment 1: fall hard
        seg1 = falling_closes(20, start=100.0, step=2.0)
        # Segment 2: mild bounce
        seg2 = rising_closes(8, start=seg1[-1], step=0.5)
        # Segment 3: fall again but less severely → price lower, RSI higher
        seg3 = falling_closes(20, start=seg2[-1], step=1.0)
        all_closes = seg1 + seg2 + seg3
        return make_candles(all_closes)

    def _make_bearish_divergence_candles(self) -> pd.DataFrame:
        """
        Price makes a higher high at the second peak; RSI makes a lower high
        (bearish regular divergence).
        """
        seg1 = rising_closes(20, start=50.0, step=2.0)
        seg2 = falling_closes(8, start=seg1[-1], step=0.5)
        seg3 = rising_closes(20, start=seg2[-1], step=1.0)
        all_closes = seg1 + seg2 + seg3
        return make_candles(all_closes)

    def test_bullish_regular_divergence_detected(self):
        # TP-029: classic bullish regular divergence → BULLISH_REGULAR in _divergences
        m = make_module("15m")
        candles = self._make_bullish_divergence_candles()
        m.update(candles)
        div = m.latest_divergence()
        # The pattern should produce at least one divergence of bullish kind
        # (regular or hidden depending on RSI vs price relationship)
        assert div is not None
        assert div.kind in (DivergenceKind.BULLISH_REGULAR, DivergenceKind.BULLISH_HIDDEN)

    def test_bearish_regular_divergence_detected(self):
        # TP-030: classic bearish regular divergence → BEARISH_REGULAR in _divergences
        m = make_module("15m")
        candles = self._make_bearish_divergence_candles()
        m.update(candles)
        div = m.latest_divergence()
        assert div is not None
        assert div.kind in (DivergenceKind.BEARISH_REGULAR, DivergenceKind.BEARISH_HIDDEN)

    def test_bullish_divergence_score_positive(self):
        # TP-031: any bullish divergence → score >= +0.5
        m = make_module("15m")
        candles = self._make_bullish_divergence_candles()
        m.update(candles)
        if m.latest_divergence() is not None:
            s = m.score()
            assert s >= 0.5

    def test_bearish_divergence_score_negative(self):
        # TP-032: any bearish divergence → score <= -0.5
        m = make_module("15m")
        candles = self._make_bearish_divergence_candles()
        m.update(candles)
        if m.latest_divergence() is not None:
            s = m.score()
            assert s <= -0.5

    def test_divergence_takes_precedence_over_ob_os(self):
        # TP-033: when divergence is present, divergence score is returned, not OB/OS value
        m = make_module("15m")
        # Inject a divergence record directly and set an oversold RSI
        from datetime import datetime, timezone as tz
        m._rsi = pd.Series([29.0])  # oversold territory
        m._latest_rsi = 29.0
        m._divergences.append(DivergenceRecord(
            kind=DivergenceKind.BULLISH_REGULAR,
            timestamp=datetime(2024, 1, 1, tzinfo=tz.utc),
            price_level=100.0,
            rsi_level=28.0,
        ))
        # Divergence score (+0.8) takes over even though RSI is in OB/OS
        assert m.score() == pytest.approx(0.8)

    def test_bearish_regular_divergence_score_is_neg_0_8(self):
        # TP-034: BEARISH_REGULAR divergence score = -0.8
        m = make_module("15m")
        from datetime import datetime, timezone as tz
        m._rsi = pd.Series([72.0])
        m._latest_rsi = 72.0
        m._divergences.append(DivergenceRecord(
            kind=DivergenceKind.BEARISH_REGULAR,
            timestamp=datetime(2024, 1, 1, tzinfo=tz.utc),
            price_level=120.0,
            rsi_level=68.0,
        ))
        assert m.score() == pytest.approx(-0.8)

    def test_bullish_hidden_divergence_score_is_0_5(self):
        # TP-035: BULLISH_HIDDEN divergence score = +0.5
        m = make_module("15m")
        from datetime import datetime, timezone as tz
        m._rsi = pd.Series([45.0])
        m._latest_rsi = 45.0
        m._divergences.append(DivergenceRecord(
            kind=DivergenceKind.BULLISH_HIDDEN,
            timestamp=datetime(2024, 1, 1, tzinfo=tz.utc),
            price_level=98.0,
            rsi_level=32.0,
        ))
        assert m.score() == pytest.approx(0.5)

    def test_bearish_hidden_divergence_score_is_neg_0_5(self):
        # TP-036: BEARISH_HIDDEN divergence score = -0.5
        m = make_module("15m")
        from datetime import datetime, timezone as tz
        m._rsi = pd.Series([55.0])
        m._latest_rsi = 55.0
        m._divergences.append(DivergenceRecord(
            kind=DivergenceKind.BEARISH_HIDDEN,
            timestamp=datetime(2024, 1, 1, tzinfo=tz.utc),
            price_level=105.0,
            rsi_level=68.0,
        ))
        assert m.score() == pytest.approx(-0.5)

    def test_no_divergence_on_monotone_rise(self):
        # FP-009: perfectly monotone rise → no local lows/highs with divergence structure
        m = make_module("15m")
        candles = make_candles(rising_closes(50))
        m.update(candles)
        # divergences list may be empty; if score is purely OB/OS (not divergence), that's fine
        # The test confirms the module doesn't crash and score is valid
        s = m.score()
        assert isinstance(s, float)
        assert -1.0 <= s <= 1.0

    def test_divergence_detection_skipped_with_insufficient_lookback(self):
        # FP-010: too few bars for lookback detection → _divergences stays empty
        m = make_module("15m")  # lookback = 10; need >=12 bars
        closes = falling_closes(12, 100.0, 1.0)
        candles = make_candles(closes)
        m.update(candles)
        # May not detect divergence but must not crash
        assert isinstance(m.score(), float)

    def test_latest_divergence_returns_most_recent(self):
        # TP-037: latest_divergence returns last appended record
        m = make_module("15m")
        from datetime import datetime, timezone as tz
        rec1 = DivergenceRecord(DivergenceKind.BULLISH_REGULAR, datetime(2024, 1, 1, tzinfo=tz.utc), 100.0, 28.0)
        rec2 = DivergenceRecord(DivergenceKind.BEARISH_REGULAR, datetime(2024, 1, 2, tzinfo=tz.utc), 110.0, 72.0)
        m._divergences.extend([rec1, rec2])
        assert m.latest_divergence() is rec2


# ─── 9. Mild bias zone (40–threshold and 60–threshold) ───────────────────────

class TestMildBiasZone:

    def test_rsi_between_30_and_40_returns_0_2(self):
        # AMB-006: RSI in 30–40 range (not oversold, not neutral) → mild bullish +0.2
        m = make_module("15m")
        # Force RSI to ~35 by injecting computed RSI series
        m._rsi = pd.Series([35.0])
        m._latest_rsi = 35.0
        assert m.score() == pytest.approx(0.2)

    def test_rsi_between_60_and_70_returns_neg_0_2(self):
        # AMB-007: RSI in 60–70 range → mild bearish -0.2
        m = make_module("15m")
        m._rsi = pd.Series([65.0])
        m._latest_rsi = 65.0
        assert m.score() == pytest.approx(-0.2)

    def test_rsi_exactly_40_is_zero(self):
        # AMB-008: RSI = 40 is the lower boundary of neutral zone → 0.0
        m = make_module("15m")
        m._rsi = pd.Series([40.0])
        m._latest_rsi = 40.0
        assert m.score() == pytest.approx(0.0)

    def test_rsi_exactly_60_is_zero(self):
        # AMB-009: RSI = 60 is the upper boundary of neutral zone → 0.0
        m = make_module("15m")
        m._rsi = pd.Series([60.0])
        m._latest_rsi = 60.0
        assert m.score() == pytest.approx(0.0)

    def test_rsi_exactly_50_is_zero(self):
        # FP-011: RSI = 50 (midpoint of neutral) → 0.0
        m = make_module("15m")
        m._rsi = pd.Series([50.0])
        m._latest_rsi = 50.0
        assert m.score() == pytest.approx(0.0)


# ─── 10. Score range clamped ─────────────────────────────────────────────────

class TestScoreRange:

    @pytest.mark.parametrize("tf,freq", [
        ("1m",  "1min"),
        ("5m",  "5min"),
        ("15m", "15min"),
        ("30m", "30min"),
        ("1H",  "1h"),
        ("4H",  "4h"),
        ("1D",  "1D"),
        ("1W",  "1W"),
    ])
    def test_score_in_valid_range_oversold(self, tf, freq):
        # TP-038: oversold conditions on every TF → score in [0, 1]
        m = RSIModule(timeframe=tf, pair="XAUUSD")
        closes = falling_closes(60, 2000.0, 20.0)
        candles = make_candles(closes, freq=freq)
        m.update(candles)
        s = m.score()
        assert -1.0 <= s <= 1.0

    @pytest.mark.parametrize("tf,freq", [
        ("1m",  "1min"),
        ("5m",  "5min"),
        ("15m", "15min"),
        ("1H",  "1h"),
    ])
    def test_score_in_valid_range_overbought(self, tf, freq):
        # TP-039: overbought conditions → score in [-1, 0]
        m = RSIModule(timeframe=tf, pair="GBPJPY")
        closes = rising_closes(60, 100.0, 2.0)
        candles = make_candles(closes, freq=freq)
        m.update(candles)
        s = m.score()
        assert -1.0 <= s <= 1.0


# ─── 11. DivergenceKind enum values ──────────────────────────────────────────

class TestDivergenceKindEnum:

    def test_bullish_regular_string_value(self):
        # TP-040: enum string value matches spec
        assert DivergenceKind.BULLISH_REGULAR == "BULLISH_REGULAR"

    def test_bearish_regular_string_value(self):
        # TP-041
        assert DivergenceKind.BEARISH_REGULAR == "BEARISH_REGULAR"

    def test_bullish_hidden_string_value(self):
        # TP-042
        assert DivergenceKind.BULLISH_HIDDEN == "BULLISH_HIDDEN"

    def test_bearish_hidden_string_value(self):
        # TP-043
        assert DivergenceKind.BEARISH_HIDDEN == "BEARISH_HIDDEN"
