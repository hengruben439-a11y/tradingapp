"""
EMA Alignment Module — Weight: 10% (XAU) / 12% (GJ)

Tracks EMA 20/50/100/200 stack alignment and Golden/Death Cross events.
Perfect bullish stack: price > EMA20 > EMA50 > EMA100 > EMA200 = +1.0

Sprint 4 deliverable: full implementation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class CrossEvent(str, Enum):
    GOLDEN_CROSS = "GOLDEN_CROSS"   # EMA50 crosses above EMA200
    DEATH_CROSS = "DEATH_CROSS"     # EMA50 crosses below EMA200


# Number of bars a cross event boosts/drags the score
CROSS_BOOST_BARS = 20
CROSS_BOOST_MAGNITUDE = 0.3


@dataclass
class CrossRecord:
    event: CrossEvent
    bar_index: int   # Bar number when cross occurred


class EMAModule:
    """
    Tracks EMA alignment across 20/50/100/200 periods.

    Score logic:
        Perfect Bullish (price > 20 > 50 > 100 > 200): +1.0
        Partial Bullish (price > 200 but stack not perfect): +0.5
        Perfect Bearish (price < 20 < 50 < 100 < 200): -1.0
        Partial Bearish: -0.5
        Ranging (no clear order): 0.0
        Golden Cross within last 20 bars: +0.3 additional
        Death Cross within last 20 bars: -0.3 additional

    Usage:
        module = EMAModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df)
        score = module.score()
    """

    PERIODS = [20, 50, 100, 200]

    def __init__(self, timeframe: str, pair: str):
        self.timeframe = timeframe
        self.pair = pair
        self._ema: dict[int, Optional[pd.Series]] = {p: None for p in self.PERIODS}
        self._last_values: dict[int, float] = {}
        self._last_price: float = 0.0
        self._cross_history: list[CrossRecord] = []
        self._current_bar: int = 0

    def update(self, candles: pd.DataFrame) -> None:
        """
        Calculate EMAs and detect Golden/Death Cross events.

        Args:
            candles: OHLCV DataFrame with at least 200 rows for full EMA warmup.
        """
        if candles.empty:
            return

        closes = candles["close"]

        for period in self.PERIODS:
            self._ema[period] = closes.ewm(span=period, adjust=False).mean()
            self._last_values[period] = float(self._ema[period].iloc[-1])

        self._last_price = float(closes.iloc[-1])
        self._current_bar = len(candles)

        # Detect Golden/Death Cross by scanning full EMA history.
        # Skip warmup period (first 200 bars) to avoid initialization artifacts
        # where both EMAs start at the same value and diverge on bar 1.
        ema50 = self._ema[50]
        ema200 = self._ema[200]
        if ema50 is not None and ema200 is not None and len(ema50) >= 2:
            e50 = ema50.values
            e200 = ema200.values
            new_crosses: list[CrossRecord] = []
            warmup = min(200, len(e50) - 1)
            for i in range(warmup, len(e50)):
                if any(math.isnan(v) for v in (e50[i], e50[i-1], e200[i], e200[i-1])):
                    continue
                if e50[i-1] <= e200[i-1] and e50[i] > e200[i]:
                    new_crosses.append(CrossRecord(CrossEvent.GOLDEN_CROSS, i))
                elif e50[i-1] >= e200[i-1] and e50[i] < e200[i]:
                    new_crosses.append(CrossRecord(CrossEvent.DEATH_CROSS, i))
            self._cross_history = new_crosses

    def score(self) -> float:
        """
        Return directional score based on EMA alignment.

        Returns:
            float in [-1.0, +1.0]
        """
        if not self._last_values or len(self._last_values) < len(self.PERIODS):
            return 0.0

        stack_score = self._score_stack()

        # Add cross boost if recent
        cross = self.recent_cross()
        if cross is not None:
            if cross.event == CrossEvent.GOLDEN_CROSS:
                stack_score = min(1.0, stack_score + CROSS_BOOST_MAGNITUDE)
            else:
                stack_score = max(-1.0, stack_score - CROSS_BOOST_MAGNITUDE)

        return stack_score

    def is_above_ema200(self) -> bool:
        """True if last price is above EMA 200 (macro bullish bias)."""
        ema200 = self._last_values.get(200)
        if ema200 is None:
            return False
        return self._last_price > ema200

    def recent_cross(self) -> Optional[CrossRecord]:
        """Return the most recent cross event if within CROSS_BOOST_BARS, else None."""
        if not self._cross_history:
            return None
        last = self._cross_history[-1]
        if self._current_bar - last.bar_index <= CROSS_BOOST_BARS:
            return last
        return None

    def _score_stack(self) -> float:
        """
        Evaluate how well-stacked the EMAs are.

        Checks ordering of: price > EMA20 > EMA50 > EMA100 > EMA200
        Returns +1.0 for perfect bullish, -1.0 for perfect bearish,
        +0.5/-0.5 for partial, 0.0 for no clear order.
        """
        vals = self._last_values
        if len(vals) < len(self.PERIODS):
            return 0.0

        p = self._last_price
        e20 = vals[20]
        e50 = vals[50]
        e100 = vals[100]
        e200 = vals[200]

        # Perfect bullish: price > EMA20 > EMA50 > EMA100 > EMA200
        if p > e20 > e50 > e100 > e200:
            return 1.0

        # Perfect bearish: price < EMA20 < EMA50 < EMA100 < EMA200
        if p < e20 < e50 < e100 < e200:
            return -1.0

        # Partial: price above EMA200 (macro bullish) but stack not perfect
        if p > e200:
            return 0.5

        # Partial: price below EMA200 (macro bearish) but stack not perfect
        if p < e200:
            return -0.5

        return 0.0
