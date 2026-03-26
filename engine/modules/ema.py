"""
EMA Alignment Module — Weight: 10% (XAU) / 12% (GJ)

Tracks EMA 20/50/100/200 stack alignment and Golden/Death Cross events.
Perfect bullish stack: price > EMA20 > EMA50 > EMA100 > EMA200 = +1.0

Sprint 4 deliverable: full implementation.
"""

from __future__ import annotations

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

        Sprint 4 implementation notes:
        - EMA formula: K = 2/(period+1); EMA_t = price_t*K + EMA_{t-1}*(1-K)
        - Use pandas .ewm(span=period, adjust=False).mean() for vectorized calc
        - Detect Golden/Death Cross: EMA50 crossing EMA200 (check last bar vs prev bar)
        - Store latest EMA values in self._last_values
        - Increment self._current_bar
        """
        raise NotImplementedError("Implement in Sprint 4")

    def score(self) -> float:
        """
        Return directional score based on EMA alignment.

        Returns:
            float in [-1.0, +1.0]
        """
        raise NotImplementedError("Implement in Sprint 4")

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

        Sprint 4 implementation:
        - Check price vs 20 vs 50 vs 100 vs 200 ordering
        - Count how many consecutive pairs are in the right order
        - Scale from 0.0 to 1.0 (or negative for bearish)
        """
        raise NotImplementedError("Implement in Sprint 4")
