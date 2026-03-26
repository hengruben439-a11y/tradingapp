"""
Kill Zone Module Tests — Sprint 5 deliverable.

Covers:
    - Outside-all-KZ penalty score and multiplier
    - Each Kill Zone active in its correct UTC time window
    - Pair-specific applicability (Asian → GBPJPY only, Shanghai_Open → XAUUSD only)
    - London and New_York active for both pairs
    - London_Close counter-trend scoring
    - Overlap resolution: NY wins over London_Close (15:00–16:00)
    - Overlap resolution: Shanghai_Open wins over Asian (00:15–02:00) for XAUUSD
    - Boundary edge cases (exact start/end times)
    - Naive datetime treated as UTC
    - Multiplier values: 1.05 active, 0.95 inactive
    - active_kz_name property
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from engine.modules.kill_zones import KillZoneModule, KZ_ACTIVE_MULTIPLIER, KZ_OUTSIDE_MULTIPLIER


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_utc(hour: int, minute: int = 0) -> datetime:
    """Create a UTC-aware datetime on a fixed date."""
    return datetime(2024, 1, 15, hour, minute, tzinfo=timezone.utc)


def make_naive(hour: int, minute: int = 0) -> datetime:
    """Create a naive datetime (no tzinfo) — should be treated as UTC."""
    return datetime(2024, 1, 15, hour, minute)


# ─── Outside all Kill Zones ───────────────────────────────────────────────────

class TestOutsideAllKillZones:
    """Times that fall outside every KZ window for both pairs."""

    def test_outside_kz_bullish_returns_negative_penalty(self):
        """Outside all KZs with bullish trend: score = -0.3."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(5, 0))   # 05:00 UTC — between Asian and London
        assert module.score(is_bullish_trend=True) == pytest.approx(-0.3)

    def test_outside_kz_bearish_returns_positive_penalty(self):
        """Outside all KZs with bearish trend: score = +0.3 (counter-penalty)."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(5, 0))
        assert module.score(is_bullish_trend=False) == pytest.approx(0.3)

    def test_outside_kz_multiplier_is_0_95(self):
        """Multiplier when no KZ is active should be 0.95."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(5, 0))
        assert module.get_multiplier() == pytest.approx(KZ_OUTSIDE_MULTIPLIER)

    def test_outside_kz_active_kz_name_is_none(self):
        """active_kz_name should return None when no KZ is active."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(5, 0))
        assert module.active_kz_name is None

    def test_midday_gap_no_kz_xauusd(self):
        """11:00 UTC is between London Close end and NY start — no KZ active."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(11, 0))
        assert module.active_kz_name is None
        assert module.score(is_bullish_trend=True) == pytest.approx(-0.3)

    def test_late_night_no_kz_gbpjpy(self):
        """22:00 UTC — no KZ active for GBPJPY."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(22, 0))
        assert module.active_kz_name is None

    def test_after_london_close_no_kz(self):
        """17:00 UTC — London_Close ends at 17:00 (exclusive), so 17:00 is outside."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(17, 0))
        assert module.active_kz_name is None


# ─── Asian Kill Zone (GBPJPY only, 00:00–02:00 UTC) ─────────────────────────

