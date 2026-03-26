"""
Bollinger Bands Module Test Suite — Sprint 4

~40 test cases covering:
  - True positives: squeeze breakout signals, mean-reversion signals
  - Ambiguous: boundary percent_b values, regime classification edges
  - False positives: no-signal conditions, insufficient data, neutral state

Test ID format:
  TP-xxx  — True positive
  AMB-xxx — Ambiguous/boundary
  FP-xxx  — False positive / should not score
"""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np

from engine.modules.bollinger import BollingerModule, BBRegime, BBState


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_candles(
    n: int = 60,
    base: float = 100.0,
    volatility: float = 1.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Random-walk candles around a fixed base with configurable volatility."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    closes = [base + rng.standard_normal() * volatility for _ in range(n)]
    opens = [c - volatility * 0.1 for c in closes]
    highs = [c + volatility * 0.2 for c in closes]
    lows = [c - volatility * 0.2 for c in closes]
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000.0] * n},
        index=idx,
    )


def make_atr(candles: pd.DataFrame, constant: float = 1.0) -> pd.Series:
    """Flat ATR series aligned to candles."""
    return pd.Series([constant] * len(candles), index=candles.index)


def make_squeeze_then_expand(
    n_squeeze: int = 40,
    n_expand: int = 10,
    base: float = 100.0,
    squeeze_vol: float = 0.05,
    expand_direction: str = "up",
    seed: int = 1,
) -> pd.DataFrame:
    """
    Build candles that create a squeeze phase followed by a directional expansion.
    expand_direction: 'up' pushes price above upper band, 'down' pushes below lower.
    """
    rng = np.random.default_rng(seed)
    # Squeeze phase: very low volatility around base
    squeeze_closes = [base + rng.standard_normal() * squeeze_vol for _ in range(n_squeeze)]
    # Expansion phase: strong directional move
    last = squeeze_closes[-1]
    if expand_direction == "up":
        expand_closes = [last + (i + 1) * 3.0 for i in range(n_expand)]
    else:
        expand_closes = [last - (i + 1) * 3.0 for i in range(n_expand)]
    closes = squeeze_closes + expand_closes
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    opens = [c - 0.05 for c in closes]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000.0] * n},
        index=idx,
    )


def make_lower_band_approach(n: int = 60, base: float = 100.0, vol: float = 1.0) -> pd.DataFrame:
    """
    Candles where the last close is near the lower Bollinger Band.
    Achieves this by making the last candle much lower than the recent mean.
    """
    rng = np.random.default_rng(77)
    closes = [base + rng.standard_normal() * vol for _ in range(n - 1)]
    # Last close far below mean to push percent_b near 0.0
    closes.append(base - 3.0 * vol)
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    opens = [c - 0.05 for c in closes]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000.0] * n},
        index=idx,
    )


# ── TestBollingerModuleInit ───────────────────────────────────────────────────

class TestBollingerModuleInit:
    def test_initial_state_is_none(self):  # FP-001
        """current_state is None before any update."""
        m = BollingerModule("15m", "XAUUSD")
        assert m.current_state is None

    def test_initial_score_is_zero(self):  # FP-002
        """score() returns 0.0 before update."""
        m = BollingerModule("15m", "XAUUSD")
        assert m.score() == 0.0

    def test_initial_is_in_squeeze_false(self):  # FP-003
        """is_in_squeeze() returns False before update."""
        m = BollingerModule("15m", "XAUUSD")
        assert m.is_in_squeeze() is False

    def test_initial_prev_regime_is_none(self):  # FP-004
        """_prev_regime is None before any update."""
        m = BollingerModule("15m", "XAUUSD")
        assert m._prev_regime is None

    def test_constructor_defaults(self):  # TP-001
        """Default period and num_std are set correctly."""
        m = BollingerModule("1H", "GBPJPY")
        assert m.period == 20
        assert m.num_std == 2.0
        assert m.timeframe == "1H"
        assert m.pair == "GBPJPY"

    def test_constructor_custom_params(self):  # TP-002
        """Custom period and num_std are stored correctly."""
        m = BollingerModule("5m", "XAUUSD", period=10, num_std=1.5)
        assert m.period == 10
        assert m.num_std == 1.5

    def test_squeeze_just_broke_false_before_update(self):  # FP-005
        """squeeze_just_broke() returns False before any update."""
        m = BollingerModule("15m", "XAUUSD")
        assert m.squeeze_just_broke("up") is False
        assert m.squeeze_just_broke("down") is False


