"""
RSI Module — Weight: 8% (XAU + GJ)

14-period RSI with overbought/oversold detection and divergence detection.
Thresholds are timeframe-dependent (scalping: 65/35, others: 70/30 etc.)

Sprint 4 deliverable: full implementation including divergence detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd


class DivergenceKind(str, Enum):
    BULLISH_REGULAR = "BULLISH_REGULAR"     # Price LL, RSI HL → reversal buy
    BEARISH_REGULAR = "BEARISH_REGULAR"     # Price HH, RSI LH → reversal sell
    BULLISH_HIDDEN = "BULLISH_HIDDEN"       # Price HL, RSI LL → continuation buy
    BEARISH_HIDDEN = "BEARISH_HIDDEN"       # Price LH, RSI HH → continuation sell


@dataclass
class DivergenceRecord:
    kind: DivergenceKind
    timestamp: datetime
    price_level: float
    rsi_level: float


# RSI thresholds per timeframe group (from config/parameters.yaml)
RSI_THRESHOLDS: dict[str, tuple[float, float]] = {
    "1m":  (65.0, 35.0),
    "5m":  (65.0, 35.0),
    "15m": (70.0, 30.0),
    "30m": (70.0, 30.0),
    "1H":  (70.0, 30.0),
    "4H":  (70.0, 30.0),
    "1D":  (75.0, 25.0),
    "1W":  (80.0, 20.0),
}

# Divergence lookback bars per timeframe group
DIVERGENCE_LOOKBACK: dict[str, int] = {
    "1m":  5,
    "5m":  8,
    "15m": 10,
    "30m": 12,
    "1H":  15,
    "4H":  18,
    "1D":  20,
    "1W":  20,
}


class RSIModule:
    """
    RSI-based momentum and divergence scoring.

    Score logic:
        RSI oversold (< lower threshold): +0.6 to +1.0 (scaled by extremity)
        RSI overbought (> upper threshold): -0.6 to -1.0
        Neutral zone (40–60): 0.0
        Bullish Regular Divergence: +0.8
        Bearish Regular Divergence: -0.8
        Bullish Hidden Divergence (trend continuation): +0.5
        Bearish Hidden Divergence: -0.5

    Usage:
        module = RSIModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df)
        score = module.score()
    """

    def __init__(self, timeframe: str, pair: str, period: int = 14):
        self.timeframe = timeframe
        self.pair = pair
        self.period = period
        self._rsi: Optional[pd.Series] = None
        self._latest_rsi: float = 50.0
        self._divergences: list[DivergenceRecord] = []

        # Get thresholds for this timeframe
        thresholds = RSI_THRESHOLDS.get(timeframe, (70.0, 30.0))
        self.overbought = thresholds[0]
        self.oversold = thresholds[1]
        self.lookback = DIVERGENCE_LOOKBACK.get(timeframe, 14)

    def update(self, candles: pd.DataFrame) -> None:
        """
        Calculate RSI and scan for divergences.

        Args:
            candles: OHLCV DataFrame sorted ascending. Min length: period + lookback.

        Sprint 4 implementation notes:
        - RSI = 100 - (100 / (1 + RS))
        - RS = avg_gain / avg_loss over period using Wilder's smoothing
        - Use pandas: gain = diff().clip(lower=0), loss = diff().clip(upper=0).abs()
        - Rolling avg: .ewm(com=period-1, adjust=False).mean()
        - Scan for divergence using self.lookback bars
        """
        raise NotImplementedError("Implement in Sprint 4")

    def score(self) -> float:
        """
        Return directional score based on RSI level and detected divergences.

        Divergence scores take precedence over raw OB/OS readings.
        """
        raise NotImplementedError("Implement in Sprint 4")

    @property
    def latest_rsi(self) -> float:
        """Return the most recently calculated RSI value."""
        return self._latest_rsi

    def is_oversold(self) -> bool:
        return self._latest_rsi < self.oversold

    def is_overbought(self) -> bool:
        return self._latest_rsi > self.overbought

    def latest_divergence(self) -> Optional[DivergenceRecord]:
        """Return the most recent divergence signal, or None."""
        return self._divergences[-1] if self._divergences else None

    def _calculate_rsi(self, closes: pd.Series) -> pd.Series:
        """
        Wilder's smoothed RSI calculation.
        Returns RSI series aligned to closes index.

        Sprint 4 implementation.
        """
        raise NotImplementedError("Implement in Sprint 4")

    def _detect_divergence(self, candles: pd.DataFrame, rsi: pd.Series) -> None:
        """
        Scan recent bars for regular and hidden RSI divergence.

        Sprint 4 implementation notes:
        - Find local price highs/lows over self.lookback window
        - Compare price extremes vs RSI extremes at same pivots
        - Regular bullish: price makes lower low, RSI makes higher low
        - Hidden bullish: price makes higher low, RSI makes lower low
        - Only flag divergences where the pivot separation is >= 3 bars
        """
        raise NotImplementedError("Implement in Sprint 4")

    def _scale_extreme_score(self, rsi_value: float) -> float:
        """
        Scale oversold/overbought intensity to a 0.6–1.0 score.
        More extreme RSI = higher score magnitude.

        Sprint 4 implementation:
        - Oversold: 0.6 at threshold, 1.0 at 10 (absolute extreme)
        - Overbought: -0.6 at threshold, -1.0 at 90
        """
        raise NotImplementedError("Implement in Sprint 4")
