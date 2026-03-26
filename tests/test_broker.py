"""
Broker integration tests — Sprint 13 deliverable.

Tests cover:
    - MetaApiClient.is_price_within_validity
    - ExecutionManager._pip_value for XAUUSD and GBPJPY
    - ExecutionManager._sl_pips calculation
    - RiskGuards.can_trade (daily risk, max signals, passing state)
    - RiskGuards.record_trade_result (daily risk increment)
    - RiskGuards.get_effective_risk_pct (adaptive scaling and recovery mode)
    - CorrelationEngine.check_new_signal (macro conflict and no-conflict)
    - CorrelationEngine.get_net_exposure (USD calculation)
    - Context-aware cooldown: pattern suppression, news-attributed, rolling loss rate

All tests mock MetaApi HTTP — no real network calls are made.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from broker.correlation import CorrelationEngine, CorrelationWarning
from broker.execution import ExecutionManager
from broker.metaapi import MetaApiClient, OrderRequest, OrderResult
from broker.risk_guards import RiskGuards, _pattern_key


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_execution_manager(
    risk_pct: float = 1.0,
    redis=None,
) -> tuple[ExecutionManager, MagicMock]:
    """Return an ExecutionManager with a mocked MetaApiClient."""
    mock_api = MagicMock(spec=MetaApiClient)
    manager = ExecutionManager(mock_api, redis, risk_pct=risk_pct)
    return manager, mock_api


def _make_signal(
    pair: str = "XAUUSD",
    direction: str = "BUY",
    entry: float = 2350.0,
    sl: float = 2330.0,
    tp1: float = 2370.0,
    tp2: float = 2390.0,
    tp3: float = 2420.0,
    atr: float = 15.0,
    current_price: float = 2350.5,
) -> dict:
    return {
        "signal_id": "test-signal-001",
        "pair": pair,
        "direction": direction,
        "entry_price": entry,
        "stop_loss": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "atr": atr,
        "current_price": current_price,
    }


def _make_account_info(balance: float = 10_000.0) -> MagicMock:
    info = MagicMock()
    info.balance = balance
    info.equity = balance * 1.02
    return info


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
# MetaApiClient.is_price_within_validity
# ══════════════════════════════════════════════════════════════════════════════


class TestIsPriceWithinValidity:
    def test_price_exactly_at_entry_is_valid(self):
        assert MetaApiClient.is_price_within_validity(
            signal_entry=2350.0,
            current_price=2350.0,
            atr=15.0,
            tolerance=0.5,
        )

    def test_price_within_tolerance_is_valid(self):
        # Tolerance = 0.5 × 15 = 7.5 → price within ±7.5 is valid
        assert MetaApiClient.is_price_within_validity(
            signal_entry=2350.0,
            current_price=2355.0,  # 5 pips away — within 7.5
            atr=15.0,
            tolerance=0.5,
        )

    def test_price_on_boundary_is_valid(self):
        # Exactly at tolerance boundary (7.5 away) → still valid (<=)
        assert MetaApiClient.is_price_within_validity(
            signal_entry=2350.0,
            current_price=2357.5,
            atr=15.0,
            tolerance=0.5,
        )

    def test_price_beyond_tolerance_is_invalid(self):
        # 8.0 away > 7.5 tolerance → invalid
        assert not MetaApiClient.is_price_within_validity(
            signal_entry=2350.0,
            current_price=2358.0,
            atr=15.0,
            tolerance=0.5,
        )

    def test_price_below_entry_beyond_tolerance_is_invalid(self):
        assert not MetaApiClient.is_price_within_validity(
            signal_entry=2350.0,
            current_price=2340.0,   # 10 away > 7.5
            atr=15.0,
            tolerance=0.5,
        )

    def test_zero_atr_returns_false(self):
        assert not MetaApiClient.is_price_within_validity(
            signal_entry=2350.0,
            current_price=2350.0,
            atr=0.0,
        )

    def test_gbpjpy_within_validity(self):
        # GBPJPY: entry=195.50, ATR=0.50, tolerance=0.5 → max deviation=0.25
        assert MetaApiClient.is_price_within_validity(
            signal_entry=195.50,
            current_price=195.65,
            atr=0.50,
            tolerance=0.5,
        )

    def test_gbpjpy_outside_validity(self):
        assert not MetaApiClient.is_price_within_validity(
            signal_entry=195.50,
            current_price=195.80,   # 0.30 away > 0.25
            atr=0.50,
            tolerance=0.5,
        )


# ══════════════════════════════════════════════════════════════════════════════
# ExecutionManager._pip_value
# ══════════════════════════════════════════════════════════════════════════════


class TestPipValue:
    def test_xauusd_pip_value_one_lot(self):
        # $1.00 per pip per standard lot
        assert ExecutionManager._pip_value("XAUUSD", 1.0) == pytest.approx(1.0)

    def test_xauusd_pip_value_two_lots(self):
        assert ExecutionManager._pip_value("XAUUSD", 2.0) == pytest.approx(2.0)

    def test_gbpjpy_pip_value_one_lot(self):
        # $9.50 per pip per standard lot (static fallback)
        assert ExecutionManager._pip_value("GBPJPY", 1.0) == pytest.approx(9.50)

    def test_gbpjpy_pip_value_half_lot(self):
        assert ExecutionManager._pip_value("GBPJPY", 0.5) == pytest.approx(4.75)

    def test_unknown_symbol_fallback(self):
        # Generic forex: $10 per pip per lot
        assert ExecutionManager._pip_value("EURUSD", 1.0) == pytest.approx(10.0)


# ══════════════════════════════════════════════════════════════════════════════
# ExecutionManager._sl_pips
# ══════════════════════════════════════════════════════════════════════════════


class TestSlPips:
    def test_xauusd_sl_pips(self):
        # Entry 2350.0, SL 2330.0 → 20 pips (pip size = 0.1)
        pips = ExecutionManager._sl_pips(2350.0, 2330.0, "XAUUSD")
        assert pips == pytest.approx(200.0)   # |2350 - 2330| / 0.1

    def test_xauusd_sl_pips_sell(self):
        # Sell trade: entry 2350, SL 2370 → still 200 pips (abs)
        pips = ExecutionManager._sl_pips(2350.0, 2370.0, "XAUUSD")
        assert pips == pytest.approx(200.0)

    def test_gbpjpy_sl_pips(self):
        # Entry 195.50, SL 195.00 → 50 pips (pip size = 0.01)
        pips = ExecutionManager._sl_pips(195.50, 195.00, "GBPJPY")
        assert pips == pytest.approx(50.0)

    def test_gbpjpy_sl_pips_small(self):
        pips = ExecutionManager._sl_pips(195.50, 195.30, "GBPJPY")
        assert pips == pytest.approx(20.0)

    def test_zero_sl_distance(self):
        pips = ExecutionManager._sl_pips(2350.0, 2350.0, "XAUUSD")
        assert pips == pytest.approx(0.0)


# ══════════════════════════════════════════════════════════════════════════════
# RiskGuards.can_trade
# ══════════════════════════════════════════════════════════════════════════════


class TestRiskGuardsCanTrade:
    def setup_method(self):
        self.guards = RiskGuards(initial_equity_peak=10_000.0)

    def test_allows_trade_under_all_limits(self):
        allowed, reason = self.guards.can_trade("XAUUSD", 1.0, news_flag=False)
        assert allowed is True
        assert reason == "ok"

    def test_blocks_when_daily_risk_exceeded(self):
        # Use 3% to hit the 3% daily limit
        self.guards.daily_risk_used = 3.0
        allowed, reason = self.guards.can_trade("XAUUSD", 0.1, news_flag=False)
        assert allowed is False
        assert "Daily risk limit" in reason

    def test_blocks_when_daily_risk_would_be_exceeded(self):
        self.guards.daily_risk_used = 2.5
        allowed, reason = self.guards.can_trade("XAUUSD", 1.0, news_flag=False)
        assert allowed is False
        assert "Daily risk limit" in reason

    def test_allows_when_just_under_daily_limit(self):
        self.guards.daily_risk_used = 2.0
        allowed, reason = self.guards.can_trade("XAUUSD", 1.0, news_flag=False)
        assert allowed is True

    def test_blocks_when_max_simultaneous_reached(self):
        self.guards._active_counts["XAUUSD"] = 3
        allowed, reason = self.guards.can_trade("XAUUSD", 1.0, news_flag=False)
        assert allowed is False
        assert "Max simultaneous signals" in reason

    def test_allows_when_under_max_simultaneous(self):
        self.guards._active_counts["XAUUSD"] = 2
        allowed, reason = self.guards.can_trade("XAUUSD", 1.0, news_flag=False)
        assert allowed is True

    def test_blocks_weekly_drawdown(self):
        self.guards.weekly_drawdown = 6.0
        allowed, reason = self.guards.can_trade("XAUUSD", 1.0, news_flag=False)
        assert allowed is False
        assert "Weekly drawdown" in reason

    def test_blocks_monthly_drawdown_recovery_mode(self):
        self.guards.monthly_drawdown = 10.0
        allowed, reason = self.guards.can_trade("XAUUSD", 1.0, news_flag=False)
        assert allowed is False
        assert "Recovery Mode" in reason

    def test_blocks_during_cooldown(self):
        self.guards._full_cooldown_until = _utcnow() + timedelta(hours=2)
        allowed, reason = self.guards.can_trade("XAUUSD", 1.0, news_flag=False)
        assert allowed is False
        assert "Cooldown active" in reason

    def test_gbpjpy_limit_independent_from_xauusd(self):
        # XAUUSD at max, GBPJPY should still be allowed
        self.guards._active_counts["XAUUSD"] = 3
        allowed, reason = self.guards.can_trade("GBPJPY", 1.0, news_flag=False)
        assert allowed is True


# ══════════════════════════════════════════════════════════════════════════════
# RiskGuards.record_trade_result — daily risk tracking
# ══════════════════════════════════════════════════════════════════════════════


class TestRiskGuardsRecordResult:
    def setup_method(self):
        self.guards = RiskGuards(initial_equity_peak=10_000.0)

    def test_record_signal_open_increments_daily_risk(self):
        self.guards.record_signal_open("XAUUSD", 1.0)
        assert self.guards.daily_risk_used == pytest.approx(1.0)

    def test_record_multiple_opens_accumulate(self):
        self.guards.record_signal_open("XAUUSD", 1.0)
        self.guards.record_signal_open("GBPJPY", 0.5)
        assert self.guards.daily_risk_used == pytest.approx(1.5)

    def test_record_trade_result_decrements_active_count(self):
        self.guards._active_counts["XAUUSD"] = 2
        self.guards.record_trade_result("s1", "XAUUSD", "win", 0.01, "London", "OB", False)
        assert self.guards._active_counts["XAUUSD"] == 1

    def test_record_loss_increments_drawdown(self):
        self.guards.record_trade_result("s1", "XAUUSD", "loss", -0.01, "London", "OB", False)
        assert self.guards.weekly_drawdown == pytest.approx(1.0)
        assert self.guards.monthly_drawdown == pytest.approx(1.0)

    def test_record_win_does_not_increase_drawdown(self):
        self.guards.record_trade_result("s1", "XAUUSD", "win", 0.02, "London", "OB", False)
        assert self.guards.weekly_drawdown == 0.0
        assert self.guards.monthly_drawdown == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# RiskGuards.get_effective_risk_pct
# ══════════════════════════════════════════════════════════════════════════════


class TestGetEffectiveRiskPct:
    def setup_method(self):
        self.guards = RiskGuards(initial_equity_peak=10_000.0)

    def test_returns_base_risk_when_no_drawdown(self):
        assert self.guards.get_effective_risk_pct(1.0) == pytest.approx(1.0)

    def test_halves_risk_at_5pct_drawdown(self):
        self.guards.monthly_drawdown = 5.0   # >= 5% threshold
        result = self.guards.get_effective_risk_pct(1.0)
        assert result == pytest.approx(0.5)

    def test_halves_risk_at_above_5pct_drawdown(self):
        self.guards.monthly_drawdown = 7.5
        result = self.guards.get_effective_risk_pct(2.0)
        assert result == pytest.approx(1.0)

    def test_caps_at_0_5_pct_in_recovery_mode(self):
        self.guards.monthly_drawdown = 10.0   # Recovery mode threshold
        result = self.guards.get_effective_risk_pct(1.0)
        assert result == pytest.approx(0.5)

    def test_recovery_mode_overrides_halving(self):
        # Even if base_risk is 2%, recovery mode caps at 0.5%
        self.guards.monthly_drawdown = 12.0
        result = self.guards.get_effective_risk_pct(2.0)
        assert result == pytest.approx(0.5)

    def test_is_in_recovery_mode_false_below_10(self):
        self.guards.monthly_drawdown = 9.9
        assert self.guards.is_in_recovery_mode() is False

    def test_is_in_recovery_mode_true_at_10(self):
        self.guards.monthly_drawdown = 10.0
        assert self.guards.is_in_recovery_mode() is True


# ══════════════════════════════════════════════════════════════════════════════
# CorrelationEngine.check_new_signal
# ══════════════════════════════════════════════════════════════════════════════


class TestCorrelationEngineCheckNewSignal:
    def setup_method(self):
        self.engine = CorrelationEngine()

    def _xau_active(self, direction="BUY"):
        return {
            "pair": "XAUUSD",
            "direction": direction,
            "lot_size": 0.10,
            "sl_pips": 200.0,
        }

    def _gj_active(self, direction="BUY"):
        return {
            "pair": "GBPJPY",
            "direction": direction,
            "lot_size": 0.10,
            "sl_pips": 50.0,
        }

    def test_xauusd_buy_plus_gbpjpy_buy_is_macro_conflict(self):
        # XAUUSD BUY already active; adding GBPJPY BUY
        warning = self.engine.check_new_signal(
            pair="GBPJPY",
            direction="BUY",
            lot_size=0.10,
            account_balance=10_000.0,
            active_signals=[self._xau_active("BUY")],
        )
        assert warning is not None
        assert warning.type == "macro_conflict"
        assert warning.severity == "warning"
        assert "risk-off" in warning.message.lower()

    def test_gbpjpy_buy_plus_xauusd_buy_is_macro_conflict(self):
        # GBPJPY BUY already active; adding XAUUSD BUY
        warning = self.engine.check_new_signal(
            pair="XAUUSD",
            direction="BUY",
            lot_size=0.10,
            account_balance=10_000.0,
            active_signals=[self._gj_active("BUY")],
        )
        assert warning is not None
        assert warning.type == "macro_conflict"

    def test_both_sell_warns_dxy(self):
        # XAUUSD SELL active; adding GBPJPY SELL
        warning = self.engine.check_new_signal(
            pair="GBPJPY",
            direction="SELL",
            lot_size=0.10,
            account_balance=10_000.0,
            active_signals=[self._xau_active("SELL")],
        )
        assert warning is not None
        assert warning.type == "same_direction"
        assert "DXY" in warning.message

    def test_returns_none_when_no_conflict(self):
        # No active signals for other pair
        warning = self.engine.check_new_signal(
            pair="XAUUSD",
            direction="BUY",
            lot_size=0.10,
            account_balance=10_000.0,
            active_signals=[],
        )
        assert warning is None

    def test_returns_none_for_opposing_directions(self):
        # XAUUSD BUY + GBPJPY SELL: no conflict (different risk narratives that can coexist)
        warning = self.engine.check_new_signal(
            pair="GBPJPY",
            direction="SELL",
            lot_size=0.10,
            account_balance=10_000.0,
            active_signals=[self._xau_active("BUY")],
        )
        assert warning is None

    def test_blocks_when_exposure_limit_exceeded(self):
        # Large lot sizes that push total exposure > 4% of $10,000
        large_xau = {"pair": "XAUUSD", "direction": "BUY", "lot_size": 2.0, "sl_pips": 200.0}
        large_gj = {"pair": "GBPJPY", "direction": "SELL", "lot_size": 2.0, "sl_pips": 100.0}
        warning = self.engine.check_new_signal(
            pair="GBPJPY",
            direction="BUY",
            lot_size=2.0,
            account_balance=10_000.0,
            active_signals=[large_xau, large_gj],
        )
        assert warning is not None
        assert warning.type == "exposure_limit"
        assert warning.severity == "block"


# ══════════════════════════════════════════════════════════════════════════════
# CorrelationEngine.get_net_exposure
# ══════════════════════════════════════════════════════════════════════════════


class TestCorrelationEngineGetNetExposure:
    def setup_method(self):
        self.engine = CorrelationEngine()

    def test_empty_signals_returns_zero(self):
        result = self.engine.get_net_exposure([], account_balance=10_000.0)
        assert result["total_risk_pct"] == 0.0
        assert result["xauusd_risk_pct"] == 0.0
        assert result["gbpjpy_risk_pct"] == 0.0
        assert result["direction_conflict"] is False

    def test_xauusd_exposure_calculation(self):
        # 0.1 lots × 200 pips × $1/pip = $20 risk → 0.2% of $10,000
        signals = [{"pair": "XAUUSD", "direction": "BUY", "lot_size": 0.1, "sl_pips": 200.0}]
        result = self.engine.get_net_exposure(signals, account_balance=10_000.0)
        assert result["xauusd_risk_pct"] == pytest.approx(0.2)
        assert result["total_risk_pct"] == pytest.approx(0.2)

    def test_gbpjpy_exposure_calculation(self):
        # 0.1 lots × 50 pips × $9.50/pip = $47.50 → 0.475% of $10,000
        signals = [{"pair": "GBPJPY", "direction": "SELL", "lot_size": 0.1, "sl_pips": 50.0}]
        result = self.engine.get_net_exposure(signals, account_balance=10_000.0)
        assert result["gbpjpy_risk_pct"] == pytest.approx(0.475)

    def test_combined_exposure(self):
        signals = [
            {"pair": "XAUUSD", "direction": "BUY", "lot_size": 0.1, "sl_pips": 200.0},
            {"pair": "GBPJPY", "direction": "BUY", "lot_size": 0.1, "sl_pips": 50.0},
        ]
        result = self.engine.get_net_exposure(signals, account_balance=10_000.0)
        # XAU: $20, GJ: $47.50 → total $67.50 = 0.675%
        assert result["total_risk_pct"] == pytest.approx(0.675)
        assert result["total_risk_usd"] == pytest.approx(67.50)

    def test_direction_conflict_flag_xau_buy_gj_buy(self):
        signals = [
            {"pair": "XAUUSD", "direction": "BUY", "lot_size": 0.1, "sl_pips": 200.0},
            {"pair": "GBPJPY", "direction": "BUY", "lot_size": 0.1, "sl_pips": 50.0},
        ]
        result = self.engine.get_net_exposure(signals, account_balance=10_000.0)
        assert result["direction_conflict"] is True

    def test_no_direction_conflict_xau_buy_gj_sell(self):
        signals = [
            {"pair": "XAUUSD", "direction": "BUY", "lot_size": 0.1, "sl_pips": 200.0},
            {"pair": "GBPJPY", "direction": "SELL", "lot_size": 0.1, "sl_pips": 50.0},
        ]
        result = self.engine.get_net_exposure(signals, account_balance=10_000.0)
        assert result["direction_conflict"] is False

    def test_zero_balance_returns_zeros(self):
        signals = [{"pair": "XAUUSD", "direction": "BUY", "lot_size": 1.0, "sl_pips": 200.0}]
        result = self.engine.get_net_exposure(signals, account_balance=0.0)
        assert result["total_risk_pct"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Context-aware cooldown — §11.4
# ══════════════════════════════════════════════════════════════════════════════


class TestContextAwareCooldown:
    def setup_method(self):
        self.guards = RiskGuards(initial_equity_peak=10_000.0)

    def test_pattern_suppressed_after_2_losses_same_kz_setup(self):
        """2 consecutive non-news losses on same KZ+setup → pattern suppressed 24h."""
        self.guards.record_trade_result("s1", "XAUUSD", "loss", -0.01, "London", "OB", False)
        self.guards.record_trade_result("s2", "XAUUSD", "loss", -0.01, "London", "OB", False)

        key = _pattern_key("XAUUSD", "London", "OB")
        assert key in self.guards.suppressed_patterns
        suppress_until = self.guards.suppressed_patterns[key]
        # Should be suppressed for approximately 24h
        expected = _utcnow() + timedelta(hours=23)
        assert suppress_until > expected

    def test_pattern_not_suppressed_after_1_loss(self):
        """Single loss should NOT trigger pattern suppression."""
        self.guards.record_trade_result("s1", "XAUUSD", "loss", -0.01, "London", "OB", False)

        key = _pattern_key("XAUUSD", "London", "OB")
        assert key not in self.guards.suppressed_patterns

    def test_news_attributed_loss_no_cooldown(self):
        """Losses during news events should NOT trigger any cooldown."""
        self.guards.record_trade_result("s1", "XAUUSD", "loss", -0.01, "London", "OB", True)
        self.guards.record_trade_result("s2", "XAUUSD", "loss", -0.01, "London", "OB", True)

        # No full cooldown
        assert self.guards._full_cooldown_until is None

        # No pattern suppression (news-attributed)
        key = _pattern_key("XAUUSD", "London", "OB")
        assert key not in self.guards.suppressed_patterns

    def test_rolling_loss_rate_triggers_full_cooldown(self):
        """Rolling loss rate > 50% on last 10 signals → 4-hour cooldown."""
        # Fill the window with 6 losses and 4 wins (60% loss rate > 50%)
        for i in range(6):
            self.guards.record_trade_result(
                f"s{i}", "XAUUSD", "loss", -0.01, "London", "OB", False
            )
        for i in range(4):
            self.guards.record_trade_result(
                f"w{i}", "XAUUSD", "win", 0.02, "NewYork", "FVG", False
            )

        assert self.guards._full_cooldown_until is not None
        # Should be ~4 hours from now
        expected_min = _utcnow() + timedelta(hours=3, minutes=50)
        assert self.guards._full_cooldown_until > expected_min

    def test_rolling_loss_rate_below_threshold_no_cooldown(self):
        """40% loss rate (4/10) should NOT trigger cooldown.

        We alternate wins and losses so the rolling rate never exceeds 50%
        during the filling of the window, ending at exactly 40% (4 losses / 10).
        """
        # Pattern: W, L, W, L, W, L, W, L, W, W  → 4 losses, 6 wins = 40%
        outcomes = ["win", "loss", "win", "loss", "win", "loss", "win", "loss", "win", "win"]
        for i, outcome in enumerate(outcomes):
            self.guards.record_trade_result(
                f"s{i}", "XAUUSD", outcome, 0.02 if outcome == "win" else -0.01,
                "London", f"SETUP_{i}", False   # unique setup to avoid pattern suppression
            )

        assert self.guards._full_cooldown_until is None

    def test_can_trade_blocked_by_pattern_suppression(self):
        """can_trade_pattern returns False when the pattern is suppressed."""
        key = _pattern_key("XAUUSD", "London", "OB")
        self.guards.suppressed_patterns[key] = _utcnow() + timedelta(hours=20)

        allowed, reason = self.guards.can_trade_pattern("XAUUSD", "London", "OB")
        assert allowed is False
        assert "suppressed" in reason.lower()

    def test_can_trade_pattern_allowed_when_not_suppressed(self):
        allowed, reason = self.guards.can_trade_pattern("XAUUSD", "London", "OB")
        assert allowed is True
        assert reason == "ok"

    def test_pattern_suppression_different_setup_type_unaffected(self):
        """Suppressing London/OB should not affect London/FVG."""
        self.guards.record_trade_result("s1", "XAUUSD", "loss", -0.01, "London", "OB", False)
        self.guards.record_trade_result("s2", "XAUUSD", "loss", -0.01, "London", "OB", False)

        # OB pattern suppressed
        ob_allowed, _ = self.guards.can_trade_pattern("XAUUSD", "London", "OB")
        assert ob_allowed is False

        # FVG pattern on same KZ should still be allowed
        fvg_allowed, _ = self.guards.can_trade_pattern("XAUUSD", "London", "FVG")
        assert fvg_allowed is True
