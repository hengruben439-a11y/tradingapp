"""
Tests for live market data providers and engine runner.

All tests use mocked HTTP responses — no real API calls are made.
Async tests use pytest-asyncio.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from live.providers.oanda import OANDAProvider
from live.providers.twelve_data import TwelveDataProvider
from live.providers.calendar_provider import CalendarProvider
from live.engine_runner import EngineRunner, _CANDLE_BUFFER_SIZE


# ── OANDAProvider: instrument name conversion ─────────────────────────────────

class TestOANDAInstrumentName:
    def test_xauusd_converts(self):
        assert OANDAProvider._instrument_name("XAUUSD") == "XAU_USD"

    def test_gbpjpy_converts(self):
        assert OANDAProvider._instrument_name("GBPJPY") == "GBP_JPY"

    def test_eurusd_converts(self):
        assert OANDAProvider._instrument_name("EURUSD") == "EUR_USD"

    def test_usdjpy_converts(self):
        assert OANDAProvider._instrument_name("USDJPY") == "USD_JPY"

    def test_generic_6char_converts(self):
        # Any 6-char pair not in the known map falls back to positional split
        assert OANDAProvider._instrument_name("AUDCAD") == "AUD_CAD"


# ── OANDAProvider: TF → granularity conversion ────────────────────────────────

class TestOANDAGranularity:
    def test_1m(self):
        assert OANDAProvider._tf_to_granularity("1m") == "M1"

    def test_5m(self):
        assert OANDAProvider._tf_to_granularity("5m") == "M5"

    def test_15m(self):
        assert OANDAProvider._tf_to_granularity("15m") == "M15"

    def test_30m(self):
        assert OANDAProvider._tf_to_granularity("30m") == "M30"

    def test_1h(self):
        assert OANDAProvider._tf_to_granularity("1H") == "H1"

    def test_4h(self):
        assert OANDAProvider._tf_to_granularity("4H") == "H4"

    def test_1d(self):
        assert OANDAProvider._tf_to_granularity("1D") == "D"

    def test_1w(self):
        assert OANDAProvider._tf_to_granularity("1W") == "W"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            OANDAProvider._tf_to_granularity("3H")


# ── TwelveDataProvider: symbol conversion ─────────────────────────────────────

class TestTwelveDataSymbol:
    def test_xauusd(self):
        assert TwelveDataProvider._symbol("XAUUSD") == "XAU/USD"

    def test_gbpjpy(self):
        assert TwelveDataProvider._symbol("GBPJPY") == "GBP/JPY"

    def test_eurusd(self):
        assert TwelveDataProvider._symbol("EURUSD") == "EUR/USD"

    def test_generic_6char(self):
        assert TwelveDataProvider._symbol("AUDNZD") == "AUD/NZD"


# ── TwelveDataProvider: interval conversion ───────────────────────────────────

class TestTwelveDataInterval:
    def test_1m(self):
        assert TwelveDataProvider._interval("1m") == "1min"

    def test_5m(self):
        assert TwelveDataProvider._interval("5m") == "5min"

    def test_15m(self):
        assert TwelveDataProvider._interval("15m") == "15min"

    def test_1h(self):
        assert TwelveDataProvider._interval("1H") == "1h"

    def test_4h(self):
        assert TwelveDataProvider._interval("4H") == "4h"

    def test_1d(self):
        assert TwelveDataProvider._interval("1D") == "1day"

    def test_1w(self):
        assert TwelveDataProvider._interval("1W") == "1week"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            TwelveDataProvider._interval("2H")


# ── CalendarProvider: is_high_impact_event_imminent ───────────────────────────

class TestCalendarProviderImminence:
    def _make_event(self, minutes_from_now: float, impact: str = "high") -> dict:
        """Helper to create a mock event dict."""
        return {
            "name":           "Test Event",
            "datetime_utc":   datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now),
            "impact":         impact,
            "pairs_affected": ["XAUUSD"],
            "actual":         None,
            "forecast":       "100",
            "previous":       "95",
            "source":         "test",
        }

    @pytest.mark.asyncio
    async def test_imminent_high_impact_returns_true(self):
        provider = CalendarProvider()
        future_event = self._make_event(minutes_from_now=10, impact="high")
        with patch.object(provider, "_fetch_events", new=AsyncMock(return_value=[future_event])):
            result = await provider.is_high_impact_event_imminent(minutes=15)
        assert result is True

    @pytest.mark.asyncio
    async def test_distant_event_returns_false(self):
        provider = CalendarProvider()
        future_event = self._make_event(minutes_from_now=60, impact="high")
        with patch.object(provider, "_fetch_events", new=AsyncMock(return_value=[future_event])):
            result = await provider.is_high_impact_event_imminent(minutes=15)
        assert result is False

    @pytest.mark.asyncio
    async def test_medium_impact_event_returns_false(self):
        """Only high-impact events trigger the imminent flag."""
        provider = CalendarProvider()
        future_event = self._make_event(minutes_from_now=5, impact="medium")
        with patch.object(provider, "_fetch_events", new=AsyncMock(return_value=[future_event])):
            result = await provider.is_high_impact_event_imminent(minutes=15)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_events_returns_false(self):
        provider = CalendarProvider()
        with patch.object(provider, "_fetch_events", new=AsyncMock(return_value=[])):
            result = await provider.is_high_impact_event_imminent(minutes=15)
        assert result is False

    def test_normalise_impact_high_variants(self):
        normalise = CalendarProvider._normalise_impact
        assert normalise("3") == "high"
        assert normalise("3.0") == "high"
        assert normalise("high") == "high"
        assert normalise("red") == "high"

    def test_normalise_impact_medium(self):
        normalise = CalendarProvider._normalise_impact
        assert normalise("2") == "medium"
        assert normalise("medium") == "medium"
        assert normalise("orange") == "medium"

    def test_normalise_impact_low(self):
        normalise = CalendarProvider._normalise_impact
        assert normalise("1") == "low"
        assert normalise("low") == "low"


# ── EngineRunner: candle buffer rolling ───────────────────────────────────────

class TestCandleBuffer:
    def _make_runner(self) -> EngineRunner:
        # Patch provider constructors to avoid needing env vars
        with patch("live.engine_runner.OANDAProvider"), \
             patch("live.engine_runner.TwelveDataProvider"):
            runner = EngineRunner(trading_styles=["day_trading"])
        return runner

    def test_buffer_maxlen(self):
        runner = self._make_runner()
        assert runner._buffers["XAUUSD"].maxlen == _CANDLE_BUFFER_SIZE

    def test_buffer_rolls_over(self):
        runner = self._make_runner()
        buf = runner._buffers["XAUUSD"]
        # Fill beyond maxlen
        for i in range(_CANDLE_BUFFER_SIZE + 50):
            buf.append({"timestamp": i, "open": 1.0, "high": 1.0, "low": 1.0,
                        "close": 1.0, "volume": 0.0})
        assert len(buf) == _CANDLE_BUFFER_SIZE
        # Oldest entries were evicted; newest remain
        assert buf[-1]["timestamp"] == _CANDLE_BUFFER_SIZE + 49


# ── EngineRunner: heartbeat monitor switches to fallback ─────────────────────

class TestHeartbeatMonitor:
    def _make_runner(self) -> EngineRunner:
        with patch("live.engine_runner.OANDAProvider"), \
             patch("live.engine_runner.TwelveDataProvider"):
            runner = EngineRunner(trading_styles=["day_trading"])
        runner._primary = MagicMock()
        runner._primary.is_connected = True
        runner._fallback = MagicMock()
        runner._fallback.is_connected = False
        runner._active_provider = runner._primary
        return runner

    @pytest.mark.asyncio
    async def test_stale_primary_triggers_fallback_switch(self):
        runner = self._make_runner()
        runner._running = True

        # Simulate a stale last_bar_time (3 minutes ago — exceeds 2x 60s interval)
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=180)
        runner._last_bar_time[("XAUUSD", "1m")] = stale_time

        runner._switch_to_fallback = AsyncMock()
        runner._try_restore_primary = AsyncMock()

        # Temporarily patch asyncio.sleep to avoid waiting
        with patch("asyncio.sleep", new=AsyncMock(side_effect=[None, asyncio.CancelledError()])):
            try:
                await runner._heartbeat_monitor()
            except asyncio.CancelledError:
                pass

        runner._switch_to_fallback.assert_called_once()

    @pytest.mark.asyncio
    async def test_fresh_feed_does_not_switch(self):
        runner = self._make_runner()
        runner._running = True

        # Simulate a fresh last_bar_time (10 seconds ago)
        runner._last_bar_time[("XAUUSD", "1m")] = (
            datetime.now(timezone.utc) - timedelta(seconds=10)
        )

        runner._switch_to_fallback = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock(side_effect=[None, asyncio.CancelledError()])):
            try:
                await runner._heartbeat_monitor()
            except asyncio.CancelledError:
                pass

        runner._switch_to_fallback.assert_not_called()


# ── EngineRunner: _publish_signal serialisation ───────────────────────────────

class TestPublishSignalSerialisation:
    def _make_runner(self) -> EngineRunner:
        with patch("live.engine_runner.OANDAProvider"), \
             patch("live.engine_runner.TwelveDataProvider"):
            return EngineRunner(trading_styles=["day_trading"])

    def _make_trade_record(self) -> object:
        """Return a minimal TradeRecord-like object."""
        from backtest.executor import TradeRecord, TradeStatus
        from engine.signal import Direction
        from datetime import datetime, timezone

        return TradeRecord(
            signal_id="test-signal-001",
            pair="XAUUSD",
            direction=Direction.BUY,
            signal_time=datetime(2026, 3, 26, 12, 0, 0, tzinfo=timezone.utc),
            entry_time=None,
            entry_price=2350.50,
            fill_price=None,
            spread_applied=0.0,
            stop_loss=2330.00,
            tp1=2370.00,
            tp2=2390.00,
            tp3=2420.00,
            initial_lot_size=0.10,
            current_lot_size=0.10,
            status=TradeStatus.PENDING,
        )

    def test_serialise_signal_has_required_keys(self):
        runner = self._make_runner()
        trade = self._make_trade_record()
        result = runner._serialise_signal(trade, "XAUUSD", "day_trading")

        required_keys = [
            "signal_id", "pair", "trading_style", "direction",
            "signal_time", "entry_price", "stop_loss",
            "tp1", "tp2", "tp3", "lot_size", "status", "published_at",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_serialise_signal_direction_is_string(self):
        runner = self._make_runner()
        trade = self._make_trade_record()
        result = runner._serialise_signal(trade, "XAUUSD", "day_trading")
        assert isinstance(result["direction"], str)
        assert result["direction"] in ("BUY", "SELL")

    def test_serialise_signal_is_json_serialisable(self):
        runner = self._make_runner()
        trade = self._make_trade_record()
        result = runner._serialise_signal(trade, "XAUUSD", "day_trading")
        # Should not raise
        encoded = json.dumps(result, default=str)
        decoded = json.loads(encoded)
        assert decoded["signal_id"] == "test-signal-001"
        assert decoded["entry_price"] == 2350.50

    def test_serialise_signal_values_match_trade(self):
        runner = self._make_runner()
        trade = self._make_trade_record()
        result = runner._serialise_signal(trade, "XAUUSD", "day_trading")
        assert result["pair"] == "XAUUSD"
        assert result["trading_style"] == "day_trading"
        assert result["stop_loss"] == 2330.00
        assert result["tp1"] == 2370.00
        assert result["tp2"] == 2390.00
        assert result["tp3"] == 2420.00
