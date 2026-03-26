"""
Live Engine Runner — connects market data to the signal pipeline.

Orchestrates:
1. OANDA primary data feed (Twelve Data fallback)
2. Per-pair SignalGenerator instances
3. Redis signal publishing
4. Heartbeat monitoring and automatic failover

Usage:
    runner = EngineRunner()
    await runner.start()  # blocks until stopped
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from data.resampler import resample_all
from engine.signal_generator import STYLE_TIMEFRAMES, SignalGenerator
from backtest.executor import TradeRecord
from live.providers.base import BaseDataProvider, DataFeedError
from live.providers.oanda import OANDAProvider
from live.providers.twelve_data import TwelveDataProvider

try:
    from api.redis_client import get_redis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    get_redis = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Pairs the engine tracks
SUPPORTED_PAIRS = ["XAUUSD", "GBPJPY"]

# Shadow log file path (for Phase 1.5 shadow mode validation)
SHADOW_SIGNALS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "reports", "shadow_signals.jsonl"
)

# Number of 1m bars to keep in the rolling candle buffer per pair
_CANDLE_BUFFER_SIZE = 2000

# Timeframes that must be polled to support all trading styles
_ALL_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]

# Expected polling interval per timeframe in seconds (mirrors provider poll intervals)
_TF_INTERVAL_SECONDS: dict[str, int] = {
    "1m":  60,
    "5m":  300,
    "15m": 900,
    "30m": 1800,
    "1H":  3600,
    "4H":  14400,
    "1D":  86400,
    "1W":  604800,
}


class EngineRunner:
    """
    Connects live market data to the confluence signal engine.

    Architecture:
    - Maintains a rolling 2000-bar 1m candle buffer per pair.
    - On every 1m bar close: resamples all timeframes from the buffer.
    - Feeds resampled candles to all relevant SignalGenerator instances.
    - Publishes signals to Redis and logs to shadow_signals.jsonl.
    - Heartbeat monitor switches to Twelve Data if OANDA feed goes stale.
    """

    def __init__(self, trading_styles: Optional[list[str]] = None) -> None:
        self.trading_styles = trading_styles or ["day_trading"]

        # One SignalGenerator per (pair, style) combination
        self._generators: dict[tuple[str, str], SignalGenerator] = {}
        for pair in SUPPORTED_PAIRS:
            for style in self.trading_styles:
                self._generators[(pair, style)] = SignalGenerator(pair, style)

        # Rolling 1m candle buffers: pair → deque of rows as dicts
        self._buffers: dict[str, deque] = {
            pair: deque(maxlen=_CANDLE_BUFFER_SIZE) for pair in SUPPORTED_PAIRS
        }

        # Primary and fallback providers
        self._primary: BaseDataProvider = OANDAProvider()
        self._fallback: BaseDataProvider = TwelveDataProvider()
        self._active_provider: BaseDataProvider = self._primary

        # Heartbeat tracking: last bar-close time per (pair, tf)
        self._last_bar_time: dict[tuple[str, str], datetime] = {}

        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Connect data feeds, subscribe to all pairs/timeframes, run until stop()."""
        self._running = True
        logger.info("EngineRunner starting (styles: %s)", self.trading_styles)

        await self._connect_provider(self._primary)

        self._primary.on_bar_close = self._on_bar_close
        for pair in SUPPORTED_PAIRS:
            await self._active_provider.subscribe(pair, _ALL_TIMEFRAMES)

        # Warm up buffers with recent history
        await self._warm_up_buffers()

        # Start heartbeat monitor
        self._monitor_task = asyncio.create_task(
            self._heartbeat_monitor(), name="heartbeat_monitor"
        )

        logger.info("EngineRunner running — waiting for bar closes")

        # Block until stopped
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Gracefully shut down all providers and background tasks."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        for provider in (self._primary, self._fallback):
            if provider.is_connected:
                try:
                    await provider.disconnect()
                except Exception:
                    logger.exception("Error disconnecting provider %s", provider)

        logger.info("EngineRunner stopped")

    # ── Bar Close Handler ──────────────────────────────────────────────────────

    def _on_bar_close(self, pair: str, tf: str, bar: pd.Series) -> None:
        """
        Fires when a bar closes on any subscribed (pair, tf).

        Updates candle buffer (1m only), resamples all timeframes, and
        runs the signal pipeline for all matching generators.
        """
        now_utc = datetime.now(timezone.utc)
        self._last_bar_time[(pair, tf)] = now_utc

        if tf == "1m":
            # Append to rolling buffer
            self._buffers[pair].append({
                "timestamp": bar.name,
                "open":      float(bar["open"]),
                "high":      float(bar["high"]),
                "low":       float(bar["low"]),
                "close":     float(bar["close"]),
                "volume":    float(bar.get("volume", 0)),
            })

        # Determine which generators should fire on this timeframe close
        entry_tfs = {STYLE_TIMEFRAMES[style][0] for style in self.trading_styles
                     if style in STYLE_TIMEFRAMES}

        if tf not in entry_tfs and tf != "1m":
            return  # Only run generators on their entry TF bar close

        buf = self._buffers.get(pair)
        if not buf or len(buf) < 10:
            logger.debug("Buffer for %s too small (%d bars) — skipping", pair, len(buf))
            return

        # Build 1m DataFrame from buffer
        df_1m = self._buffer_to_dataframe(pair)
        if df_1m is None or df_1m.empty:
            return

        # Resample to all timeframes
        try:
            candles_dict = resample_all(df_1m)
        except Exception:
            logger.exception("Resample failed for %s", pair)
            return

        # Run generators for this pair
        for style in self.trading_styles:
            entry_tf = STYLE_TIMEFRAMES.get(style, (None,))[0]
            if entry_tf != tf and tf != "1m":
                continue  # Only fire on the generator's entry TF
            if entry_tf not in candles_dict:
                continue

            gen = self._generators.get((pair, style))
            if gen is None:
                continue

            entry_candles = candles_dict[entry_tf]
            if len(entry_candles) < 5:
                continue

            bar_index = len(entry_candles) - 1

            # Check news proximity (lazy: calendar not async-called here to avoid blocking)
            news_proximity = False

            try:
                signal = gen.process_bar(
                    candles_dict=candles_dict,
                    bar_index=bar_index,
                    news_proximity=news_proximity,
                )
            except Exception:
                logger.exception("Signal generator failed for %s %s", pair, style)
                continue

            if signal is not None:
                asyncio.ensure_future(
                    self._publish_signal(signal, pair, style)
                )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _buffer_to_dataframe(self, pair: str) -> Optional[pd.DataFrame]:
        """Convert the rolling deque buffer to a UTC-indexed OHLCV DataFrame."""
        buf = self._buffers.get(pair)
        if not buf:
            return None

        rows = list(buf)
        df = pd.DataFrame(rows)
        if df.empty:
            return None

        df = df.set_index("timestamp")
        df.index = pd.DatetimeIndex(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        df = df.astype("float64")
        df = df.sort_index()
        return df

    async def _warm_up_buffers(self) -> None:
        """
        Pre-fill 1m candle buffers with recent historical data.

        We need at least 200 bars on every timeframe for engine warmup,
        which means ~2000 1m bars (covers 4H with 500 bars).
        """
        for pair in SUPPORTED_PAIRS:
            try:
                df = await self._active_provider.get_latest_candles(
                    pair, "1m", n=_CANDLE_BUFFER_SIZE
                )
                if df.empty:
                    logger.warning("Warm-up returned empty DataFrame for %s 1m", pair)
                    continue

                for ts, row in df.iterrows():
                    self._buffers[pair].append({
                        "timestamp": ts,
                        "open":      float(row["open"]),
                        "high":      float(row["high"]),
                        "low":       float(row["low"]),
                        "close":     float(row["close"]),
                        "volume":    float(row.get("volume", 0)),
                    })

                logger.info(
                    "Warmed up %s buffer: %d 1m candles",
                    pair, len(self._buffers[pair]),
                )
            except Exception:
                logger.exception("Warm-up failed for %s — signals may be delayed", pair)

    async def _connect_provider(self, provider: BaseDataProvider) -> None:
        """Attempt to connect a provider; raise DataFeedError on failure."""
        try:
            await provider.connect()
            self._active_provider = provider
        except DataFeedError:
            logger.exception("Provider %s failed to connect", type(provider).__name__)
            raise

    # ── Heartbeat Monitor ──────────────────────────────────────────────────────

    async def _heartbeat_monitor(self) -> None:
        """
        Periodically check that the active feed is delivering data.

        If the primary feed has not produced a bar in 2x its expected interval,
        switch to the fallback (Twelve Data).
        """
        check_interval = 60  # seconds between heartbeat checks

        while self._running:
            await asyncio.sleep(check_interval)

            if not self._running:
                break

            now_utc = datetime.now(timezone.utc)
            feed_stale = False

            # Check 1m bars for all pairs — these should arrive every ~60s
            for pair in SUPPORTED_PAIRS:
                key = (pair, "1m")
                last = self._last_bar_time.get(key)
                if last is None:
                    continue  # No bars yet — still warming up

                elapsed = (now_utc - last).total_seconds()
                expected = _TF_INTERVAL_SECONDS["1m"]
                if elapsed > 2 * expected:
                    logger.warning(
                        "Feed stale for %s 1m: last bar %.0fs ago (2x expected = %ds)",
                        pair, elapsed, 2 * expected,
                    )
                    feed_stale = True
                    break

            if feed_stale and self._active_provider is self._primary:
                logger.warning("Primary feed stale — switching to Twelve Data fallback")
                await self._switch_to_fallback()
            elif not feed_stale and self._active_provider is self._fallback:
                # Try to reconnect to primary
                logger.info("Attempting to reconnect to primary OANDA feed")
                await self._try_restore_primary()

    async def _switch_to_fallback(self) -> None:
        """Switch from OANDA to Twelve Data fallback."""
        try:
            if not self._fallback.is_connected:
                await self._fallback.connect()
            self._fallback.on_bar_close = self._on_bar_close
            for pair in SUPPORTED_PAIRS:
                await self._fallback.subscribe(pair, _ALL_TIMEFRAMES)
            self._active_provider = self._fallback
            logger.info("Switched to Twelve Data fallback provider")
        except Exception:
            logger.exception("Failed to switch to Twelve Data fallback — no data source active")

    async def _try_restore_primary(self) -> None:
        """Attempt to restore the primary OANDA feed."""
        try:
            if not self._primary.is_connected:
                await self._primary.connect()
            self._primary.on_bar_close = self._on_bar_close
            for pair in SUPPORTED_PAIRS:
                await self._primary.subscribe(pair, _ALL_TIMEFRAMES)
            self._active_provider = self._primary
            logger.info("Restored primary OANDA feed")
        except Exception:
            logger.debug("Primary OANDA feed not yet available — staying on fallback")

    # ── Signal Publishing ──────────────────────────────────────────────────────

    async def _publish_signal(
        self,
        signal: TradeRecord,
        pair: str,
        style: str,
    ) -> None:
        """
        Serialise a TradeRecord and publish it to Redis + shadow log.

        Redis channel: "signals:{pair}" (e.g. "signals:XAUUSD")
        """
        signal_dict = self._serialise_signal(signal, pair, style)

        # Log to shadow_signals.jsonl (always, regardless of Redis)
        try:
            os.makedirs(os.path.dirname(SHADOW_SIGNALS_PATH), exist_ok=True)
            with open(SHADOW_SIGNALS_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(signal_dict, default=str) + "\n")
        except Exception:
            logger.exception("Failed to write signal to shadow log")

        # Publish to Redis
        if _REDIS_AVAILABLE and get_redis is not None:
            try:
                redis = await get_redis()
                if redis is not None:
                    channel = f"signals:{pair}"
                    await redis.publish(channel, json.dumps(signal_dict, default=str))
                    logger.debug("Published signal %s to Redis channel %s", signal.signal_id, channel)
            except Exception:
                logger.exception("Redis publish failed for signal %s", signal.signal_id)

        logger.info(
            "Signal: %s %s %s | entry=%.2f SL=%.2f TP1=%.2f | score_id=%s",
            pair,
            signal.direction.value if hasattr(signal.direction, "value") else signal.direction,
            style,
            signal.entry_price,
            signal.stop_loss,
            signal.tp1,
            signal.signal_id[:8],
        )

    @staticmethod
    def _serialise_signal(signal: TradeRecord, pair: str, style: str) -> dict:
        """Convert a TradeRecord to a JSON-serialisable dict."""
        return {
            "signal_id":      signal.signal_id,
            "pair":           pair,
            "trading_style":  style,
            "direction":      (
                signal.direction.value
                if hasattr(signal.direction, "value")
                else str(signal.direction)
            ),
            "signal_time":    signal.signal_time.isoformat() if signal.signal_time else None,
            "entry_price":    signal.entry_price,
            "stop_loss":      signal.stop_loss,
            "tp1":            signal.tp1,
            "tp2":            signal.tp2,
            "tp3":            signal.tp3,
            "lot_size":       signal.initial_lot_size,
            "status":         signal.status.value if hasattr(signal.status, "value") else str(signal.status),
            "published_at":   datetime.now(timezone.utc).isoformat(),
        }


if __name__ == "__main__":
    import asyncio
    runner = EngineRunner()
    asyncio.run(runner.start())