class TestAsianKillZone:
    """Asian KZ applies to GBPJPY only, 00:00–02:00 UTC."""

    def test_asian_active_gbpjpy_at_00_30(self):
        """Asian KZ active for GBPJPY at 00:30 UTC."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(0, 30))
        assert module.active_kz_name == "Asian"

    def test_asian_bullish_score_gbpjpy(self):
        """Asian KZ with bullish trend on GBPJPY: +0.3."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(1, 0))
        assert module.score(is_bullish_trend=True) == pytest.approx(0.3)

    def test_asian_bearish_score_gbpjpy(self):
        """Asian KZ with bearish trend on GBPJPY: -0.3."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(1, 0))
        assert module.score(is_bullish_trend=False) == pytest.approx(-0.3)

    def test_asian_not_active_for_xauusd(self):
        """Asian KZ should NOT apply to XAUUSD — 01:00 UTC returns None (or Shanghai) for XAUUSD."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(1, 0))
        # For XAUUSD at 01:00 UTC, Shanghai_Open (00:15–02:15) should win
        assert module.active_kz_name != "Asian"

    def test_asian_boundary_exact_start_gbpjpy(self):
        """Exact 00:00 UTC — Asian KZ starts at 00:00, should be active for GBPJPY."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(0, 0))
        assert module.active_kz_name == "Asian"

    def test_asian_boundary_exact_end_gbpjpy(self):
        """Exact 02:00 UTC — Asian KZ ends at 02:00 (exclusive), not active."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(2, 0))
        assert module.active_kz_name != "Asian"

    def test_asian_multiplier_active(self):
        """Multiplier should be 1.05 when Asian KZ is active."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(1, 0))
        assert module.get_multiplier() == pytest.approx(KZ_ACTIVE_MULTIPLIER)


# ─── Shanghai Open Kill Zone (XAUUSD only, 00:15–02:15 UTC) ─────────────────

class TestShanghaiOpenKillZone:
    """Shanghai_Open KZ applies to XAUUSD only, 00:15–02:15 UTC."""

    def test_shanghai_active_xauusd_at_01_00(self):
        """Shanghai_Open active for XAUUSD at 01:00 UTC."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(1, 0))
        assert module.active_kz_name == "Shanghai_Open"

    def test_shanghai_bullish_score_xauusd(self):
        """Shanghai_Open with bullish trend: +0.6."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(1, 0))
        assert module.score(is_bullish_trend=True) == pytest.approx(0.6)

    def test_shanghai_bearish_score_xauusd(self):
        """Shanghai_Open with bearish trend: -0.6."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(1, 0))
        assert module.score(is_bullish_trend=False) == pytest.approx(-0.6)

    def test_shanghai_not_active_for_gbpjpy(self):
        """Shanghai_Open should NOT apply to GBPJPY."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(1, 0))
        # At 01:00 UTC, GBPJPY should be in Asian KZ, not Shanghai_Open
        assert module.active_kz_name != "Shanghai_Open"

    def test_shanghai_boundary_exact_start(self):
        """Exact 00:15 UTC — Shanghai_Open KZ starts here, should be active for XAUUSD."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(0, 15))
        assert module.active_kz_name == "Shanghai_Open"

    def test_shanghai_boundary_exact_end(self):
        """Exact 02:15 UTC — Shanghai_Open ends at 02:15 (exclusive), not active."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(2, 15))
        assert module.active_kz_name != "Shanghai_Open"

    def test_shanghai_beats_asian_in_overlap_for_xauusd(self):
        """00:15–02:00 UTC: Shanghai_Open (score 0.6) beats Asian (score 0.3) for XAUUSD."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(0, 30))   # overlap window
        assert module.active_kz_name == "Shanghai_Open"

    def test_before_shanghai_start_no_kz_xauusd(self):
        """00:05 UTC — before Shanghai_Open starts and Asian doesn't apply to XAUUSD."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(0, 5))
        assert module.active_kz_name is None

    def test_shanghai_multiplier_active(self):
        """Multiplier should be 1.05 during Shanghai_Open for XAUUSD."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(1, 0))
        assert module.get_multiplier() == pytest.approx(KZ_ACTIVE_MULTIPLIER)


# ─── London Kill Zone (ALL pairs, 07:00–10:00 UTC) ───────────────────────────

class TestLondonKillZone:
    """London KZ applies to both XAUUSD and GBPJPY, 07:00–10:00 UTC."""

    def test_london_active_xauusd(self):
        """London KZ active for XAUUSD at 08:00 UTC."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(8, 0))
        assert module.active_kz_name == "London"

    def test_london_active_gbpjpy(self):
        """London KZ active for GBPJPY at 08:00 UTC."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(8, 0))
        assert module.active_kz_name == "London"

    def test_london_bullish_score(self):
        """London KZ with bullish trend: +0.8."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(8, 0))
        assert module.score(is_bullish_trend=True) == pytest.approx(0.8)

    def test_london_bearish_score(self):
        """London KZ with bearish trend: -0.8."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(8, 0))
        assert module.score(is_bullish_trend=False) == pytest.approx(-0.8)

    def test_london_boundary_exact_start(self):
        """Exact 07:00 UTC — London KZ starts here."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(7, 0))
        assert module.active_kz_name == "London"

    def test_london_boundary_exact_end(self):
        """Exact 10:00 UTC — London KZ ends at 10:00 (exclusive)."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(10, 0))
        assert module.active_kz_name != "London"

    def test_london_multiplier_active(self):
        """Multiplier should be 1.05 during London KZ."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(9, 0))
        assert module.get_multiplier() == pytest.approx(KZ_ACTIVE_MULTIPLIER)


# ─── New York Kill Zone (ALL pairs, 13:00–16:00 UTC) ─────────────────────────

class TestNewYorkKillZone:
    """New_York KZ applies to both pairs, 13:00–16:00 UTC. Highest score = 1.0."""

    def test_ny_active_xauusd(self):
        """New_York KZ active for XAUUSD at 14:00 UTC."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(14, 0))
        assert module.active_kz_name == "New_York"

    def test_ny_active_gbpjpy(self):
        """New_York KZ active for GBPJPY at 14:00 UTC."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(14, 0))
        assert module.active_kz_name == "New_York"

    def test_ny_bullish_score(self):
        """New_York KZ with bullish trend: +1.0."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(14, 0))
        assert module.score(is_bullish_trend=True) == pytest.approx(1.0)

    def test_ny_bearish_score(self):
        """New_York KZ with bearish trend: -1.0."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(14, 0))
        assert module.score(is_bullish_trend=False) == pytest.approx(-1.0)

    def test_ny_boundary_exact_start(self):
        """Exact 13:00 UTC — New_York KZ starts here."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(13, 0))
        assert module.active_kz_name == "New_York"

    def test_ny_boundary_exact_end(self):
        """Exact 16:00 UTC — New_York KZ ends at 16:00 (exclusive)."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(16, 0))
        assert module.active_kz_name != "New_York"

    def test_ny_beats_london_close_in_overlap(self):
        """15:00–16:00 UTC: NY (score 1.0) beats London_Close (score 0.5)."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(15, 30))
        assert module.active_kz_name == "New_York"

    def test_ny_beats_london_close_at_15_00(self):
        """Exact 15:00 UTC start of overlap: NY wins."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(15, 0))
        assert module.active_kz_name == "New_York"

    def test_ny_multiplier_active(self):
        """Multiplier should be 1.05 during New_York KZ."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(14, 0))
        assert module.get_multiplier() == pytest.approx(KZ_ACTIVE_MULTIPLIER)


