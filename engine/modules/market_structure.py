"""
Market Structure Module — Weight: 25% (XAU + GJ)

Detects Break of Structure (BOS) and Change of Character (CHoCH) by tracking
swing highs and lows. Maintains a state machine per timeframe.

Sprint 2 deliverable: full implementation with 200+ labeled test cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd


class TrendState(str, Enum):
    UNKNOWN = "UNKNOWN"            # Insufficient history to establish trend
    BULLISH_TREND = "BULLISH_TREND"
    BEARISH_TREND = "BEARISH_TREND"
    RANGING = "RANGING"
    TRANSITIONING = "TRANSITIONING"


class StructureEvent(str, Enum):
    BOS_BULLISH = "BOS_BULLISH"    # Continuation break up
    BOS_BEARISH = "BOS_BEARISH"    # Continuation break down
    CHOCH_BULLISH = "CHOCH_BULLISH"  # Reversal: bearish → bullish
    CHOCH_BEARISH = "CHOCH_BEARISH"  # Reversal: bullish → bearish


@dataclass
class SwingPoint:
    timestamp: datetime
    price: float
    kind: str          # "high" | "low"
    confirmed: bool    # True once N candles on both sides have been seen


@dataclass
class StructureEventRecord:
    event: StructureEvent
    price: float
    timestamp: datetime
    swing_ref: SwingPoint
    displacement_size: float  # size of the candle that caused the break (in ATR multiples)


# Module score lookup by state and last event
_SCORE_MAP: dict[tuple[TrendState, Optional[StructureEvent]], float] = {
    (TrendState.UNKNOWN, None): 0.0,
    (TrendState.BULLISH_TREND, StructureEvent.BOS_BULLISH): 0.8,
    (TrendState.BULLISH_TREND, StructureEvent.CHOCH_BULLISH): 1.0,   # pre-cap; aggregator caps to 0.85
    (TrendState.BEARISH_TREND, StructureEvent.BOS_BEARISH): -0.8,
    (TrendState.BEARISH_TREND, StructureEvent.CHOCH_BEARISH): -1.0,  # pre-cap
    (TrendState.RANGING, None): 0.0,
    (TrendState.TRANSITIONING, None): 0.3,   # sign determined by pending direction
}


class MarketStructureModule:
    """
    Swing-point based trend tracker with BOS/CHoCH detection.

    Usage:
        module = MarketStructureModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df)
        score = module.score()
    """

    def __init__(self, timeframe: str, pair: str):
        self.timeframe = timeframe
        self.pair = pair
        self.state: TrendState = TrendState.UNKNOWN
        self.swing_highs: list[SwingPoint] = []
        self.swing_lows: list[SwingPoint] = []
        self.events: list[StructureEventRecord] = []
        self._atr_series: Optional[pd.Series] = None

    def update(self, candles: pd.DataFrame) -> None:
        """
        Process new candle data and update internal state.

        Args:
            candles: OHLCV DataFrame with columns [open, high, low, close, volume].
                     Must be sorted ascending by timestamp index.
                     Minimum length: lookback_n * 2 + 1 candles.

        Sprint 2 implementation notes:
        - Use _detect_swing_points() with pair-specific lookback N from config
        - Detect BOS when close crosses most recent swing in trend direction
        - Detect CHoCH when close crosses swing point against trend
        - Require CHoCH displacement >= 1.5x ATR to filter noise
        - RANGING state: 3+ swing points within 1.5x ATR band
        """
        raise NotImplementedError("Implement in Sprint 2")

    def score(self) -> float:
        """
        Return the module's directional score in range [-1.0, +1.0].
        Values > 0.85 are valid (aggregator applies the 0.85 cap).

        Returns:
            float: Positive = bullish bias, Negative = bearish bias, 0.0 = neutral.
        """
        raise NotImplementedError("Implement in Sprint 2")

    def latest_event(self) -> Optional[StructureEventRecord]:
        """Return the most recent structural event, or None."""
        return self.events[-1] if self.events else None

    def _detect_swing_points(self, candles: pd.DataFrame) -> None:
        """
        Find swing highs and lows using N-candle lookback from config.
        A swing high is confirmed when N candles on both sides have lower highs.

        Sprint 2 implementation: vectorized pandas operation.
        """
        raise NotImplementedError("Implement in Sprint 2")

    def _score_from_state(self) -> float:
        """Map current state + latest event to a directional score."""
        event = self.latest_event()
        event_type = event.event if event else None
        key = (self.state, event_type)
        base = _SCORE_MAP.get(key, 0.0)
        # TRANSITIONING: sign determined by direction of the CHoCH that triggered it
        if self.state == TrendState.TRANSITIONING and event:
            sign = 1.0 if event.event == StructureEvent.CHOCH_BULLISH else -1.0
            return sign * abs(base)
        return base
