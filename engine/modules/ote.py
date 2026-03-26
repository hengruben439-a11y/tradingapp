"""
Optimal Trade Entry (OTE) Fibonacci Module — Weight: 15% (XAU + GJ)

Applies Fibonacci retracement to the most recent dealing range (swing H→L or L→H).
The OTE zone is 0.618–0.786 retracement. Sweet spot: 0.705.

Sprint 3 deliverable: full OTE scoring with confluence boost flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd


# Fibonacci retracement levels tracked
FIB_LEVELS = {
    "0.0":   0.000,
    "0.236": 0.236,
    "0.382": 0.382,
    "0.500": 0.500,
    "0.618": 0.618,
    "0.705": 0.705,
    "0.786": 0.786,
    "1.0":   1.000,
}

# Fibonacci extension levels (for TP projection)
FIB_EXTENSIONS = {
    "-0.27":  -0.270,
    "-0.618": -0.618,
    "-1.0":   -1.000,
}

# OTE zone boundaries
OTE_LOWER = 0.618
OTE_UPPER = 0.786
OTE_SWEET_SPOT = 0.705


@dataclass
class DealingRange:
    """A swing high → swing low (or vice versa) range used for Fibonacci projection."""
    start_timestamp: datetime
    end_timestamp: datetime
    swing_high: float
    swing_low: float
    is_bullish: bool   # True = retracement of bullish leg (price pulled back, look for buy OTE)

    def fib_level(self, ratio: float) -> float:
        """Calculate price at a given Fibonacci ratio."""
        rng = self.swing_high - self.swing_low
        if self.is_bullish:
            # Bullish: 0.0 = swing_high, 1.0 = swing_low
            return self.swing_high - (ratio * rng)
        else:
            # Bearish: 0.0 = swing_low, 1.0 = swing_high
            return self.swing_low + (ratio * rng)

    @property
    def ote_high(self) -> float:
        return self.fib_level(OTE_LOWER)

    @property
    def ote_low(self) -> float:
        return self.fib_level(OTE_UPPER)

    @property
    def ote_sweet_spot(self) -> float:
        return self.fib_level(OTE_SWEET_SPOT)

    def sl_level(self, buffer_pct: float = 0.0005) -> float:
        """
        Stop loss beyond the 100% retracement level.
        buffer_pct: percentage of price to add as stop hunt protection.
        """
        raw = self.fib_level(1.0)
        if self.is_bullish:
            return raw * (1.0 - buffer_pct)
        else:
            return raw * (1.0 + buffer_pct)

    def tp_extension(self, ratio: float) -> float:
        """Calculate TP level at a Fibonacci extension (e.g. -0.618)."""
        rng = self.swing_high - self.swing_low
        if self.is_bullish:
            return self.swing_high + (abs(ratio) * rng)
        else:
            return self.swing_low - (abs(ratio) * rng)


class OTEModule:
    """
    Applies Fibonacci retracement to identify Optimal Trade Entry zones.

    Usage:
        module = OTEModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df, swing_highs, swing_lows)
        score = module.score(current_price)
        ob_confluence = module.has_ob_confluence(ob_high, ob_low)
    """

    def __init__(self, timeframe: str, pair: str):
        self.timeframe = timeframe
        self.pair = pair
        self.current_range: Optional[DealingRange] = None

    def update(
        self,
        candles: pd.DataFrame,
        swing_highs: list,
        swing_lows: list,
    ) -> None:
        """
        Identify the most recent significant dealing range from swing points.

        Args:
            candles: OHLCV DataFrame sorted ascending.
            swing_highs: List of SwingPoint (from MarketStructureModule).
            swing_lows: List of SwingPoint (from MarketStructureModule).

        Sprint 3 implementation notes:
        - Find the most recent significant swing high and swing low
        - Determine direction: is price retracing a bullish or bearish leg?
        - Set self.current_range to the new DealingRange
        - Reset if a CHoCH invalidates the previous range
        """
        raise NotImplementedError("Implement in Sprint 3")

    def score(self, current_price: float) -> float:
        """
        Score based on price position relative to OTE zone.

        Returns:
            +1.0  — price at/near OTE sweet spot (0.705)
            +0.8  — price within OTE zone (0.618–0.786)
            +0.4  — price in 0.5–0.618 zone (partial confluence)
             0.0  — price outside OTE range or no dealing range set
        """
        raise NotImplementedError("Implement in Sprint 3")

    def has_ob_confluence(self, ob_high: float, ob_low: float) -> bool:
        """
        Check if an Order Block zone overlaps with the current OTE zone.
        Returns True → 1.08x multiplier applies.
        """
        if self.current_range is None:
            return False
        ote_h = max(self.current_range.ote_high, self.current_range.ote_low)
        ote_l = min(self.current_range.ote_high, self.current_range.ote_low)
        return ob_low <= ote_h and ob_high >= ote_l

    def has_fvg_confluence(self, fvg_top: float, fvg_bottom: float) -> bool:
        """
        Check if an FVG zone overlaps with the current OTE zone.
        Returns True → 1.06x multiplier applies.
        """
        if self.current_range is None:
            return False
        ote_h = max(self.current_range.ote_high, self.current_range.ote_low)
        ote_l = min(self.current_range.ote_high, self.current_range.ote_low)
        return fvg_bottom <= ote_h and fvg_top >= ote_l

    def get_tp_levels(self) -> dict[str, float]:
        """
        Return TP levels at Fibonacci extensions for the current dealing range.
        Returns empty dict if no dealing range is set.
        """
        if self.current_range is None:
            return {}
        return {
            "tp_ext_0.27":  self.current_range.tp_extension(-0.27),
            "tp_ext_0.618": self.current_range.tp_extension(-0.618),
            "tp_ext_1.0":   self.current_range.tp_extension(-1.0),
        }