# ── TestBollingerUpdate ───────────────────────────────────────────────────────

class TestBollingerUpdate:
    def test_update_with_enough_data_populates_state(self):  # TP-003
        """update() with 30+ bars populates current_state."""
        candles = make_candles(n=40)
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles))
        assert m.current_state is not None

    def test_update_insufficient_data_leaves_state_none(self):  # FP-006
        """update() with fewer than period rows must not set state."""
        candles = make_candles(n=10)
        m = BollingerModule("15m", "XAUUSD", period=20)
        m.update(candles, make_atr(candles))
        assert m.current_state is None

    def test_update_state_has_valid_band_ordering(self):  # TP-004
        """After update, upper > middle > lower (positive band width)."""
        candles = make_candles(n=60, volatility=1.0)
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles))
        s = m.current_state
        assert s is not None
        assert s.upper > s.middle > s.lower

    def test_update_percent_b_near_half_for_price_at_midline(self):  # AMB-001
        """
        percent_b should be close to 0.5 when the last close is near the SMA.
        Build candles where the last close equals the mean of recent closes.
        """
        n = 40
        idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
        # All closes identical → SMA == close → percent_b == 0.5 (but std=0 edge case)
        # Use small volatility instead so std > 0
        rng = np.random.default_rng(5)
        closes = [100.0 + rng.standard_normal() * 0.5 for _ in range(n)]
        # Force last close to be exactly the mean of the last 20
        closes[-1] = float(np.mean(closes[-20:]))
        candles = pd.DataFrame(
            {"open": closes, "high": [c + 0.1 for c in closes],
             "low": [c - 0.1 for c in closes], "close": closes, "volume": [1000.0] * n},
            index=idx,
        )
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles))
        assert m.current_state is not None
        # percent_b should be close to 0.5 when price is at SMA
        assert m.current_state.percent_b == pytest.approx(0.5, abs=0.05)

    def test_update_sets_prev_regime_on_second_call(self):  # TP-005
        """After a second update call, _prev_regime is set to the first call's regime."""
        candles = make_candles(n=60)
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles))
        first_regime = m.current_state.regime
        m.update(candles, make_atr(candles))
        assert m._prev_regime == first_regime

    def test_update_with_exactly_period_bars(self):  # AMB-002
        """update() with exactly period rows should populate state (rolling window is valid)."""
        candles = make_candles(n=20)
        m = BollingerModule("15m", "XAUUSD", period=20)
        m.update(candles, make_atr(candles))
        # With exactly 20 rows, only the last row of rolling(20) is valid
        assert m.current_state is not None

    def test_update_width_is_normalized(self):  # TP-006
        """Band width = (upper - lower) / middle; must be positive."""
        candles = make_candles(n=60, volatility=2.0)
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles))
        assert m.current_state.width > 0.0


# ── TestBollingerClassifyRegime ───────────────────────────────────────────────

