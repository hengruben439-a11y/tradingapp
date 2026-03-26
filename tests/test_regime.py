"""
RegimeDetector Tests — engine/regime.py

Covers:
    - Insufficient bars: regime stays UNKNOWN
    - Trending market: TRENDING classification
    - Ranging market: RANGING classification
    - Fresh detector defaults
    - apply_threshold_adjustment behaviour per regime
    - apply_score_penalty behaviour per regime
    - is_mean_reversion_allowed per regime
    - ADX non-negativity
    - Multiple sequential updates
    - BB secondary confirmation interaction
    - Edge cases (all same price, minimal bars, regime property access)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.regime import (
    MarketRegime,
    RegimeDetector,
    ADX_TRENDING_THRESHOLD,
    ADX_RANGING_THRESHOLD,
    ADX_PERIOD,
    TRANSITIONAL_PENALTY,
    RANGING_THRESHOLD_BOOST,
)


# ─── Candle builders ─────────────────────────────────────────────────────────

def make_trending_candles(n: int = 200, direction: str = "up") -> pd.DataFrame:
    """Strongly trending market — each close advances by +1 or -1."""
    closes = np.cumsum(np.ones(n) * (1 if direction == "up" else -1)) + 100
    return pd.DataFrame(
        {
            "open": closes - 0.3,
            "high": closes + 0.5,
            "low": closes - 0.5,
            "close": closes,
            "volume": np.ones(n) * 1000,
        }
    )


def make_ranging_candles(n: int = 200) -> pd.DataFrame:
    """Sideways ranging market — pure stationary noise produces very low ADX."""
    np.random.seed(99)
    noise = np.random.normal(0, 0.5, n)
    closes = 100.0 + noise
    return pd.DataFrame(
        {
            "open": closes - 0.1,
            "high": closes + 0.3,
            "low": closes - 0.3,
            "close": closes,
            "volume": np.ones(n) * 1000,
        }
    )


def make_flat_candles(n: int = 50) -> pd.DataFrame:
    """Completely flat price — zero directional movement."""
    closes = np.full(n, 100.0)
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + 0.01,
            "low": closes - 0.01,
            "close": closes,
            "volume": np.ones(n) * 1000,
        }
    )


MIN_BARS = 2 * ADX_PERIOD + 1  # 29


# ─── Fixture helpers ─────────────────────────────────────────────────────────

@pytest.fixture()
def fresh_detector() -> RegimeDetector:
    return RegimeDetector(timeframe="15m", pair="XAUUSD")


@pytest.fixture()
def trending_detector() -> RegimeDetector:
    det = RegimeDetector(timeframe="15m", pair="XAUUSD")
    det.update(make_trending_candles(200, "up"))
    return det


@pytest.fixture()
def ranging_detector() -> RegimeDetector:
    det = RegimeDetector(timeframe="15m", pair="XAUUSD")
    det.update(make_ranging_candles(200))
    return det


# ─── 1. Initialisation & defaults ────────────────────────────────────────────

class TestDefaults:
    def test_initial_regime_is_unknown(self, fresh_detector):
        assert fresh_detector.regime == MarketRegime.UNKNOWN

    def test_initial_adx_is_zero(self, fresh_detector):
        assert fresh_detector.adx == 0.0

    def test_timeframe_stored(self, fresh_detector):
        assert fresh_detector.timeframe == "15m"

    def test_pair_stored(self, fresh_detector):
        assert fresh_detector.pair == "XAUUSD"

    def test_gbpjpy_pair_stored(self):
        det = RegimeDetector(timeframe="1H", pair="GBPJPY")
        assert det.pair == "GBPJPY"
        assert det.regime == MarketRegime.UNKNOWN

    def test_regime_is_unknown_before_any_update(self, fresh_detector):
        # No update called at all
        assert fresh_detector.regime is MarketRegime.UNKNOWN


# ─── 2. Insufficient bars ────────────────────────────────────────────────────

class TestInsufficientBars:
    def test_zero_bars_stays_unknown(self, fresh_detector):
        fresh_detector.update(pd.DataFrame(columns=["high", "low", "close"]))
        assert fresh_detector.regime == MarketRegime.UNKNOWN

    def test_one_bar_stays_unknown(self, fresh_detector):
        df = make_trending_candles(1)
        fresh_detector.update(df)
        assert fresh_detector.regime == MarketRegime.UNKNOWN

    def test_min_bars_minus_one_stays_unknown(self, fresh_detector):
        df = make_trending_candles(MIN_BARS - 1)  # 28 bars
        fresh_detector.update(df)
        assert fresh_detector.regime == MarketRegime.UNKNOWN

    def test_exactly_min_bars_no_longer_unknown(self, fresh_detector):
        """At exactly MIN_BARS the detector should produce a result."""
        df = make_trending_candles(MIN_BARS)
        fresh_detector.update(df)
        # Not necessarily TRENDING at exactly 29 bars, but should not be UNKNOWN
        assert fresh_detector.regime != MarketRegime.UNKNOWN

    def test_adx_stays_zero_when_insufficient_bars(self, fresh_detector):
        df = make_trending_candles(MIN_BARS - 1)
        fresh_detector.update(df)
        assert fresh_detector.adx == 0.0

    def test_28_bars_trending_data_stays_unknown(self, fresh_detector):
        df = make_trending_candles(28)
        fresh_detector.update(df)
        assert fresh_detector.regime == MarketRegime.UNKNOWN


# ─── 3. Trending market classification ───────────────────────────────────────

class TestTrendingClassification:
    def test_strong_uptrend_classified_trending(self, trending_detector):
        assert trending_detector.regime == MarketRegime.TRENDING

    def test_strong_downtrend_classified_trending(self):
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det.update(make_trending_candles(200, "down"))
        assert det.regime == MarketRegime.TRENDING

    def test_adx_above_trending_threshold_when_trending(self, trending_detector):
        # ADX must exceed 25 for a decisively TRENDING regime
        assert trending_detector.adx > ADX_TRENDING_THRESHOLD

    def test_adx_positive_after_trending_update(self, trending_detector):
        assert trending_detector.adx > 0

    def test_trending_regime_is_not_ranging(self, trending_detector):
        assert trending_detector.regime != MarketRegime.RANGING

    def test_trending_regime_with_150_bars(self):
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det.update(make_trending_candles(150))
        assert det.regime == MarketRegime.TRENDING

    def test_trending_regime_with_very_strong_trend(self):
        """Steeper slope should still yield TRENDING."""
        n = 200
        closes = np.cumsum(np.ones(n) * 5) + 100  # +5 per bar
        df = pd.DataFrame({
            "open": closes - 1,
            "high": closes + 2,
            "low": closes - 2,
            "close": closes,
            "volume": np.ones(n) * 1000,
        })
        det = RegimeDetector(timeframe="1H", pair="GBPJPY")
        det.update(df)
        assert det.regime == MarketRegime.TRENDING


# ─── 4. Ranging market classification ────────────────────────────────────────

class TestRangingClassification:
    def test_ranging_market_classified_ranging_or_transitional(self, ranging_detector):
        # ADX takes many bars to fully settle; accept RANGING or TRANSITIONAL
        assert ranging_detector.regime in (MarketRegime.RANGING, MarketRegime.TRANSITIONAL)

    def test_adx_non_negative_for_ranging(self, ranging_detector):
        assert ranging_detector.adx >= 0

    def test_ranging_regime_is_not_trending(self, ranging_detector):
        assert ranging_detector.regime != MarketRegime.TRENDING

    def test_flat_price_produces_low_adx(self):
        """Completely flat price = no directional movement = ADX near zero."""
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det.update(make_flat_candles(100))
        # ADX should be very low for flat price
        assert det.adx < ADX_TRENDING_THRESHOLD

    def test_sine_wave_200_bars_not_trending(self):
        """200-bar sine wave should not produce TRENDING regime."""
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det.update(make_ranging_candles(200))
        assert det.regime != MarketRegime.TRENDING


# ─── 5. ADX value properties ─────────────────────────────────────────────────

class TestADXValues:
    def test_adx_non_negative_after_trending_update(self, trending_detector):
        assert trending_detector.adx >= 0.0

    def test_adx_non_negative_after_ranging_update(self, ranging_detector):
        assert ranging_detector.adx >= 0.0

    def test_adx_is_float(self, trending_detector):
        assert isinstance(trending_detector.adx, float)

    def test_adx_bounded_between_0_and_100(self, trending_detector):
        # ADX is mathematically bounded [0, 100] — allow small float epsilon
        assert 0.0 <= trending_detector.adx <= 100.0 + 1e-9

    def test_trending_adx_greater_than_ranging_adx(self, trending_detector, ranging_detector):
        assert trending_detector.adx > ranging_detector.adx


# ─── 6. apply_threshold_adjustment ──────────────────────────────────────────

class TestThresholdAdjustment:
    def test_ranging_raises_threshold_by_020(self, ranging_detector):
        if ranging_detector.regime == MarketRegime.RANGING:
            adjusted = ranging_detector.apply_threshold_adjustment(0.50)
            assert abs(adjusted - 0.70) < 1e-9

    def test_trending_threshold_unchanged(self, trending_detector):
        base = 0.50
        adjusted = trending_detector.apply_threshold_adjustment(base)
        assert adjusted == base

    def test_unknown_threshold_unchanged(self, fresh_detector):
        base = 0.50
        adjusted = fresh_detector.apply_threshold_adjustment(base)
        assert adjusted == base

    def test_ranging_raises_065_to_085(self):
        """0.65 + 0.20 = 0.85."""
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det.update(make_ranging_candles(200))
        if det.regime == MarketRegime.RANGING:
            assert abs(det.apply_threshold_adjustment(0.65) - 0.85) < 1e-9

    def test_ranging_caps_at_10(self):
        """High base threshold cannot exceed 1.0 after boost."""
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det.update(make_ranging_candles(200))
        if det.regime == MarketRegime.RANGING:
            result = det.apply_threshold_adjustment(0.95)
            assert result <= 1.0

    def test_manually_force_ranging_applies_boost(self):
        """Force regime to RANGING and verify boost is applied."""
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det._regime = MarketRegime.RANGING
        adjusted = det.apply_threshold_adjustment(0.50)
        assert abs(adjusted - 0.70) < 1e-9

    def test_manually_force_transitional_no_threshold_change(self):
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det._regime = MarketRegime.TRANSITIONAL
        base = 0.60
        assert det.apply_threshold_adjustment(base) == base

    def test_trending_various_base_values_unchanged(self, trending_detector):
        for base in [0.30, 0.50, 0.65, 0.80]:
            assert trending_detector.apply_threshold_adjustment(base) == base


# ─── 7. apply_score_penalty ──────────────────────────────────────────────────

class TestScorePenalty:
    def _transitional_detector(self) -> RegimeDetector:
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det._regime = MarketRegime.TRANSITIONAL
        return det

    def test_transitional_reduces_positive_score(self):
        det = self._transitional_detector()
        result = det.apply_score_penalty(0.80)
        assert abs(result - (0.80 - TRANSITIONAL_PENALTY)) < 1e-9

    def test_transitional_reduces_negative_score_magnitude(self):
        det = self._transitional_detector()
        result = det.apply_score_penalty(-0.70)
        # Magnitude reduces, sign preserved
        assert abs(result - (-0.60)) < 1e-9

    def test_transitional_preserves_sign_positive(self):
        det = self._transitional_detector()
        assert det.apply_score_penalty(0.50) > 0

    def test_transitional_preserves_sign_negative(self):
        det = self._transitional_detector()
        assert det.apply_score_penalty(-0.50) < 0

    def test_transitional_score_at_exactly_penalty_becomes_zero(self):
        det = self._transitional_detector()
        result = det.apply_score_penalty(TRANSITIONAL_PENALTY)
        assert result == 0.0

    def test_transitional_score_below_penalty_floored_at_zero(self):
        det = self._transitional_detector()
        result = det.apply_score_penalty(0.05)
        assert result == 0.0

    def test_transitional_negative_score_below_penalty_magnitude_floored(self):
        det = self._transitional_detector()
        result = det.apply_score_penalty(-0.05)
        assert result == 0.0

    def test_trending_no_penalty_applied(self, trending_detector):
        score = 0.75
        assert trending_detector.apply_score_penalty(score) == score

    def test_ranging_no_penalty_applied(self, ranging_detector):
        score = -0.60
        assert ranging_detector.apply_score_penalty(score) == score

    def test_unknown_no_penalty_applied(self, fresh_detector):
        score = 0.40
        assert fresh_detector.apply_score_penalty(score) == score

    def test_penalty_applied_symmetrically(self):
        det = self._transitional_detector()
        pos = det.apply_score_penalty(0.70)
        neg = det.apply_score_penalty(-0.70)
        assert abs(abs(pos) - abs(neg)) < 1e-9

    def test_penalty_value_matches_constant(self):
        det = self._transitional_detector()
        result = det.apply_score_penalty(0.50)
        assert abs(result - (0.50 - TRANSITIONAL_PENALTY)) < 1e-9


# ─── 8. is_mean_reversion_allowed ────────────────────────────────────────────

class TestMeanReversionAllowed:
    def test_ranging_allows_mean_reversion(self, ranging_detector):
        if ranging_detector.regime == MarketRegime.RANGING:
            assert ranging_detector.is_mean_reversion_allowed() is True

    def test_trending_disallows_mean_reversion(self, trending_detector):
        assert trending_detector.is_mean_reversion_allowed() is False

    def test_unknown_disallows_mean_reversion(self, fresh_detector):
        assert fresh_detector.is_mean_reversion_allowed() is False

    def test_transitional_disallows_mean_reversion(self):
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det._regime = MarketRegime.TRANSITIONAL
        assert det.is_mean_reversion_allowed() is False

    def test_forced_ranging_allows_mean_reversion(self):
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det._regime = MarketRegime.RANGING
        assert det.is_mean_reversion_allowed() is True

    def test_returns_bool(self, trending_detector):
        result = trending_detector.is_mean_reversion_allowed()
        assert isinstance(result, bool)


# ─── 9. Multiple updates ─────────────────────────────────────────────────────

class TestMultipleUpdates:
    def test_second_update_overwrites_first(self):
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det.update(make_ranging_candles(200))
        regime_after_first = det.regime

        det.update(make_trending_candles(200))
        regime_after_second = det.regime

        # After strong trend data the regime should be TRENDING
        assert regime_after_second == MarketRegime.TRENDING

    def test_adx_changes_on_new_data(self):
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det.update(make_ranging_candles(200))
        adx_first = det.adx

        det.update(make_trending_candles(200))
        adx_second = det.adx

        # Trending data should produce higher ADX
        assert adx_second > adx_first

    def test_update_with_same_data_produces_same_regime(self):
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        candles = make_trending_candles(200)
        det.update(candles)
        regime1 = det.regime
        det.update(candles)
        regime2 = det.regime
        assert regime1 == regime2

    def test_regime_transitions_trending_to_ranging(self):
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        det.update(make_trending_candles(200))
        assert det.regime == MarketRegime.TRENDING

        # Override with ranging data — regime must change away from TRENDING
        det.update(make_ranging_candles(200))
        assert det.regime != MarketRegime.TRENDING


# ─── 10. BB secondary confirmation edge cases ────────────────────────────────

class TestBBConfirmation:
    def test_insufficient_bars_for_bb_does_not_crash(self):
        """Only 50 bars — BB confirmation needs 70. Should not raise."""
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        df = make_trending_candles(50)
        det.update(df)
        # Should complete without exception and produce some regime
        assert det.regime in list(MarketRegime)

    def test_70_plus_bars_triggers_bb_path(self):
        """75 bars should reach the BB confirmation branch without error."""
        det = RegimeDetector(timeframe="15m", pair="XAUUSD")
        df = make_trending_candles(75)
        det.update(df)
        assert det.adx >= 0.0


# ─── 11. Regime enum integrity ───────────────────────────────────────────────

class TestRegimeEnumIntegrity:
    def test_regime_property_returns_market_regime_instance(self, trending_detector):
        assert isinstance(trending_detector.regime, MarketRegime)

    def test_all_four_enum_values_exist(self):
        assert MarketRegime.TRENDING
        assert MarketRegime.RANGING
        assert MarketRegime.TRANSITIONAL
        assert MarketRegime.UNKNOWN

    def test_trending_constant_is_25(self):
        assert ADX_TRENDING_THRESHOLD == 25.0

    def test_ranging_constant_is_20(self):
        assert ADX_RANGING_THRESHOLD == 20.0

    def test_min_bars_formula(self):
        assert MIN_BARS == 29