# ─── London Close Kill Zone (ALL pairs, 15:00–17:00 UTC, counter-trend) ──────

class TestLondonCloseKillZone:
    """London_Close KZ is counter-trend (retracement). Active after NY ends (16:00–17:00)."""

    def test_london_close_active_post_ny(self):
        """London_Close active at 16:30 UTC (after NY ends at 16:00)."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(16, 30))
        assert module.active_kz_name == "London_Close"

    def test_london_close_counter_trend_bullish(self):
        """London_Close with bullish trend: -0.5 (counter-trend retracement)."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(16, 30))
        assert module.score(is_bullish_trend=True) == pytest.approx(-0.5)

    def test_london_close_counter_trend_bearish(self):
        """London_Close with bearish trend: +0.5 (counter-trend = buy retracement)."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(16, 30))
        assert module.score(is_bullish_trend=False) == pytest.approx(0.5)

    def test_london_close_active_gbpjpy(self):
        """London_Close applies to GBPJPY too."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_utc(16, 0))
        assert module.active_kz_name == "London_Close"

    def test_london_close_boundary_not_active_before_start(self):
        """14:59 UTC — before London_Close starts, NY should be active instead."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(14, 59))
        assert module.active_kz_name != "London_Close"

    def test_london_close_multiplier_active(self):
        """Multiplier should be 1.05 during London_Close (it IS a KZ, even counter-trend)."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_utc(16, 30))
        assert module.get_multiplier() == pytest.approx(KZ_ACTIVE_MULTIPLIER)


# ─── Naive Datetime Handling ──────────────────────────────────────────────────

class TestNaiveDatetime:
    """Naive datetimes (no tzinfo) should be treated as UTC."""

    def test_naive_datetime_in_london_window(self):
        """Naive datetime at 08:00 treated as 08:00 UTC — London KZ active."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_naive(8, 0))
        assert module.active_kz_name == "London"

    def test_naive_datetime_in_ny_window(self):
        """Naive datetime at 14:00 treated as 14:00 UTC — New_York KZ active."""
        module = KillZoneModule(pair="GBPJPY")
        module.update_bar(make_naive(14, 0))
        assert module.active_kz_name == "New_York"

    def test_naive_datetime_outside_all_kzs(self):
        """Naive datetime at 05:00 — outside all KZs, returns penalty score."""
        module = KillZoneModule(pair="XAUUSD")
        module.update_bar(make_naive(5, 0))
        assert module.active_kz_name is None
        assert module.score(is_bullish_trend=True) == pytest.approx(-0.3)


# ─── State Before First update_bar Call ──────────────────────────────────────

class TestInitialState:
    """Module state before update_bar is called."""

    def test_no_active_kz_before_update(self):
        """Before any bar update, active_kz_name should be None."""
        module = KillZoneModule(pair="XAUUSD")
        assert module.active_kz_name is None

    def test_multiplier_outside_before_update(self):
        """Before any bar update, multiplier should be 0.95 (no active KZ)."""
        module = KillZoneModule(pair="XAUUSD")
        assert module.get_multiplier() == pytest.approx(KZ_OUTSIDE_MULTIPLIER)


# ─── Multiplier Constant Values ───────────────────────────────────────────────

class TestMultiplierConstants:
    """Verify the exported constant values are correct per PRD §5.2."""

    def test_active_multiplier_value(self):
        assert KZ_ACTIVE_MULTIPLIER == pytest.approx(1.05)

    def test_outside_multiplier_value(self):
        assert KZ_OUTSIDE_MULTIPLIER == pytest.approx(0.95)