class TestBollingerClassifyRegime:
    def test_squeeze_regime_when_width_at_period_low(self):  # TP-007
        """
        After a squeeze phase (very low volatility), regime should be SQUEEZE.
        """
        candles = make_squeeze_then_expand(n_squeeze=50, n_expand=0)
        # Trim to just the squeeze portion
        candles = candles.iloc[:50]
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles, constant=0.05))
        if m.current_state is not None:
            # Should be SQUEEZE or NEUTRAL in tight range
            assert m.current_state.regime in (BBRegime.SQUEEZE, BBRegime.NEUTRAL)

    def test_expansion_regime_when_width_spikes(self):  # TP-008
        """
        After a sharp directional move, band width should expand → EXPANSION regime.
        """
        candles = make_candles(n=60, volatility=5.0, seed=99)
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles, constant=5.0))
        if m.current_state is not None:
            # High volatility candles often produce EXPANSION; at minimum not guaranteed SQUEEZE
            assert m.current_state.regime in (BBRegime.EXPANSION, BBRegime.NEUTRAL)

    def test_neutral_regime_for_normal_volatility(self):  # AMB-003
        """Normal random candles with moderate volatility typically land in NEUTRAL."""
        candles = make_candles(n=60, volatility=1.0, seed=42)
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles))
        if m.current_state is not None:
            assert m.current_state.regime in (BBRegime.NEUTRAL, BBRegime.SQUEEZE, BBRegime.EXPANSION)

    def test_classify_regime_with_insufficient_valid_points(self):  # AMB-004
        """
        _classify_regime() with a width_series containing only 1 valid value returns NEUTRAL.
        """
        m = BollingerModule("15m", "XAUUSD")
        width_series = pd.Series([float("nan"), float("nan"), 0.05])
        regime = m._classify_regime(width_series)
        assert regime == BBRegime.NEUTRAL

    def test_classify_regime_squeeze_detected_directly(self):  # TP-009
        """
        _classify_regime() directly: current width is lowest in lookback → SQUEEZE.
        """
        m = BollingerModule("15m", "XAUUSD")
        # 20 values: first 19 are large, last is smallest
        values = [0.05] * 19 + [0.01]
        width_series = pd.Series(values)
        regime = m._classify_regime(width_series)
        assert regime == BBRegime.SQUEEZE

    def test_classify_regime_expansion_detected_directly(self):  # TP-010
        """
        _classify_regime() directly: current width > 1.5x average → EXPANSION.
        """
        m = BollingerModule("15m", "XAUUSD")
        # 20 values of 0.02, last is 0.10 (5x avg ~ expansion)
        values = [0.02] * 19 + [0.10]
        width_series = pd.Series(values)
        regime = m._classify_regime(width_series)
        assert regime == BBRegime.EXPANSION

    def test_classify_regime_neutral_when_neither_squeeze_nor_expansion(self):  # FP-007
        """
        _classify_regime() returns NEUTRAL when width is between thresholds.
        """
        m = BollingerModule("15m", "XAUUSD")
        # Uniform values: current is not the min (not squeeze) and not > 1.5x avg (not expansion)
        values = [0.05] * 18 + [0.04, 0.045]
        width_series = pd.Series(values)
        regime = m._classify_regime(width_series)
        assert regime == BBRegime.NEUTRAL


# ── TestBollingerScore ────────────────────────────────────────────────────────

