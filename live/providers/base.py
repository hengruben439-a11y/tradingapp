"""Base class for market data providers."""

from __future__ import annotations

import abc
from typing import Callable, Optional

import pandas as pd


class DataFeedError(Exception):
    """Raised when a data provider encounters an unrecoverable feed error."""


class BaseDataProvider(abc.ABC):
    """
    Abstract base class for market data providers.

    Concrete implementations (OANDA, Twelve Data) must implement all abstract
    methods. The on_bar_close callback is fired by the provider whenever a bar
    closes on one of the subscribed timeframes.

    Callback signature:
        on_bar_close(pair: str, tf: str, bar: pd.Series) -> None
        where bar is a single OHLCV row with a UTC-aware Timestamp as name.
    """

    def __init__(self) -> None:
        self._on_bar_close: Optional[Callable[[str, str, pd.Series], None]] = None
        self._is_connected: bool = False

    # ── Callback property ─────────────────────────────────────────────────────

    @property
    def on_bar_close(self) -> Optional[Callable[[str, str, pd.Series], None]]:
        """Callback fired on every confirmed bar close: (pair, tf, bar_series)."""
        return self._on_bar_close

    @on_bar_close.setter
    def on_bar_close(self, callback: Callable[[str, str, pd.Series], None]) -> None:
        self._on_bar_close = callback

    # ── Connection state ──────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """True if the provider has an active, validated connection."""
        return self._is_connected

    # ── Abstract interface ────────────────────────────────────────────────────

    @abc.abstractmethod
    async def connect(self) -> None:
        """
        Establish and validate the provider connection.

        Raises:
            DataFeedError: If credentials are invalid or the endpoint is unreachable.
        """

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Cleanly shut down the provider, cancelling any background tasks."""

    @abc.abstractmethod
    async def subscribe(self, pair: str, timeframes: list[str]) -> None:
        """
        Subscribe to bar-close events for the given pair and timeframes.

        Args:
            pair: Instrument identifier, e.g. "XAUUSD" or "GBPJPY".
            timeframes: List of timeframe strings, e.g. ["1m", "5m", "1H"].

        Raises:
            DataFeedError: If the subscription cannot be established.
        """

    @abc.abstractmethod
    async def get_latest_candles(
        self,
        pair: str,
        tf: str,
        n: int = 500,
    ) -> pd.DataFrame:
        """
        Return the most recent N closed candles for the pair/timeframe.

        Args:
            pair: Instrument identifier, e.g. "XAUUSD".
            tf: Timeframe string, e.g. "15m", "1H", "4H".
            n: Number of candles to fetch (default 500).

        Returns:
            DataFrame with columns [open, high, low, close, volume] and a
            UTC-aware DatetimeIndex. Rows are sorted oldest-first.

        Raises:
            DataFeedError: On API error or insufficient data.
        """
