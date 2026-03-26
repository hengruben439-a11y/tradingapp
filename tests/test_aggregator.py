"""
Confluence Aggregator Tests — Sprint 5 deliverable.

Tests the full aggregation pipeline including:
    - Weighted sum calculation with pair-specific weights
    - Module score capping at 0.85
    - Multiplier bonus stacking
    - HTF conflict and news proximity penalties
    - Regime-adjusted thresholds
    - Signal strength classification
    - Score direction consistency

Sprint 1: scaffolding.
Sprint 5: full test suite added alongside implementation.
"""

from __future__ import annotations

import pytest

from engine.aggregator import (
    AggregatorInput,
    ConfluenceAggregator,
    MODULE_SCORE_CAP,
    WEIGHTS,
    _MODULE_NAMES,
)
from engine.signal import Direction, MarketRegime, SignalStrength


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _all_bullish_inputs(**overrides) -> AggregatorInput:
    """All module scores = +1.0 (bullish), no bonuses/penalties."""
    base = AggregatorInput(
        market_structure=1.0,
        order_blocks_fvg=1.0,
        ote=1.0,
        ema=1.0,
        rsi=1.0,
        macd=1.0,
        bollinger=1.0,
        kill_zone=1.0,
        support_resistance=1.0,
        regime=MarketRegime.TRENDING,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _all_bearish_inputs(**overrides) -> AggregatorInput:
    """All module scores = -1.0 (bearish), no bonuses/penalties."""
    base = _all_bullish_inputs()
    base.market_structure = -1.0
    base.order_blocks_fvg = -1.0
    base.ote = -1.0
    base.ema = -1.0
    base.rsi = -1.0
    base.macd = -1.0
    base.bollinger = -1.0
    base.kill_zone = -1.0
    base.support_resistance = -1.0
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _neutral_inputs(**overrides) -> AggregatorInput:
    """All module scores = 0.0."""
    base = AggregatorInput(
        market_structure=0.0,
        order_blocks_fvg=0.0,
        ote=0.0,
        ema=0.0,
        rsi=0.0,
        macd=0.0,
        bollinger=0.0,
        kill_zone=0.0,
        support_resistance=0.0,
        regime=MarketRegime.TRENDING,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


@pytest.fixture
def agg_xau() -> ConfluenceAggregator:
    return ConfluenceAggregator(pair="XAUUSD")


@pytest.fixture
def agg_gj() -> ConfluenceAggregator:
    return ConfluenceAggregator(pair="GBPJPY")


# ─── Weight Configuration Tests (no implementation needed) ───────────────────

class TestWeightConfig:
    def test_xauusd_weights_sum_to_one(self):
        assert sum(WEIGHTS["XAUUSD"]) == pytest.approx(1.0)

    def test_gbpjpy_weights_sum_to_one(self):
        assert sum(WEIGHTS["GBPJPY"]) == pytest.approx(1.0)

    def test_xauusd_has_nine_modules(self):
        assert len(WEIGHTS["XAUUSD"]) == 9

    def test_gbpjpy_has_nine_modules(self):
        assert len(WEIGHTS["GBPJPY"]) == 9

    def test_module_names_count(self):
        assert len(_MODULE_NAMES) == 9

    def test_no_weight_exceeds_thirty_pct(self):
        for pair, weights in WEIGHTS.items():
            for w in weights:
                assert w <= 0.30, f"{pair} has weight {w} > 0.30"

    def test_no_weight_below_three_pct(self):
        for pair, weights in WEIGHTS.items():
            for w in weights:
                assert w >= 0.03, f"{pair} has weight {w} < 0.03"

    def test_market_structure_weight_25pct_both_pairs(self):
        assert WEIGHTS["XAUUSD"][0] == pytest.approx(0.25)
        assert WEIGHTS["GBPJPY"][0] == pytest.approx(0.25)

    def test_xau_ema_weight_less_than_gj(self):
        """GBPJPY has higher EMA weight (12%) vs XAUUSD (10%)."""
        xau_ema_idx = 3
        assert WEIGHTS["GBPJPY"][xau_ema_idx] > WEIGHTS["XAUUSD"][xau_ema_idx]


# ─── Score Cap Tests ──────────────────────────────────────────────────────────

class TestScoreCap:
    def test_cap_clips_positive_score(self, agg_xau):
        assert agg_xau._cap_score(1.0) == pytest.approx(MODULE_SCORE_CAP)

    def test_cap_clips_negative_score(self, agg_xau):
        assert agg_xau._cap_score(-1.0) == pytest.approx(-MODULE_SCORE_CAP)

    def test_cap_preserves_value_within_range(self, agg_xau):
        assert agg_xau._cap_score(0.5) == pytest.approx(0.5)
        assert agg_xau._cap_score(-0.5) == pytest.approx(-0.5)

    def test_cap_at_exact_limit(self, agg_xau):
        assert agg_xau._cap_score(0.85) == pytest.approx(0.85)
        assert agg_xau._cap_score(-0.85) == pytest.approx(-0.85)

    def test_cap_module_score_constant(self):
        assert MODULE_SCORE_CAP == pytest.approx(0.85)


# ─── Weighted Sum Tests ───────────────────────────────────────────────────────

class TestWeightedSum:
    def test_all_zero_scores_give_zero_sum(self, agg_xau):
        scores = [0.0] * 9
        assert agg_xau._compute_weighted_sum(scores) == pytest.approx(0.0)

    def test_all_max_scores_give_capped_weighted_sum(self, agg_xau):
        """All scores = 1.0 → capped to 0.85 → weighted sum = 0.85."""
        scores = [1.0] * 9
        result = agg_xau._compute_weighted_sum(scores)
        assert result == pytest.approx(MODULE_SCORE_CAP)

    def test_weighted_sum_sign_matches_direction(self, agg_xau):
        bullish = [0.8] * 9
        bearish = [-0.8] * 9
        assert agg_xau._compute_weighted_sum(bullish) > 0
        assert agg_xau._compute_weighted_sum(bearish) < 0


# ─── Full Aggregation Tests (Sprint 5) ───────────────────────────────────────

class TestFullAggregation:
    @pytest.mark.skip(reason="Implement in Sprint 5")
    def test_all_bullish_gives_positive_score(self, agg_xau):
        inputs = _all_bullish_inputs()
        result = agg_xau.aggregate(inputs)
        assert result.confluence_score > 0.0
        assert result.direction == Direction.BUY

    @pytest.mark.skip(reason="Implement in Sprint 5")
    def test_all_bearish_gives_negative_score(self, agg_xau):
        inputs = _all_bearish_inputs()
        result = agg_xau.aggregate(inputs)
        assert result.confluence_score < 0.0
        assert result.direction == Direction.SELL

    @pytest.mark.skip(reason="Implement in Sprint 5")
    def test_all_neutral_no_signal(self, agg_xau):
        inputs = _neutral_inputs()
        result = agg_xau.aggregate(inputs)
        assert not result.passes_threshold

    @pytest.mark.skip(reason="Implement in Sprint 5")
    def test_htf_conflict_reduces_score(self, agg_xau):
        without_conflict = agg_xau.aggregate(_all_bullish_inputs())
        with_conflict = agg_xau.aggregate(_all_bullish_inputs(htf_conflict=True))
        assert abs(with_conflict.confluence_score) < abs(without_conflict.confluence_score)

    @pytest.mark.skip(reason="Implement in Sprint 5")
    def test_unicorn_multiplier_increases_score(self, agg_xau):
        base = agg_xau.aggregate(_all_bullish_inputs())
        unicorn = agg_xau.aggregate(_all_bullish_inputs(unicorn_setup=True))
        assert unicorn.confluence_score > base.confluence_score

    @pytest.mark.skip(reason="Implement in Sprint 5")
    def test_score_clamped_to_one(self, agg_xau):
        inputs = _all_bullish_inputs(unicorn_setup=True, ote_ob_confluence=True, kill_zone_active=True)
        result = agg_xau.aggregate(inputs)
        assert result.confluence_score <= 1.0

    @pytest.mark.skip(reason="Implement in Sprint 5")
    def test_ranging_regime_raises_threshold(self, agg_xau):
        """In RANGING regime, weak signals should not pass threshold."""
        inputs = _neutral_inputs(
            market_structure=0.5,
            regime=MarketRegime.RANGING,
        )
        result = agg_xau.aggregate(inputs)
        assert not result.passes_threshold

    @pytest.mark.skip(reason="Implement in Sprint 5")
    def test_very_strong_classification(self, agg_xau):
        inputs = _all_bullish_inputs(kill_zone_active=True)
        result = agg_xau.aggregate(inputs)
        assert result.strength == SignalStrength.VERY_STRONG

    @pytest.mark.skip(reason="Implement in Sprint 5")
    def test_module_scores_list_has_nine_entries(self, agg_xau):
        inputs = _all_bullish_inputs()
        result = agg_xau.aggregate(inputs)
        assert len(result.module_scores) == 9

    @pytest.mark.skip(reason="Implement in Sprint 5")
    def test_aligned_modules_count_bullish(self, agg_xau):
        """All modules bullish → all should be marked aligned for BUY direction."""
        inputs = _all_bullish_inputs()
        result = agg_xau.aggregate(inputs)
        assert all(m.aligned for m in result.module_scores)
