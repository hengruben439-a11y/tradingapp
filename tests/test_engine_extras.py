"""
Tests for the supplementary engine components:
  - PostMortemGenerator
  - ConflictAnalyzer
  - NewsReactionService
  - SignalDecay / DecayResult
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from engine.postmortem import PostMortemGenerator, PostMortem
from engine.conflict_templates import ConflictAnalyzer, ConflictAnalysis
from data.news_reactions import NewsReactionService
from engine.signal_decay import SignalDecay, DecayResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_signal(
    direction: str = "BUY",
    module_scores: dict | None = None,
    pair: str = "XAUUSD",
    generated_at: datetime | None = None,
) -> dict:
    """Helper: build a minimal signal dict."""
    if module_scores is None:
        module_scores = {
            "market_structure": 0.8,
            "order_blocks_fvg": 0.7,
            "ote": 0.6,
            "ema": 0.5,
            "rsi": 0.4,
            "macd": -0.2,
            "bollinger": 0.1,
            "kill_zone": 0.3,
            "support_resistance": 0.6,
        }
    return {
        "signal_id": "test-signal-001",
        "direction": direction,
        "entry_price": 2341.50,
        "stop_loss": 2320.00,
        "module_scores": module_scores,
        "generated_at": generated_at or datetime.now(timezone.utc),
        "pair": pair,
    }


def _make_exit_bar(
    direction: str = "BUY",
    sl: float = 2320.00,
    pair: str = "XAUUSD",
    timestamp: datetime | None = None,
    stop_hunt: bool = False,
    gap: bool = False,
) -> dict:
    """Helper: build a minimal exit bar dict."""
    ts = timestamp or datetime.now(timezone.utc)

    if gap:
        # Bar opens below SL for a BUY — gap down
        bar_open = sl - 5.0 if direction == "BUY" else sl + 5.0
        return {
            "open": bar_open,
            "high": bar_open + 2.0,
            "low": bar_open - 2.0,
            "close": bar_open + 1.0,
            "timestamp": ts,
            "pair": pair,
        }

    if stop_hunt and direction == "BUY":
        # Wick down well below SL, close recovers above SL
        return {
            "open": sl + 2.0,
            "high": sl + 4.0,
            "low": sl - 2.0,  # spike through SL
            "close": sl + 1.5,  # recovers above SL
            "timestamp": ts,
            "pair": pair,
        }

    # Normal SL hit
    return {
        "open": sl + 1.0,
        "high": sl + 2.0,
        "low": sl - 1.0,
        "close": sl - 0.5,
        "timestamp": ts,
        "pair": pair,
    }


def _make_news_event(
    impact: str = "HIGH",
    offset_minutes: int = 0,
    name: str = "NFP",
) -> dict:
    """Helper: build a news event dict near now."""
    ts = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    return {
        "name": name,
        "timestamp": ts,
        "impact": impact,
    }


# ── PostMortemGenerator tests ─────────────────────────────────────────────────

class TestPostMortemGenerator:

    def test_news_attributed_true_when_news_within_30min(self):
        """Generates post-mortem with news_attributed=True when news is recent."""
        gen = PostMortemGenerator()
        signal = _make_signal()
        exit_bar = _make_exit_bar()
        # News event 15 minutes ago — within 30-minute window
        news = [_make_news_event(impact="HIGH", offset_minutes=-15)]

        pm = gen.generate(signal, exit_bar, news_events=news)

        assert isinstance(pm, PostMortem)
        assert pm.news_attributed is True
        assert pm.failure_category == "news_spike"

    def test_news_attributed_false_when_no_news(self):
        """Generates post-mortem with news_attributed=False when no news events."""
        gen = PostMortemGenerator()
        signal = _make_signal()
        exit_bar = _make_exit_bar()

        pm = gen.generate(signal, exit_bar, news_events=None)

        assert pm.news_attributed is False

    def test_news_attributed_false_when_news_outside_window(self):
        """News event 60+ minutes ago should not be attributed."""
        gen = PostMortemGenerator()
        signal = _make_signal()
        exit_bar = _make_exit_bar()
        # News event 90 minutes ago — outside the 30-minute window
        news = [_make_news_event(impact="HIGH", offset_minutes=-90)]

        pm = gen.generate(signal, exit_bar, news_events=news)

        assert pm.news_attributed is False

    def test_failed_module_is_highest_score_agreeing_with_direction(self):
        """Identifies the module with the highest score in the signal direction."""
        gen = PostMortemGenerator()
        # market_structure has highest positive score for a BUY
        module_scores = {
            "market_structure": 0.9,   # highest positive
            "order_blocks_fvg": 0.7,
            "ema": 0.5,
            "rsi": -0.3,               # disagrees
        }
        signal = _make_signal(direction="BUY", module_scores=module_scores)
        exit_bar = _make_exit_bar(direction="BUY")

        pm = gen.generate(signal, exit_bar, news_events=None)

        assert pm.failed_module == "market_structure"

    def test_failed_module_for_sell_is_highest_negative_score(self):
        """For a SELL signal, picks module with largest magnitude negative score."""
        gen = PostMortemGenerator()
        module_scores = {
            "market_structure": -0.9,   # strongest sell vote
            "order_blocks_fvg": -0.6,
            "ema": 0.2,                 # disagrees (bullish)
        }
        signal = _make_signal(
            direction="SELL",
            module_scores=module_scores,
            pair="GBPJPY",
        )
        exit_bar = _make_exit_bar(direction="SELL", sl=155.50, pair="GBPJPY")

        pm = gen.generate(signal, exit_bar, news_events=None)

        assert pm.failed_module == "market_structure"

    def test_postmortem_has_lesson_and_what_happened(self):
        """Post-mortem always populates lesson and what_happened strings."""
        gen = PostMortemGenerator()
        signal = _make_signal()
        exit_bar = _make_exit_bar()

        pm = gen.generate(signal, exit_bar, news_events=None)

        assert isinstance(pm.what_happened, str)
        assert len(pm.what_happened) > 10
        assert isinstance(pm.lesson, str)
        assert len(pm.lesson) > 10

    def test_stop_hunt_detected_when_wick_exceeds_sl(self):
        """was_stop_hunt=True when bar wicks well through SL then recovers."""
        gen = PostMortemGenerator()
        signal = _make_signal(direction="BUY")
        # The stop_hunt helper creates a bar with a wick below SL and close above SL
        exit_bar = _make_exit_bar(direction="BUY", sl=2320.00, stop_hunt=True)

        pm = gen.generate(signal, exit_bar, news_events=None)

        assert pm.was_stop_hunt is True

    def test_gap_detected_when_bar_opens_beyond_sl(self):
        """was_gap=True when bar opens below SL level (gap down for BUY)."""
        gen = PostMortemGenerator()
        signal = _make_signal(direction="BUY")
        exit_bar = _make_exit_bar(direction="BUY", sl=2320.00, gap=True)

        pm = gen.generate(signal, exit_bar, news_events=None)

        assert pm.was_gap is True

    def test_signal_id_preserved_in_postmortem(self):
        """signal_id from signal dict is preserved in PostMortem."""
        gen = PostMortemGenerator()
        signal = _make_signal()
        signal["signal_id"] = "abc-123"
        exit_bar = _make_exit_bar()

        pm = gen.generate(signal, exit_bar)

        assert pm.signal_id == "abc-123"


# ── ConflictAnalyzer tests ────────────────────────────────────────────────────

class TestConflictAnalyzer:

    def test_bullish_entry_bearish_htf_returns_explanation(self):
        """Conflicting bullish LTF vs bearish HTF returns a conflict analysis."""
        analyzer = ConflictAnalyzer()

        result = analyzer.analyze(
            entry_tf_state="bullish",
            htf_state="bearish",
            entry_tf="15m",
            htf="4H",
            pair="XAUUSD",
        )

        assert isinstance(result, ConflictAnalysis)
        assert result.confidence_penalty > 0
        assert "15m" in result.explanation or "4H" in result.explanation
        assert len(result.explanation) > 20

    def test_bearish_entry_bullish_htf_returns_explanation(self):
        """Conflicting bearish LTF vs bullish HTF returns an explanation."""
        analyzer = ConflictAnalyzer()

        result = analyzer.analyze(
            entry_tf_state="bearish",
            htf_state="bullish",
            entry_tf="1H",
            htf="1D",
            pair="GBPJPY",
        )

        assert isinstance(result, ConflictAnalysis)
        assert result.confidence_penalty >= 0.20  # Counter-trend = high penalty

    def test_same_direction_returns_zero_penalty(self):
        """Aligned trends should produce zero confidence penalty."""
        analyzer = ConflictAnalyzer()

        result = analyzer.analyze(
            entry_tf_state="bullish",
            htf_state="bullish",
            entry_tf="15m",
            htf="4H",
            pair="XAUUSD",
        )

        assert result is not None
        assert result.confidence_penalty == 0.0

    def test_both_bearish_returns_zero_penalty(self):
        """Aligned bearish trends should also produce zero penalty."""
        analyzer = ConflictAnalyzer()

        result = analyzer.analyze(
            entry_tf_state="bearish",
            htf_state="bearish",
            entry_tf="4H",
            htf="1D",
            pair="GBPJPY",
        )

        assert result is not None
        assert result.confidence_penalty == 0.0

    def test_unknown_state_returns_none(self):
        """Unrecognised state strings should return None."""
        analyzer = ConflictAnalyzer()

        result = analyzer.analyze(
            entry_tf_state="unknown",
            htf_state="bullish",
            entry_tf="15m",
            htf="4H",
            pair="XAUUSD",
        )

        assert result is None

    def test_ranging_htf_reduces_confidence(self):
        """Bullish entry in ranging HTF should reduce confidence."""
        analyzer = ConflictAnalyzer()

        result = analyzer.analyze(
            entry_tf_state="bullish",
            htf_state="ranging",
            entry_tf="5m",
            htf="1H",
            pair="XAUUSD",
        )

        assert result is not None
        assert result.confidence_penalty > 0

    def test_recommendation_is_valid_string(self):
        """Recommendation is one of the three valid options."""
        analyzer = ConflictAnalyzer()
        valid_recs = {"avoid", "reduce_size", "monitor_htf"}

        result = analyzer.analyze(
            entry_tf_state="bullish",
            htf_state="bearish",
            entry_tf="15m",
            htf="4H",
            pair="XAUUSD",
        )

        assert result is not None
        assert result.recommendation in valid_recs

    def test_tf_labels_injected_into_explanation(self):
        """Entry TF and HTF labels should appear in the explanation text."""
        analyzer = ConflictAnalyzer()

        result = analyzer.analyze(
            entry_tf_state="bearish",
            htf_state="ranging",
            entry_tf="30m",
            htf="1D",
            pair="XAUUSD",
        )

        assert result is not None
        # At least one of the TF labels should appear in the explanation
        assert "30m" in result.explanation or "1D" in result.explanation


# ── NewsReactionService tests ─────────────────────────────────────────────────

class TestNewsReactionService:

    def test_get_description_formats_correctly(self):
        """get_description returns a human-readable string with key values."""
        service = NewsReactionService()

        desc = service.get_description("XAUUSD", "NFP")

        assert "NFP" in desc
        assert "XAUUSD" in desc
        assert "200" in desc    # lower bound of range
        assert "500" in desc    # upper bound of range
        # Should mention time duration
        assert "hour" in desc or "minute" in desc

    def test_get_reaction_returns_none_for_unknown_event(self):
        """Unknown event name returns None without raising."""
        service = NewsReactionService()

        result = service.get_reaction("XAUUSD", "UNKNOWN_EVENT_XYZ")

        assert result is None

    def test_get_reaction_returns_none_for_unknown_pair(self):
        """Unknown pair returns None without raising."""
        service = NewsReactionService()

        result = service.get_reaction("EURUSD", "NFP")

        assert result is None

    def test_get_reaction_returns_dict_for_known_event(self):
        """Known pair+event combination returns a properly structured dict."""
        service = NewsReactionService()

        result = service.get_reaction("GBPJPY", "BOE")

        assert result is not None
        assert "avg_move_pips" in result
        assert "range" in result
        assert "direction_bias" in result
        assert "avg_duration_min" in result

    def test_get_description_for_unknown_event_returns_message(self):
        """Unknown event returns a graceful message string, not an error."""
        service = NewsReactionService()

        desc = service.get_description("XAUUSD", "MADE_UP_EVENT")

        assert isinstance(desc, str)
        assert len(desc) > 0
        # Should mention the event name
        assert "MADE_UP_EVENT" in desc

    def test_get_high_impact_pairs_returns_list(self):
        """get_high_impact_pairs returns a non-empty list for a major event."""
        service = NewsReactionService()

        pairs = service.get_high_impact_pairs("FOMC")

        assert isinstance(pairs, list)
        # FOMC should impact both pairs
        assert len(pairs) >= 1
        assert "XAUUSD" in pairs

    def test_get_high_impact_pairs_returns_empty_for_unknown(self):
        """Unknown event returns an empty list from get_high_impact_pairs."""
        service = NewsReactionService()

        pairs = service.get_high_impact_pairs("TOTALLY_FAKE_EVENT")

        assert pairs == []


# ── SignalDecay tests ─────────────────────────────────────────────────────────

class TestSignalDecay:

    def test_compute_at_zero_elapsed_returns_base_score(self):
        """At 0% elapsed, displayed_score equals base_score exactly."""
        decay = SignalDecay()
        base_score = 0.80
        # Set generated_at to exactly now so elapsed ≈ 0
        generated_at = datetime.now(timezone.utc)

        result = decay.compute(
            base_score=base_score,
            generated_at=generated_at,
            expiry_window_bars=12,
            bar_interval_minutes=60,
        )

        # Allow small floating-point tolerance for tiny elapsed time
        assert abs(result.displayed_score - base_score) < 0.01
        assert result.elapsed_fraction < 0.01
        assert not result.is_expired
        assert not result.is_fading

    def test_compute_at_50_percent_elapsed(self):
        """At 50% elapsed, displayed_score = base_score × 0.875."""
        decay = SignalDecay()
        base_score = 0.80
        # 12 bars × 60 min = 720 min total window; 50% = 360 min elapsed
        total_minutes = 12 * 60
        generated_at = datetime.now(timezone.utc) - timedelta(minutes=total_minutes * 0.5)

        result = decay.compute(
            base_score=base_score,
            generated_at=generated_at,
            expiry_window_bars=12,
            bar_interval_minutes=60,
        )

        expected = base_score * 0.875  # 0.80 × (1 - 0.25 × 0.5) = 0.80 × 0.875
        assert abs(result.displayed_score - expected) < 0.01
        assert abs(result.elapsed_fraction - 0.5) < 0.01

    def test_compute_at_100_percent_elapsed(self):
        """At 100% elapsed, displayed_score = base_score × 0.75."""
        decay = SignalDecay()
        base_score = 0.80
        # 12 bars × 60 min = 720 min total; elapsed = 720 min
        total_minutes = 12 * 60
        generated_at = datetime.now(timezone.utc) - timedelta(minutes=total_minutes)

        result = decay.compute(
            base_score=base_score,
            generated_at=generated_at,
            expiry_window_bars=12,
            bar_interval_minutes=60,
        )

        expected = base_score * 0.75  # 0.80 × (1 - 0.25 × 1.0) = 0.60
        assert abs(result.displayed_score - expected) < 0.01
        assert result.elapsed_fraction == 1.0

    def test_is_expired_when_decayed_score_below_threshold(self):
        """is_expired returns True when decayed score falls below 0.30."""
        decay = SignalDecay()
        # base_score = 0.35; at 100% decay → 0.35 × 0.75 = 0.2625 < 0.30
        base_score = 0.35
        total_minutes = 5 * 5   # 5-bar window on 5m chart = 25 min
        generated_at = datetime.now(timezone.utc) - timedelta(minutes=total_minutes + 1)

        expired = decay.is_expired(
            base_score=base_score,
            generated_at=generated_at,
            expiry_window_bars=5,
            bar_interval_minutes=5,
        )

        assert expired is True

    def test_is_expired_false_for_strong_recent_signal(self):
        """Strong signal with little elapsed time should not be expired."""
        decay = SignalDecay()

        expired = decay.is_expired(
            base_score=0.85,
            generated_at=datetime.now(timezone.utc),
            expiry_window_bars=12,
            bar_interval_minutes=60,
        )

        assert expired is False

    def test_get_expiry_bars_1m_returns_5(self):
        """1m timeframe → 5 expiry bars per CLAUDE.md §8.4."""
        decay = SignalDecay()
        assert decay.get_expiry_bars("scalping", "1m") == 5

    def test_get_expiry_bars_5m_returns_5(self):
        """5m timeframe → 5 expiry bars."""
        decay = SignalDecay()
        assert decay.get_expiry_bars("scalping", "5m") == 5

    def test_get_expiry_bars_15m_returns_8(self):
        """15m timeframe → 8 expiry bars."""
        decay = SignalDecay()
        assert decay.get_expiry_bars("day_trading", "15m") == 8

    def test_get_expiry_bars_30m_returns_8(self):
        """30m timeframe → 8 expiry bars."""
        decay = SignalDecay()
        assert decay.get_expiry_bars("day_trading", "30m") == 8

    def test_get_expiry_bars_1H_returns_12(self):
        """1H timeframe → 12 expiry bars."""
        decay = SignalDecay()
        assert decay.get_expiry_bars("swing_trading", "1H") == 12

    def test_get_expiry_bars_4H_returns_12(self):
        """4H timeframe → 12 expiry bars."""
        decay = SignalDecay()
        assert decay.get_expiry_bars("swing_trading", "4H") == 12

    def test_get_expiry_bars_1D_returns_5(self):
        """1D timeframe → 5 expiry bars."""
        decay = SignalDecay()
        assert decay.get_expiry_bars("position_trading", "1D") == 5

    def test_get_expiry_bars_1W_returns_3(self):
        """1W timeframe → 3 expiry bars."""
        decay = SignalDecay()
        assert decay.get_expiry_bars("position_trading", "1W") == 3

    def test_get_expiry_bars_raises_for_unknown_tf(self):
        """Unknown timeframe should raise ValueError."""
        decay = SignalDecay()
        with pytest.raises(ValueError, match="Unknown timeframe"):
            decay.get_expiry_bars("scalping", "2H")

    def test_decay_result_is_fading_between_030_and_050(self):
        """is_fading=True when displayed_score is between 0.30 and 0.50."""
        decay = SignalDecay()
        # base_score = 0.55; at 100% elapsed → 0.55 × 0.75 = 0.4125 → fading
        base_score = 0.55
        total_minutes = 5 * 5  # 5-bar 5m window = 25 min
        generated_at = datetime.now(timezone.utc) - timedelta(minutes=total_minutes + 1)

        result = decay.compute(
            base_score=base_score,
            generated_at=generated_at,
            expiry_window_bars=5,
            bar_interval_minutes=5,
        )

        assert result.is_fading is True
        assert 0.30 <= result.displayed_score < 0.50

    def test_decay_result_time_remaining_decreases(self):
        """time_remaining_seconds should be less than the full window when some time has elapsed."""
        decay = SignalDecay()
        total_minutes = 12 * 60  # 12-bar 1H window
        # Elapsed = 2 hours (120 minutes)
        generated_at = datetime.now(timezone.utc) - timedelta(minutes=120)

        result = decay.compute(
            base_score=0.80,
            generated_at=generated_at,
            expiry_window_bars=12,
            bar_interval_minutes=60,
        )

        assert result.time_remaining_seconds < total_minutes * 60
        assert result.time_remaining_seconds > 0  # Still has time left

    def test_score_65_at_90_percent_elapsed(self):
        """
        Verify the §5.3.1 example: 0.65 signal at 90% elapsed shows ≈ 0.50.

        Formula: 0.65 × (1 - 0.25 × 0.9) = 0.65 × 0.775 = 0.50375
        """
        decay = SignalDecay()
        base_score = 0.65
        total_minutes = 12 * 60  # 720 min
        generated_at = datetime.now(timezone.utc) - timedelta(minutes=720 * 0.9)

        result = decay.compute(
            base_score=base_score,
            generated_at=generated_at,
            expiry_window_bars=12,
            bar_interval_minutes=60,
        )

        expected = 0.65 * (1 - 0.25 * 0.9)  # = 0.50375
        assert abs(result.displayed_score - expected) < 0.01
        # Should be just above 0.50 — not fading yet
        assert not result.is_fading

    def test_score_050_at_50_percent_elapsed(self):
        """
        Verify the §5.3.1 example: 0.50 signal at 50% elapsed shows ≈ 0.44.

        Formula: 0.50 × (1 - 0.25 × 0.5) = 0.50 × 0.875 = 0.4375 → fading
        """
        decay = SignalDecay()
        base_score = 0.50
        total_minutes = 12 * 60  # 720 min
        generated_at = datetime.now(timezone.utc) - timedelta(minutes=720 * 0.5)

        result = decay.compute(
            base_score=base_score,
            generated_at=generated_at,
            expiry_window_bars=12,
            bar_interval_minutes=60,
        )

        expected = 0.50 * 0.875  # = 0.4375
        assert abs(result.displayed_score - expected) < 0.01
        assert result.is_fading is True  # Below 0.50 threshold
