"""
Fair Value Gap (FVG) Module — Part of OB+FVG module (combined weight: 20%/18%)

Three-candle pattern where price moved so fast it left an imbalance gap.
Tracks creation, fill status, and inversion.

Sprint 3 deliverable: full implementation with Unicorn (OB+FVG overlap) detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd


class FVGKind(str, Enum):
    BULLISH = "BULLISH"   # Candle[3].low > Candle[1].high
    BEARISH = "BEARISH"   # Candle[3].high < Candle[1].low


class FVGStatus(str, Enum):
    OPEN = "OPEN"                         # Gap not yet touched
    PARTIALLY_FILLED = "PARTIALLY_FILLED" # Price entered but didn't close through
    FILLED = "FILLED"                     # Price closed through entire gap
    INVERTED = "INVERTED"                 # Breached; now acting as opposite S/R


@dataclass
class FairValueGap:
    timestamp: datetime           # Timestamp of the middle candle (Candle 2)
    kind: FVGKind
    top: float                    # Upper boundary of the gap
    bottom: float                 # Lower boundary of the gap
    midpoint: float               # 50% level (Consequent Encroachment)
    size_atr: float               # Gap size expressed as ATR multiples
    status: FVGStatus = FVGStatus.OPEN
    fill_pct: float = 0.0         # 0.0–1.0, how much of gap is filled


class FVGModule:
    """
    Detects and tracks Fair Value Gaps across a timeframe.

    FVG minimum sizes (from config):
        1m/5m  = 0.5x ATR
        15m/30m = 0.75x ATR
        1H/4H  = 1.0x ATR
        1D     = 1.5x ATR
        1W     = 2.0x ATR

    Usage:
        module = FVGModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df, atr_series)
        score = module.score(current_price)
        has_unicorn = module.check_unicorn_overlap(ob_high, ob_low)
    """

    def __init__(self, timeframe: str, pair: str, min_size_atr_multiple: float = 1.0):
        self.timeframe = timeframe
        self.pair = pair
        self.min_size_atr_multiple = min_size_atr_multiple
        self.fvgs: list[FairValueGap] = []

    def update(self, candles: pd.DataFrame, atr: pd.Series) -> None:
        """
        Scan for new FVGs and update fill status of existing ones.

        Args:
            candles: OHLCV DataFrame sorted ascending.
            atr: ATR(14) series aligned to candles index.

        Sprint 3 implementation notes:
        - Scan every 3-candle window: check [i-2].high vs [i].low (bullish)
          and [i-2].low vs [i].high (bearish)
        - Filter: gap size >= self.min_size_atr_multiple * ATR
        - Update fill status: track price penetration into each open FVG
        - Mark INVERTED if price closes through fully and reversal follows
        """
        raise NotImplementedError("Implement in Sprint 3")

    def score(self, current_price: float) -> float:
        """
        Score based on whether price is at an open or partially-filled FVG.

        Returns:
            +0.7  — price entering bullish FVG (in trend direction)
            +1.0  — Unicorn: FVG overlaps with an active OB (passed externally)
             0.0  — no relevant FVG
            -0.3  — price at inverted FVG (potential resistance)
        """
        raise NotImplementedError("Implement in Sprint 3")

    def check_unicorn_overlap(self, ob_high: float, ob_low: float) -> bool:
        """
        Check if any open FVG overlaps with the given OB zone.
        Returns True if overlap found — signals ICT Unicorn Setup (1.10x multiplier).
        """
        raise NotImplementedError("Implement in Sprint 3")

    def nearest_fvg(self, current_price: float) -> Optional[FairValueGap]:
        """Return the nearest open/partially-filled FVG to current price."""
        candidates = [f for f in self.fvgs if f.status in (FVGStatus.OPEN, FVGStatus.PARTIALLY_FILLED)]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda f: min(abs(current_price - f.top), abs(current_price - f.bottom)),
        )

    def get_open_fvgs(self) -> list[FairValueGap]:
        """Return all FVGs that have not been fully filled."""
        return [f for f in self.fvgs if f.status in (FVGStatus.OPEN, FVGStatus.PARTIALLY_FILLED)]

    def _update_fill_status(self, candles: pd.DataFrame) -> None:
        """
        For each open FVG, check how much it has been filled by recent price action.
        Track Consequent Encroachment (CE) at midpoint as a key reaction level.

        Sprint 3 implementation notes:
        - For bullish FVG: fill when price low dips into [bottom, top] range
        - fill_pct = (top - lowest_price_in_fvg) / (top - bottom)
        - FILLED when price closes below bottom (bullish) or above top (bearish)
        """
        raise NotImplementedError("Implement in Sprint 3")
