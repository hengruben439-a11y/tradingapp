"""
MACD Module — Weight: 7% (XAU + GJ)

Standard MACD (12, 26, 9) with crossover and histogram divergence detection.
Prioritizes crossovers near the zero line (stronger momentum shifts).

Sprint 4 deliverable: full implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd


class MACDSignalKind(str, Enum):
    BULLISH_CROSSOVER_NEAR_ZERO = "BULLISH_CROSSOVER_NEAR_ZERO"   # Strongest
    BULLISH_CROSSOVER_FAR_ZERO = "BULLISH_CROSSOVER_FAR_ZERO"     # Weaker
    BEARISH_CROSSOVER_NEAR_ZERO = "BEARISH_CROSSOVER_NEAR_ZERO"
    BEARISH_CROSSOVER_FAR_ZERO = "BEARISH_CROSSOVER_FAR_ZERO"
    HISTOGRAM_BULLISH_DIVERGENCE = "HISTOGRAM_BULLISH_DIVERGENCE"
    HISTOGRAM_BEARISH_DIVERGENCE = "HISTOGRAM_BEARISH_DIVERGENCE"
    HISTOGRAM_RISING = "HISTOGRAM_RISING"
    HISTOGRAM_FALLING = "HISTOGRAM_FALLING"
    NEUTRAL = "NEUTRAL"


@dataclass
class MACDState:
    macd_line: float
    signal_line: float
    histogram: float
    latest_signal: MACDSignalKind


# Threshold for "near zero line" classification
NEAR_ZERO_THRESHOLD_ATR_PCT = 0.05   # Within 5% of ATR range from zero


class MACDModule:
    """
    MACD momentum scoring.

    Score logic:
        Bullish crossover near zero line: +0.8
        Bullish crossover far from zero: +0.4
        Histogram increasing (positive, getting larger): +0.3
        Histogram bearish divergence (price HH, histogram LH): -0.6
        Bearish crossover near zero: -0.8
        Bearish crossover far: -0.4
        No crossover, flat histogram: 0.0

    Usage:
        module = MACDModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df)
        score = module.score()
    """

    def __init__(
        self,
        timeframe: str,
        pair: str,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ):
        self.timeframe = timeframe
        self.pair = pair
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self._state: Optional[MACDState] = None
        self._macd_line: Optional[pd.Series] = None
        self._signal_line: Optional[pd.Series] = None
        self._histogram: Optional[pd.Series] = None

    def update(self, candles: pd.DataFrame) -> None:
        """
        Calculate MACD components and detect crossover/divergence events.

        Args:
            candles: OHLCV DataFrame sorted ascending.
                     Minimum length: slow + signal + divergence_lookback bars.

        Sprint 4 implementation notes:
        - MACD Line = EMA(fast) - EMA(slow)
        - Signal Line = EMA(signal_period) of MACD Line
        - Histogram = MACD Line - Signal Line
        - Crossover: MACD was below Signal last bar, now above = bullish cross
        - Near zero: |MACD Line| < NEAR_ZERO_THRESHOLD_ATR_PCT * current_atr
        - Histogram divergence: price makes new high but histogram peak is lower
        """
        raise NotImplementedError("Implement in Sprint 4")

    def score(self) -> float:
        """
        Return directional MACD score.

        Returns:
            float in [-1.0, +1.0]
        """
        raise NotImplementedError("Implement in Sprint 4")

    @property
    def current_state(self) -> Optional[MACDState]:
        """Return the most recently computed MACD state."""
        return self._state

    def is_bullish_momentum(self) -> bool:
        """True if histogram is positive and increasing."""
        if self._state is None:
            return False
        return (
            self._state.histogram > 0
            and self._state.latest_signal in (
                MACDSignalKind.HISTOGRAM_RISING,
                MACDSignalKind.BULLISH_CROSSOVER_NEAR_ZERO,
                MACDSignalKind.BULLISH_CROSSOVER_FAR_ZERO,
            )
        )

    def _detect_histogram_divergence(
        self,
        candles: pd.DataFrame,
        histogram: pd.Series,
        lookback: int = 10,
    ) -> Optional[MACDSignalKind]:
        """
        Detect MACD histogram divergence by comparing price extremes
        vs histogram extremes over the last `lookback` bars.

        Sprint 4 implementation.
        """
        raise NotImplementedError("Implement in Sprint 4")