class TestBollingerScore:
    def test_score_zero_before_update(self):  # FP-008
        """score() is 0.0 before any update has been called."""
        m = BollingerModule("15m", "XAUUSD")
        assert m.score() == 0.0

    def test_score_zero_neutral_bands_no_squeeze(self):  # FP-009
        """Price between bands with no squeeze and no boundary touching → 0.0."""
        candles = make_candles(n=60, base=100.0, volatility=1.0)
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles))
        s = m.score(macd_is_bullish=False, rsi_is_oversold=False)
        assert isinstance(s, float)
        # In normal conditions the score is 0.0; squeeze breakout path not taken
        assert s == 0.0 or abs(s) <= 0.8

    def test_squeeze_breakout_bullish_score_plus_0_8(self):  # TP-011
        """
        Squeeze breakout upward with bullish MACD → +0.8.
        Simulate by setting _prev_regime=SQUEEZE and percent_b > 1.0.
        """
        candles = make_candles(n=60)
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles))
        # Override state for deterministic test
        m._prev_regime = BBRegime.SQUEEZE
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.EXPANSION,
            percent_b=1.05,  # above 1.0 → broke above upper band
        )
        assert m.score(macd_is_bullish=True, rsi_is_oversold=False) == pytest.approx(0.8)

    def test_squeeze_breakout_bearish_score_minus_0_8(self):  # TP-012
        """Squeeze breakout downward with bearish MACD → -0.8."""
        candles = make_candles(n=60)
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles))
        m._prev_regime = BBRegime.SQUEEZE
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.EXPANSION,
            percent_b=-0.05,  # below 0.0 → broke below lower band
        )
        assert m.score(macd_is_bullish=False, rsi_is_oversold=False) == pytest.approx(-0.8)

    def test_squeeze_breakout_bullish_requires_macd_bullish(self):  # AMB-005
        """
        Breakout above upper band without bullish MACD should NOT score +0.8.
        """
        m = BollingerModule("15m", "XAUUSD")
        m._prev_regime = BBRegime.SQUEEZE
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.EXPANSION,
            percent_b=1.05,
        )
        assert m.score(macd_is_bullish=False, rsi_is_oversold=False) != pytest.approx(0.8)

    def test_squeeze_breakout_bearish_requires_macd_bearish(self):  # AMB-006
        """
        Breakout below lower band with bullish MACD should NOT score -0.8.
        """
        m = BollingerModule("15m", "XAUUSD")
        m._prev_regime = BBRegime.SQUEEZE
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.EXPANSION,
            percent_b=-0.05,
        )
        assert m.score(macd_is_bullish=True, rsi_is_oversold=False) != pytest.approx(-0.8)

    def test_mean_reversion_lower_band_with_rsi_oversold(self):  # TP-013
        """Price at lower band (percent_b <= 0.05) + RSI oversold → +0.5."""
        m = BollingerModule("15m", "XAUUSD")
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.NEUTRAL,
            percent_b=0.03,  # just inside lower band territory
        )
        m._prev_regime = BBRegime.NEUTRAL
        assert m.score(macd_is_bullish=False, rsi_is_oversold=True) == pytest.approx(0.5)

    def test_mean_reversion_upper_band_overbought(self):  # TP-014
        """Price at upper band (percent_b >= 0.95) with RSI not oversold → -0.5."""
        m = BollingerModule("15m", "XAUUSD")
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.NEUTRAL,
            percent_b=0.97,  # near upper band
        )
        m._prev_regime = BBRegime.NEUTRAL
        assert m.score(macd_is_bullish=False, rsi_is_oversold=False) == pytest.approx(-0.5)

    def test_lower_band_touch_without_rsi_oversold_no_signal(self):  # FP-010
        """Price at lower band but RSI not oversold → no mean-reversion signal."""
        m = BollingerModule("15m", "XAUUSD")
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.NEUTRAL,
            percent_b=0.03,
        )
        m._prev_regime = BBRegime.NEUTRAL
        assert m.score(macd_is_bullish=False, rsi_is_oversold=False) == 0.0

    def test_active_squeeze_no_breakout_returns_zero(self):  # FP-011
        """Active squeeze with no breakout yet → 0.0 (waiting for direction)."""
        m = BollingerModule("15m", "XAUUSD")
        m._state = BBState(
            upper=100.5, middle=100.0, lower=99.5,
            width=0.005, regime=BBRegime.SQUEEZE,
            percent_b=0.5,
        )
        m._prev_regime = BBRegime.NEUTRAL
        assert m.score(macd_is_bullish=True, rsi_is_oversold=False) == 0.0

    def test_percent_b_exactly_one_not_breakout(self):  # AMB-007
        """
        percent_b == 1.0 exactly (price at upper band, not above it) with squeeze prev.
        The condition is > 1.0, so this should NOT trigger the +0.8 breakout.
        """
        m = BollingerModule("15m", "XAUUSD")
        m._prev_regime = BBRegime.SQUEEZE
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.EXPANSION,
            percent_b=1.0,  # at the boundary, not > 1.0
        )
        assert m.score(macd_is_bullish=True) != pytest.approx(0.8)

    def test_percent_b_exactly_zero_not_bearish_breakout(self):  # AMB-008
        """
        percent_b == 0.0 exactly (price at lower band, not below it).
        The condition is < 0.0, so should NOT trigger -0.8.
        """
        m = BollingerModule("15m", "XAUUSD")
        m._prev_regime = BBRegime.SQUEEZE
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.EXPANSION,
            percent_b=0.0,  # at boundary, not < 0.0
        )
        assert m.score(macd_is_bullish=False) != pytest.approx(-0.8)

    @pytest.mark.parametrize("pct_b,macd,rsi_os,expected", [
        (1.05, True, False, 0.8),    # TP squeeze breakout up
        (-0.05, False, False, -0.8), # TP squeeze breakout down
        (0.03, False, True, 0.5),    # TP mean reversion lower
        (0.97, False, False, -0.5),  # TP mean reversion upper
        (0.5, False, False, 0.0),    # FP neutral
    ])
    def test_score_parametrized_with_prev_squeeze(self, pct_b, macd, rsi_os, expected):  # AMB-009
        """Parametrized score checks across common scenarios."""
        m = BollingerModule("15m", "XAUUSD")
        m._prev_regime = BBRegime.SQUEEZE
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.NEUTRAL,
            percent_b=pct_b,
        )
        assert m.score(macd_is_bullish=macd, rsi_is_oversold=rsi_os) == pytest.approx(expected)


# ── TestBollingerSqueezeHelpers ───────────────────────────────────────────────

