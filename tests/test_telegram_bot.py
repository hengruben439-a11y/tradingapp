"""
Telegram Bot Formatter Tests — Sprint 11 deliverable.

Tests formatter functions only (bot integration tests require a live token).
All tests are pure-Python, zero network calls, zero Telegram API calls.

Covers:
    - format_signal_message: BUY/SELL direction, emoji, required fields
    - format_signal_message: price formatting for XAUUSD vs GBPJPY
    - format_daily_rundown: empty events case
    - format_daily_rundown: populated events, time conversion, impact emoji
    - format_tp_hit: TP1, TP2, TP3 level display and action hints
    - format_sl_hit: includes post-mortem text when provided
    - format_sl_hit: graceful fallback when post_mortem is absent
    - Confidence score → label mapping (Very Strong / Strong / Moderate / Weak / Neutral)
    - _confidence_label is accessible and maps all threshold boundaries correctly
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from telegram_bot.formatters import (
    _confidence_label,
    format_daily_rundown,
    format_signal_message,
    format_sl_hit,
    format_tp_hit,
)


# ─── Test fixtures ────────────────────────────────────────────────────────────

def _xau_buy_signal(**overrides) -> dict:
    """Minimal valid XAUUSD BUY signal for testing."""
    base = {
        "signal_id": "XAU_001",
        "pair": "XAUUSD",
        "direction": "BUY",
        "entry": 2341.50,
        "sl": 2328.00,
        "tp1": 2355.00,
        "tp2": 2368.00,
        "tp3": 2385.00,
        "confidence": 0.74,
        "kill_zone": "London",
        "generated_at": datetime(2026, 3, 26, 1, 15, tzinfo=timezone.utc),  # 09:15 SGT
        "timeframe": "15m",
        "lot_size": 0.15,
        "risk_usd": 100.00,
    }
    base.update(overrides)
    return base


def _gj_sell_signal(**overrides) -> dict:
    """Minimal valid GBPJPY SELL signal for testing."""
    base = {
        "signal_id": "GJ_001",
        "pair": "GBPJPY",
        "direction": "SELL",
        "entry": 192.345,
        "sl": 192.785,
        "tp1": 191.900,
        "tp2": 191.450,
        "tp3": 190.800,
        "confidence": 0.82,
        "kill_zone": "New_York",
        "generated_at": datetime(2026, 3, 26, 13, 30, tzinfo=timezone.utc),  # 21:30 SGT
        "timeframe": "1H",
        "lot_size": 0.08,
        "risk_usd": 100.00,
    }
    base.update(overrides)
    return base


def _make_events(n: int) -> list[dict]:
    """Generate n synthetic economic calendar events."""
    events = []
    base_hour = 8
    for i in range(n):
        events.append({
            "name": f"Event {i + 1}",
            "time_utc": datetime(2026, 3, 26, base_hour + i, 30, tzinfo=timezone.utc),
            "currency": "USD",
            "impact": "high" if i == 0 else ("medium" if i == 1 else "low"),
            "forecast": f"{i + 1}.2%",
            "previous": f"{i}.8%",
        })
    return events


# ─── format_signal_message ────────────────────────────────────────────────────

class TestFormatSignalMessage:
    """Tests for format_signal_message."""

    def test_buy_signal_contains_green_emoji(self):
        """BUY direction must produce the 🟢 emoji."""
        msg = format_signal_message(_xau_buy_signal())
        assert "🟢" in msg

    def test_sell_signal_contains_red_emoji(self):
        """SELL direction must produce the 🔴 emoji."""
        msg = format_signal_message(_gj_sell_signal())
        assert "🔴" in msg

    def test_buy_signal_contains_direction_label(self):
        """BUY label must appear in the header."""
        msg = format_signal_message(_xau_buy_signal())
        assert "BUY" in msg

    def test_sell_signal_contains_direction_label(self):
        """SELL label must appear in the header."""
        msg = format_signal_message(_gj_sell_signal())
        assert "SELL" in msg

    def test_pair_appears_in_header(self):
        """Pair name must appear in the formatted message."""
        msg_xau = format_signal_message(_xau_buy_signal())
        msg_gj = format_signal_message(_gj_sell_signal())
        assert "XAUUSD" in msg_xau
        assert "GBPJPY" in msg_gj

    def test_entry_price_present(self):
        """Entry price must appear in the message."""
        msg = format_signal_message(_xau_buy_signal())
        assert "2,341.50" in msg

    def test_sl_price_present(self):
        """Stop-loss price must appear in the message."""
        msg = format_signal_message(_xau_buy_signal())
        assert "2,328.00" in msg

    def test_all_three_tp_levels_present(self):
        """TP1, TP2, and TP3 must all appear in the message."""
        msg = format_signal_message(_xau_buy_signal())
        assert "2,355.00" in msg  # TP1
        assert "2,368.00" in msg  # TP2
        assert "2,385.00" in msg  # TP3

    def test_tp_close_percentages_present(self):
        """The 40%/30%/30% close percentages must be shown."""
        msg = format_signal_message(_xau_buy_signal())
        assert "40%" in msg
        assert "30%" in msg

    def test_confidence_label_in_message(self):
        """Confidence label must appear in the formatted message."""
        msg = format_signal_message(_xau_buy_signal(confidence=0.74))
        assert "Strong" in msg

    def test_kill_zone_shown(self):
        """Kill zone name must appear when provided."""
        msg = format_signal_message(_xau_buy_signal(kill_zone="London"))
        assert "London" in msg

    def test_no_kill_zone_omitted_gracefully(self):
        """Message should not error when kill_zone is None."""
        msg = format_signal_message(_xau_buy_signal(kill_zone=None))
        assert "BUY" in msg  # message still generated

    def test_timeframe_shown(self):
        """Timeframe label must appear when provided."""
        msg = format_signal_message(_xau_buy_signal(timeframe="15m"))
        assert "15m" in msg

    def test_sgt_time_conversion(self):
        """generated_at in UTC must be shown in SGT (UTC+8)."""
        # 01:15 UTC = 09:15 SGT
        signal = _xau_buy_signal(
            generated_at=datetime(2026, 3, 26, 1, 15, tzinfo=timezone.utc)
        )
        msg = format_signal_message(signal)
        assert "09:15" in msg
        assert "SGT" in msg

    def test_lot_size_and_risk_shown(self):
        """Lot size and risk USD must appear in the risk line."""
        msg = format_signal_message(_xau_buy_signal(lot_size=0.15, risk_usd=100.0))
        assert "0.15" in msg
        assert "100.00" in msg

    def test_gbpjpy_price_format_three_decimals(self):
        """GBPJPY prices must use 3 decimal places."""
        msg = format_signal_message(_gj_sell_signal())
        assert "192.345" in msg

    def test_html_bold_tags_present(self):
        """Message must contain HTML bold tags for Telegram HTML parse mode."""
        msg = format_signal_message(_xau_buy_signal())
        assert "<b>" in msg and "</b>" in msg

    def test_html_code_tags_on_prices(self):
        """Prices must be wrapped in <code> tags."""
        msg = format_signal_message(_xau_buy_signal())
        assert "<code>" in msg


# ─── BUY vs SELL direction ────────────────────────────────────────────────────

class TestBuySellDirectionFormatting:
    """Explicit direction-specific formatting checks."""

    def test_buy_does_not_contain_red_emoji(self):
        """BUY signal must NOT produce the 🔴 emoji in the header area."""
        msg = format_signal_message(_xau_buy_signal())
        # The header line is the first line; 🔴 should not be there
        first_line = msg.splitlines()[0]
        assert "🔴" not in first_line

    def test_sell_does_not_contain_green_emoji_in_header(self):
        """SELL signal must NOT produce the 🟢 emoji in the header area."""
        msg = format_signal_message(_gj_sell_signal())
        first_line = msg.splitlines()[0]
        assert "🟢" not in first_line

    def test_direction_case_insensitive_buy(self):
        """Lowercase 'buy' direction should still produce a valid message."""
        msg = format_signal_message(_xau_buy_signal(direction="buy"))
        assert "🟢" in msg
        assert "BUY" in msg

    def test_direction_case_insensitive_sell(self):
        """Lowercase 'sell' direction should still produce a valid message."""
        msg = format_signal_message(_gj_sell_signal(direction="sell"))
        assert "🔴" in msg
        assert "SELL" in msg


# ─── format_daily_rundown ─────────────────────────────────────────────────────

class TestFormatDailyRundown:
    """Tests for format_daily_rundown."""

    def test_empty_events_returns_no_events_message(self):
        """Empty event list must produce a 'no events' message."""
        msg = format_daily_rundown([], "Thursday 26 Mar 2026")
        assert "No high-impact events" in msg

    def test_empty_events_contains_date(self):
        """Date string must appear even with no events."""
        msg = format_daily_rundown([], "Thursday 26 Mar 2026")
        assert "Thursday 26 Mar 2026" in msg

    def test_three_events_all_shown(self):
        """All 3 events must appear by name."""
        events = _make_events(3)
        msg = format_daily_rundown(events, "Thursday 26 Mar 2026")
        assert "Event 1" in msg
        assert "Event 2" in msg
        assert "Event 3" in msg

    def test_high_impact_emoji_present(self):
        """High-impact events must use the 🔴 emoji."""
        events = _make_events(1)  # first event is always high
        msg = format_daily_rundown(events, "26 Mar 2026")
        assert "🔴" in msg

    def test_sgt_time_in_rundown(self):
        """Event times must be converted from UTC to SGT."""
        # 08:30 UTC = 16:30 SGT
        events = [
            {
                "name": "CPI",
                "time_utc": datetime(2026, 3, 26, 8, 30, tzinfo=timezone.utc),
                "currency": "USD",
                "impact": "high",
            }
        ]
        msg = format_daily_rundown(events, "26 Mar 2026")
        assert "16:30" in msg
        assert "SGT" in msg

    def test_forecast_and_previous_shown(self):
        """Forecast and previous values must appear for events that have them."""
        events = _make_events(1)
        msg = format_daily_rundown(events, "26 Mar 2026")
        assert "Forecast" in msg
        assert "Prev" in msg

    def test_signal_suppression_notice_present(self):
        """The signal-suppression disclaimer must appear in populated rundowns."""
        events = _make_events(2)
        msg = format_daily_rundown(events, "26 Mar 2026")
        assert "suppressed" in msg.lower()

    def test_date_header_present(self):
        """Daily Rundown header must contain the supplied date."""
        msg = format_daily_rundown([], "Monday 30 Mar 2026")
        assert "Monday 30 Mar 2026" in msg


# ─── format_tp_hit ────────────────────────────────────────────────────────────

class TestFormatTpHit:
    """Tests for format_tp_hit."""

    def test_tp1_hit_contains_tp1_label(self):
        """TP1 notification must label itself TP1."""
        msg = format_tp_hit(_xau_buy_signal(), "TP1")
        assert "TP1" in msg

    def test_tp2_hit_contains_tp2_label(self):
        """TP2 notification must label itself TP2."""
        msg = format_tp_hit(_xau_buy_signal(), "TP2")
        assert "TP2" in msg

    def test_tp3_hit_contains_tp3_label(self):
        """TP3 notification must label itself TP3."""
        msg = format_tp_hit(_xau_buy_signal(), "TP3")
        assert "TP3" in msg

    def test_tp1_suggests_move_sl_to_be(self):
        """TP1 hit must suggest moving SL to breakeven."""
        msg = format_tp_hit(_xau_buy_signal(), "TP1")
        assert "breakeven" in msg.lower() or "BE" in msg

    def test_tp2_mentions_trail_or_tp1(self):
        """TP2 hit must reference trailing SL or TP1."""
        msg = format_tp_hit(_xau_buy_signal(), "TP2")
        # Either "trail" or "TP1" should appear to indicate next action
        assert "trail" in msg.lower() or "TP1" in msg

    def test_tp3_full_close_message(self):
        """TP3 hit must indicate full target reached."""
        msg = format_tp_hit(_xau_buy_signal(), "TP3")
        assert "full" in msg.lower() or "target" in msg.lower()

    def test_tp1_price_shown(self):
        """The TP1 price value must appear in the TP1 notification."""
        msg = format_tp_hit(_xau_buy_signal(), "TP1")
        assert "2,355.00" in msg

    def test_tp_level_case_insensitive(self):
        """Lowercase 'tp1' should produce the same result as 'TP1'."""
        msg_upper = format_tp_hit(_xau_buy_signal(), "TP1")
        msg_lower = format_tp_hit(_xau_buy_signal(), "tp1")
        assert "TP1" in msg_upper
        assert "TP1" in msg_lower

    def test_pair_name_in_tp_notification(self):
        """Pair name must appear in the TP hit notification."""
        msg = format_tp_hit(_xau_buy_signal(), "TP1")
        assert "XAUUSD" in msg


# ─── format_sl_hit ────────────────────────────────────────────────────────────

class TestFormatSlHit:
    """Tests for format_sl_hit."""

    def test_sl_hit_contains_stop_loss_label(self):
        """SL hit message must contain a stop-loss label."""
        msg = format_sl_hit(_xau_buy_signal())
        assert "STOP" in msg.upper() or "SL" in msg

    def test_sl_hit_contains_pair(self):
        """Pair name must appear in the SL hit message."""
        msg = format_sl_hit(_xau_buy_signal())
        assert "XAUUSD" in msg

    def test_sl_hit_with_post_mortem_shows_module(self):
        """When post_mortem is present, the failed module name must appear."""
        signal = _xau_buy_signal(
            post_mortem={
                "module_failed": "Order Block",
                "what_happened": "Price swept through the OB zone.",
                "lesson": "Verify OB is unmitigated before entry.",
            }
        )
        msg = format_sl_hit(signal)
        assert "Order Block" in msg

    def test_sl_hit_with_post_mortem_shows_lesson(self):
        """When post_mortem is present, the lesson text must appear."""
        lesson = "Verify OB is unmitigated before entry."
        signal = _xau_buy_signal(
            post_mortem={
                "module_failed": "Order Block",
                "what_happened": "Price swept through the OB zone.",
                "lesson": lesson,
            }
        )
        msg = format_sl_hit(signal)
        assert lesson in msg

    def test_sl_hit_without_post_mortem_does_not_crash(self):
        """Missing post_mortem must not raise an exception."""
        signal = _xau_buy_signal()
        signal.pop("post_mortem", None)
        msg = format_sl_hit(signal)
        assert "STOP" in msg.upper() or "SL" in msg

    def test_sl_hit_fallback_text_when_no_post_mortem(self):
        """Without post_mortem, a generic fallback message must still appear."""
        signal = _xau_buy_signal()
        msg = format_sl_hit(signal)
        # Should have some instructional text
        assert "journal" in msg.lower() or "app" in msg.lower() or "review" in msg.lower()

    def test_sl_hit_entry_price_shown(self):
        """Entry price must appear in the SL hit message."""
        msg = format_sl_hit(_xau_buy_signal())
        assert "2,341.50" in msg

    def test_sl_hit_sl_price_shown(self):
        """SL price must appear in the SL hit message."""
        msg = format_sl_hit(_xau_buy_signal())
        assert "2,328.00" in msg


# ─── Confidence score → label mapping ────────────────────────────────────────

class TestConfidenceLabelMapping:
    """Tests for _confidence_label threshold boundary behaviour."""

    def test_score_0_80_is_very_strong(self):
        """Score exactly at 0.80 must map to 'Very Strong'."""
        assert _confidence_label(0.80) == "Very Strong"

    def test_score_0_95_is_very_strong(self):
        """Score above 0.80 must map to 'Very Strong'."""
        assert _confidence_label(0.95) == "Very Strong"

    def test_score_1_00_is_very_strong(self):
        """Maximum score 1.00 must map to 'Very Strong'."""
        assert _confidence_label(1.00) == "Very Strong"

    def test_score_0_65_is_strong(self):
        """Score exactly at 0.65 must map to 'Strong'."""
        assert _confidence_label(0.65) == "Strong"

    def test_score_0_79_is_strong(self):
        """Score between 0.65 and 0.80 must map to 'Strong'."""
        assert _confidence_label(0.79) == "Strong"

    def test_score_0_50_is_moderate(self):
        """Score exactly at 0.50 must map to 'Moderate'."""
        assert _confidence_label(0.50) == "Moderate"

    def test_score_0_64_is_moderate(self):
        """Score between 0.50 and 0.65 must map to 'Moderate'."""
        assert _confidence_label(0.64) == "Moderate"

    def test_score_0_30_is_weak(self):
        """Score exactly at 0.30 must map to 'Weak'."""
        assert _confidence_label(0.30) == "Weak"

    def test_score_0_49_is_weak(self):
        """Score between 0.30 and 0.50 must map to 'Weak'."""
        assert _confidence_label(0.49) == "Weak"

    def test_score_0_29_is_neutral(self):
        """Score below 0.30 must map to 'Neutral'."""
        assert _confidence_label(0.29) == "Neutral"

    def test_score_0_00_is_neutral(self):
        """Zero score must map to 'Neutral'."""
        assert _confidence_label(0.0) == "Neutral"

    def test_negative_score_uses_absolute_value(self):
        """Negative scores (SELL direction) must use absolute value for label mapping."""
        assert _confidence_label(-0.80) == "Very Strong"
        assert _confidence_label(-0.65) == "Strong"
        assert _confidence_label(-0.50) == "Moderate"
