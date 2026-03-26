"""
OANDA REST API provider for live OHLCV data.

Config (from env):
    OANDA_API_KEY: Bearer token
    OANDA_ACCOUNT_ID: Account ID
    OANDA_ENVIRONMENT: "practice" or "live" (default: practice)

Instruments: XAUUSD → XAU_USD, GBPJPY → GBP_JPY

OANDA does not offer a WebSocket candle stream — only tick streaming.
Bar close detection is implemented via polling at appropriate intervals
per timeframe. The provider detects a new closed bar by comparing the
latest candle's timestamp against the previously observed timestamp.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False
    httpx = None  # type: ignore[assignment]

from live.providers.base import BaseDataProvider, DataFeedError

logger = logging.getLogger(__name__)

# OANDA REST API base URLs
_OANDA_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live":     "https://api-fxtrade.oanda.com",
}

# Granularity strings for each timeframe (OANDA v3 API)
_GRANULARITY: dict[str, str] = {
    "1m":  "M1",
    "5m":  "M5",
    "15m": "M15",
    "30m": "M30",
    "1H":  "H1",
    "4H":  "H4",
    "1D":  "D",
    "1W":  "W",
}

# Polling interval per timeframe in seconds.
# We poll more frequently than the bar duration to catch closes promptly.
_POLL_INTERVAL: dict[str, int] = {
    "1m":  30,
    "5m":  60,
    "15m": 60,
    "30m": 60,
    "1H":  120,
    "4H":  300,
    "1D":  600,
    "1W":  3600,
}

# Maximum retries before raising DataFeedError
_MAX_RETRIES = 5


class OANDAProvider(BaseDataProvider):
    """
    OANDA REST API market data provider.

    Uses polling to detect bar closes across all subscribed timeframes.
    Credentials are read from environment variables at instantiation time.
    """

    def __init__(self) -> None:
        super().__init__()
        if not _HTTPX_AVAILABLE:
            raise ImportError("httpx is required for OANDAProvider. Install with: pip install httpx")

        self._api_key: str = os.environ.get("OANDA_API_KEY", "")
        self._account_id: str = os.environ.get("OANDA_ACCOUNT_ID", "")
        env = os.environ.get("OANDA_ENVIRONMENT", "practice").lower()
        if env not in _OANDA_URLS:
            raise ValueError(f"OANDA_ENVIRONMENT must be 'practice' or 'live', got: {env!r}")
        self._base_url: str = _OANDA_URLS[env]

        self._client: Optional[httpx.AsyncClient] = None
        self._poll_tasks: list[asyncio.Task] = []

        # Tracks last seen candle timestamp per (pair, tf) to detect new bar closes
        self._last_seen: dict[tuple[str, str], Optional[datetime]] = {}

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Validate OANDA credentials by fetching account summary."""
        if not self._api_key or not self._account_id:
            raise DataFeedError(
                "OANDA credentials missing. Set OANDA_API_KEY and OANDA_ACCOUNT_ID env vars."
            )

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

        try:
            resp = await self._client.get(f"/v3/accounts/{self._account_id}")
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            await self._client.aclose()
            self._client = None
            raise DataFeedError(
                f"OANDA authentication failed (HTTP {exc.response.status_code}): {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            await self._client.aclose()
            self._client = None
            raise DataFeedError(f"OANDA connection error: {exc}") from exc

        self._is_connected = True
        logger.info("OANDAProvider connected (account: %s)", self._account_id)

    async def disconnect(self) -> None:
        """Cancel all polling tasks and close the HTTP client."""
        self._is_connected = False
        for task in self._poll_tasks:
            task.cancel()
        if self._poll_tasks:
            await asyncio.gather(*self._poll_tasks, return_exceptions=True)
        self._poll_tasks.clear()
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("OANDAProvider disconnected")

    # ── Subscription ──────────────────────────────────────────────────────────

    async def subscribe(self, pair: str, timeframes: list[str]) -> None:
        """Start polling loops for each (pair, tf) combination."""
        if not self._is_connected:
            raise DataFeedError("OANDAProvider.connect() must be called before subscribe().")

        for tf in timeframes:
            if tf not in _POLL_INTERVAL:
                logger.warning("OANDAProvider: unknown timeframe %r — skipping", tf)
                continue
            key = (pair, tf)
            if key in self._last_seen:
                logger.debug("Already subscribed to %s %s", pair, tf)
                continue
            self._last_seen[key] = None
            task = asyncio.create_task(
                self._poll_loop(pair, tf),
                name=f"oanda_poll_{pair}_{tf}",
            )
            self._poll_tasks.append(task)
            logger.info("OANDAProvider: subscribed to %s %s (poll every %ds)", pair, tf, _POLL_INTERVAL[tf])

    # ── Data Fetch ────────────────────────────────────────────────────────────

    async def get_latest_candles(
        self,
        pair: str,
        tf: str,
        n: int = 500,
    ) -> pd.DataFrame:
        """Fetch the N most recent closed candles via OANDA REST candles endpoint."""
        return await self.get_historical_candles(pair, tf, count=n)

    async def get_historical_candles(
        self,
        pair: str,
        tf: str,
        count: int = 500,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV candles from OANDA.

        Uses GET /v3/instruments/{instrument}/candles with count parameter.
        Returns only completed (closed) candles.
        """
        if self._client is None:
            raise DataFeedError("OANDAProvider is not connected.")

        instrument = self._instrument_name(pair)
        granularity = self._tf_to_granularity(tf)

        params = {
            "count": min(count, 5000),  # OANDA max is 5000 per request
            "granularity": granularity,
            "price": "M",   # Mid-point candles (OHLC average of bid/ask)
        }

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await self._client.get(
                    f"/v3/instruments/{instrument}/candles",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                return self._parse_candles(data.get("candles", []))

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (429, 503):
                    wait = 2 ** attempt
                    logger.warning(
                        "OANDA rate-limited (attempt %d/%d) — backing off %ds",
                        attempt, _MAX_RETRIES, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise DataFeedError(
                        f"OANDA candles HTTP error {exc.response.status_code}: {exc.response.text}"
                    ) from exc
            except httpx.RequestError as exc:
                wait = 2 ** attempt
                logger.warning(
                    "OANDA request error on attempt %d/%d: %s — retrying in %ds",
                    attempt, _MAX_RETRIES, exc, wait,
                )
                await asyncio.sleep(wait)

        raise DataFeedError(
            f"OANDA candle fetch failed after {_MAX_RETRIES} retries for {pair} {tf}"
        )

    # ── Poll Loop ─────────────────────────────────────────────────────────────

    async def _poll_loop(self, pair: str, tf: str) -> None:
        """
        Continuously poll OANDA for new candles on the given pair/timeframe.

        Compares the latest candle timestamp against _last_seen. When a new
        closed candle is detected, fires on_bar_close.
        """
        interval = _POLL_INTERVAL[tf]
        key = (pair, tf)

        while self._is_connected:
            try:
                df = await self.get_historical_candles(pair, tf, count=3)
                if df.empty:
                    await asyncio.sleep(interval)
                    continue

                latest_bar = df.iloc[-1]
                latest_ts: datetime = latest_bar.name.to_pydatetime()  # type: ignore[union-attr]

                prev_ts = self._last_seen.get(key)
                if prev_ts is None:
                    # First poll — record the timestamp but don't fire callback
                    self._last_seen[key] = latest_ts
                elif latest_ts > prev_ts:
                    # New bar detected
                    self._last_seen[key] = latest_ts
                    if self._on_bar_close is not None:
                        try:
                            self._on_bar_close(pair, tf, latest_bar)
                        except Exception:
                            logger.exception(
                                "on_bar_close callback raised for %s %s", pair, tf
                            )

            except DataFeedError:
                logger.exception("OANDA poll error for %s %s", pair, tf)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in OANDA poll loop %s %s", pair, tf)

            await asyncio.sleep(interval)

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_candles(self, candles: list[dict]) -> pd.DataFrame:
        """Parse OANDA candle objects into a standard OHLCV DataFrame."""
        rows = []
        for c in candles:
            if not c.get("complete", True):
                continue  # Skip the currently open bar
            mid = c.get("mid", {})
            ts = pd.Timestamp(c["time"]).tz_convert("UTC")
            rows.append({
                "timestamp": ts,
                "open":   float(mid.get("o", 0)),
                "high":   float(mid.get("h", 0)),
                "low":    float(mid.get("l", 0)),
                "close":  float(mid.get("c", 0)),
                "volume": float(c.get("volume", 0)),
            })

        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(rows).set_index("timestamp")
        df.index = pd.DatetimeIndex(df.index, tz="UTC")
        return df.astype("float64")

    # ── Conversion Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _instrument_name(pair: str) -> str:
        """Convert pair identifier to OANDA instrument format.

        Examples:
            "XAUUSD" → "XAU_USD"
            "GBPJPY" → "GBP_JPY"
        """
        known = {
            "XAUUSD": "XAU_USD",
            "GBPJPY": "GBP_JPY",
            "EURUSD": "EUR_USD",
            "USDJPY": "USD_JPY",
        }
        if pair in known:
            return known[pair]
        # Generic: insert underscore before the quote currency (last 3 chars)
        if len(pair) == 6:
            return f"{pair[:3]}_{pair[3:]}"
        return pair

    @staticmethod
    def _tf_to_granularity(tf: str) -> str:
        """Convert internal timeframe string to OANDA granularity code.

        Examples:
            "1m"  → "M1"
            "1H"  → "H1"
            "4H"  → "H4"
            "1D"  → "D"
            "1W"  → "W"
        """
        gran = _GRANULARITY.get(tf)
        if gran is None:
            raise ValueError(f"Unsupported timeframe for OANDA: {tf!r}")
        return gran