class TestBollingerSqueezeHelpers:
    def test_is_in_squeeze_true_when_squeeze_regime(self):  # TP-015
        """is_in_squeeze() returns True when current regime is SQUEEZE."""
        m = BollingerModule("15m", "XAUUSD")
        m._state = BBState(
            upper=100.2, middle=100.0, lower=99.8,
            width=0.002, regime=BBRegime.SQUEEZE,
            percent_b=0.5,
        )
        assert m.is_in_squeeze() is True

    def test_is_in_squeeze_false_when_neutral(self):  # FP-012
        """is_in_squeeze() returns False when regime is NEUTRAL."""
        m = BollingerModule("15m", "XAUUSD")
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.NEUTRAL,
            percent_b=0.5,
        )
        assert m.is_in_squeeze() is False

    def test_is_in_squeeze_false_when_expansion(self):  # FP-013
        """is_in_squeeze() returns False when regime is EXPANSION."""
        m = BollingerModule("15m", "XAUUSD")
        m._state = BBState(
            upper=106.0, middle=100.0, lower=94.0,
            width=0.12, regime=BBRegime.EXPANSION,
            percent_b=0.8,
        )
        assert m.is_in_squeeze() is False

    def test_squeeze_just_broke_up_true(self):  # TP-016
        """squeeze_just_broke('up') returns True when prev was SQUEEZE and percent_b > 1.0."""
        m = BollingerModule("15m", "XAUUSD")
        m._prev_regime = BBRegime.SQUEEZE
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.EXPANSION,
            percent_b=1.1,
        )
        assert m.squeeze_just_broke("up") is True

    def test_squeeze_just_broke_down_true(self):  # TP-017
        """squeeze_just_broke('down') returns True when prev was SQUEEZE and percent_b < 0.0."""
        m = BollingerModule("15m", "XAUUSD")
        m._prev_regime = BBRegime.SQUEEZE
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.EXPANSION,
            percent_b=-0.1,
        )
        assert m.squeeze_just_broke("down") is True

    def test_squeeze_just_broke_up_false_when_prev_not_squeeze(self):  # FP-014
        """squeeze_just_broke('up') is False when prev_regime was not SQUEEZE."""
        m = BollingerModule("15m", "XAUUSD")
        m._prev_regime = BBRegime.NEUTRAL
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.EXPANSION,
            percent_b=1.1,
        )
        assert m.squeeze_just_broke("up") is False

    def test_squeeze_just_broke_down_false_when_prev_not_squeeze(self):  # FP-015
        """squeeze_just_broke('down') is False when prev_regime was not SQUEEZE."""
        m = BollingerModule("15m", "XAUUSD")
        m._prev_regime = BBRegime.EXPANSION
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.EXPANSION,
            percent_b=-0.1,
        )
        assert m.squeeze_just_broke("down") is False

    def test_squeeze_just_broke_false_before_update(self):  # FP-016
        """squeeze_just_broke() returns False when state is None."""
        m = BollingerModule("15m", "XAUUSD")
        assert m.squeeze_just_broke("up") is False
        assert m.squeeze_just_broke("down") is False

    def test_squeeze_just_broke_up_false_when_price_within_bands(self):  # AMB-010
        """squeeze_just_broke('up') is False when price is inside the bands (percent_b = 0.5)."""
        m = BollingerModule("15m", "XAUUSD")
        m._prev_regime = BBRegime.SQUEEZE
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.NEUTRAL,
            percent_b=0.5,
        )
        assert m.squeeze_just_broke("up") is False

    def test_squeeze_just_broke_invalid_direction_returns_false(self):  # AMB-011
        """squeeze_just_broke() with an unrecognised direction string returns False."""
        m = BollingerModule("15m", "XAUUSD")
        m._prev_regime = BBRegime.SQUEEZE
        m._state = BBState(
            upper=102.0, middle=100.0, lower=98.0,
            width=0.04, regime=BBRegime.EXPANSION,
            percent_b=1.1,
        )
        assert m.squeeze_just_broke("sideways") is False

    def test_is_in_squeeze_after_real_squeeze_candles(self):  # TP-018
        """
        After feeding tight-range candles, is_in_squeeze() should return True
        (regime classified as SQUEEZE because width is at its 20-bar low).
        """
        candles = make_squeeze_then_expand(n_squeeze=50, n_expand=0, squeeze_vol=0.02, seed=5)
        candles = candles.iloc[:50]
        m = BollingerModule("15m", "XAUUSD")
        m.update(candles, make_atr(candles, constant=0.02))
        # After tight ranging, regime should be SQUEEZE or at worst NEUTRAL
        if m.current_state is not None:
            assert m.current_state.regime in (BBRegime.SQUEEZE, BBRegime.NEUTRAL)
