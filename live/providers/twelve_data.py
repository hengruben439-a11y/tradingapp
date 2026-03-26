"""
Twelve Data API provider — fallback when OANDA is unavailable.

Config (from env):
    TWELVE_DATA_API_KEY: API key

Heartbeat monitoring: if primary hasn't sent data in 2x expected interval,
the EngineRunner switches to this provider automatically.

Twelve Data REST time_series endpoint returns OHLCV candles for all
timeframes in a single call. No streaming API is used; polling is used
to detect bar closes, matching the OANDA provider pattern.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
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

_TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"

# Twelve Data interval strings for each internal timeframe
_INTERVAL: dict[str, str] = {
    "1m":  "1min",
    "5m":  "5min",
    "15m": "15min",
    "30m": "30min",
    "1H":  "1h",
    "4H":  "4h",
    "1D":  "1day",
    "1W":  "1week",
}

# Polling intervals in seconds (same schedule as OANDA)
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

_MAX_RETRIES = 5


class TwelveDataProvider(BaseDataProvider):
    """
    Twelve Data REST API market data provider.

    Serves as automatic fallback when the OANDA primary feed is stale.
    Implements the same BaseDataProvider interface as OANDAProvider,
    including polling-based bar close detection.
    """

    def __init__(self) -> None:
        super().__init__()
        if not _HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for TwelveDataProvider. Install with: pip install httpx"
            )

        self._api_key: str = os.environ.get("TWELVE_DATA_API_KEY", "")
        self._client: Optional[httpx.AsyncClient] = None
        self._poll_tasks: list[asyncio.Task] = []
        self._last_seen: dict[tuple[str, str], Optional[datetime]] = {}

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Validate Twelve Data credentials with a lightweight API check."""
        if not self._api_key:
            raise DataFeedError(
                "Twelve Data API key missing. Set TWELVE_DATA_API_KEY env var."
            )

        self._client = httpx.AsyncClient(
            base_url=_TWELVE_DATA_BASE_URL,
            timeout=30.0,
        )

        # Light validation: fetch a tiny slice to confirm credentials
        try:
            resp = await self._client.get(
                "/time_series",
                params={
                    "symbol": "XAU/USD",
                    "interval": "1day",
                    "outputsize": 1,
                    "apikey": self._api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "error":
                await self._client.aclose()
                self._client = None
                raise DataFeedError(
                    f"Twelve Data authentication failed: {data.get('message', 'unknown error')}"
                )
        except httpx.RequestError as exc:
            await self._client.aclose()
            self._client = None
            raise DataFeedError(f"Twelve Data connection error: {exc}") from exc

        self._is_connected = True
        logger.info("TwelveDataProvider connected")

    async def disconnect(self) -> None:
        """Cancel polling tasks and close the HTTP client."""
        self._is_connected = False
        for task in self._poll_tasks:
            task.cancel()
        if self._poll_tasks:
            await asyncio.gather(*self._poll_tasks, return_exceptions=True)
        self._poll_tasks.clear()
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("TwelveDataProvider disconnected")

    # ── Subscription ──────────────────────────────────────────────────────────

    async def subscribe(self, pair: str, timeframes: list[str]) -> None:
        """Start polling loops for each (pair, tf) combination."""
        if not self._is_connected:
            raise DataFeedError(
                "TwelveDataProvider.connect() must be called before subscribe()."
            )

        for tf in timeframes:
            if tf not in _POLL_INTERVAL:
                logger.warning("TwelveDataProvider: unknown timeframe %r — skipping", tf)
                continue
            key = (pair, tf)
            if key in self._last_seen:
                logger.debug("Already subscribed to %s %s", pair, tf)
                continue
            self._last_seen[key] = None
            task = asyncio.create_task(
                self._poll_loop(pair, tf),
                name=f"twelvedata_poll_{pair}_{tf}",
            )
            self._poll_tasks.append(task)
            logger.info(
                "TwelveDataProvider: subscribed to %s %s (poll every %ds)",
                pair, tf, _POLL_INTERVAL[tf],
            )

    # ── Data Fetch ────────────────────────────────────────────────────────────

    async def get_latest_candles(
        self,
        pair: str,
        tf: str,
        n: int = 500,
    ) -> pd.DataFrame:
        """Fetch the N most recent closed candles via Twelve Data time_series."""
        if self._client is None:
            raise DataFeedError("TwelveDataProvider is not connected.")

        symbol = self._symbol(pair)
        interval = self._interval(tf)

        params = {
            "symbol":     symbol,
            "interval":   interval,
            "outputsize": min(n, 5000),
            "order":      "ASC",
            "timezone":   "UTC",
            "apikey":     self._api_key,
        }

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await self._client.get("/time_series", params=params)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") == "error":
                    raise DataFeedError(
                        f"Twelve Data API error: {data.get('message', 'unknown')}"
                    )

                return self._parse_candles(data.get("values", []))

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (429, 503):
                    wait = 2 ** attempt
                    logger.warning(
                        "Twelve Data rate-limited (attempt %d/%d) — backing off %ds",
                        attempt, _MAX_RETRIES, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise DataFeedError(
                        f"Twelve Data HTTP error {exc.response.status_code}: {exc.response.text}"
                    ) from exc
            except httpx.RequestError as exc:
                wait = 2 ** attempt
                logger.warning(
                    "Twelve Data request error on attempt %d/%d: %s — retrying in %ds",
                    attempt, _MAX_RETRIES, exc, wait,
                )
                await asyncio.sleep(wait)

        raise DataFeedError(
            f"Twelve Data candle fetch failed after {_MAX_RETRIES} retries for {pair} {tf}"
        )

    # ── Poll Loop ─────────────────────────────────────────────────────────────

    async def _poll_loop(self, pair: str, tf: str) -> None:
        """
        Continuously poll Twelve Data for new closed candles.

        Compares the latest candle timestamp against _last_seen. When a new
        closed candle is detected, fires on_bar_close.
        """
        interval = _POLL_INTERVAL[tf]
        key = (pair, tf)

        while self._is_connected:
            try:
                df = await self.get_latest_candles(pair, tf, n=3)
                if df.empty:
                    await asyncio.sleep(interval)
                    continue

                latest_bar = df.iloc[-1]
                latest_ts: datetime = latest_bar.name.to_pydatetime()  # type: ignore[union-attr]

                prev_ts = self._last_seen.get(key)
                if prev_ts is None:
                    self._last_seen[key] = latest_ts
                elif latest_ts > prev_ts:
                    self._last_seen[key] = latest_ts
                    if self._on_bar_close is not None:
                        try:
                            self._on_bar_close(pair, tf, latest_bar)
                        except Exception:
                            logger.exception(
                                "on_bar_close callback raised for %s %s", pair, tf
                            )

            except DataFeedError:
                logger.exception("Twelve Data poll error for %s %s", pair, tf)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    "Unexpected error in Twelve Data poll loop %s %s", pair, tf
                )

            await asyncio.sleep(interval)

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_candles(self, values: list[dict]) -> pd.DataFrame:
        """
        Parse Twelve Data time_series values into a standard OHLCV DataFrame.

        Twelve Data returns values newest-first when order is not specified,
        but we request ASC ordering so rows are oldest-first.
        """
        rows = []
        for v in values:
            try:
                ts = pd.Timestamp(v["datetime"]).tz_localize("UTC")
                rows.append({
                    "timestamp": ts,
                    "open":   float(v["open"]),
                    "high":   float(v["high"]),
                    "low":    float(v["low"]),
                    "close":  float(v["close"]),
                    "volume": float(v.get("volume", 0)),
                })
            except (KeyError, ValueError):
                logger.debug("Skipping malformed Twelve Data candle: %s", v)
                continue

        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(rows).set_index("timestamp")
        df.index = pd.DatetimeIndex(df.index, tz="UTC")
        return df.astype("float64")

    # ── Conversion Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _symbol(pair: str) -> str:
        """Convert pair identifier to Twelve Data symbol format.

        Examples:
            "XAUUSD" → "XAU/USD"
            "GBPJPY" → "GBP/JPY"
        """
        known = {
            "XAUUSD": "XAU/USD",
            "GBPJPY": "GBP/JPY",
            "EURUSD": "EUR/USD",
            "USDJPY": "USD/JPY",
        }
        if pair in known:
            return known[pair]
        if len(pair) == 6:
            return f"{pair[:3]}/{pair[3:]}"
        return pair

    @staticmethod
    def _interval(tf: str) -> str:
        """Convert internal timeframe string to Twelve Data interval format.

        Examples:
            "1m"  → "1min"
            "15m" → "15min"
            "1H"  → "1h"
            "4H"  → "4h"
            "1D"  → "1day"
        """
        val = _INTERVAL.get(tf)
        if val is None:
            raise ValueError(f"Unsupported timeframe for Twelve Data: {tf!r}")
        return val
