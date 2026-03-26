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
        """
        existing_ts = {fvg.timestamp for fvg in self.fvgs}
        highs = candles["high"].values
        lows = candles["low"].values
        new_fvgs: list[FairValueGap] = []

        for i in range(2, len(candles)):
            # Middle candle (Candle 2) timestamp identifies this FVG
            ts = candles.index[i - 1]
            if isinstance(ts, pd.Timestamp):
                ts = ts.to_pydatetime()

            if ts in existing_ts:
                continue

            atr_val = float(atr.iloc[i - 1]) if i - 1 < len(atr) else 1.0
            if atr_val <= 0:
                hl = float(highs[i - 1]) - float(lows[i - 1])
                atr_val = hl if hl > 0 else 1.0

            c1_high = float(highs[i - 2])
            c1_low = float(lows[i - 2])
            c3_low = float(lows[i])
            c3_high = float(highs[i])

            # Bullish FVG: gap between Candle 1 high and Candle 3 low
            if c3_low > c1_high:
                gap = c3_low - c1_high
                if gap >= self.min_size_atr_multiple * atr_val:
                    new_fvgs.append(FairValueGap(
                        timestamp=ts,
                        kind=FVGKind.BULLISH,
                        top=c3_low,
                        bottom=c1_high,
                        midpoint=(c3_low + c1_high) / 2.0,
                        size_atr=gap / atr_val,
                    ))
                    existing_ts.add(ts)
                    continue

            # Bearish FVG: gap between Candle 3 high and Candle 1 low
            if c3_high < c1_low:
                gap = c1_low - c3_high
                if gap >= self.min_size_atr_multiple * atr_val:
                    new_fvgs.append(FairValueGap(
                        timestamp=ts,
                        kind=FVGKind.BEARISH,
                        top=c1_low,
                        bottom=c3_high,
                        midpoint=(c1_low + c3_high) / 2.0,
                        size_atr=gap / atr_val,
                    ))
                    existing_ts.add(ts)

        self.fvgs.extend(new_fvgs)
        self._update_fill_status(candles)

    def score(self, current_price: float) -> float:
        """
        Score based on whether price is at an open or partially-filled FVG.

        Returns:
            +0.7  — price inside open/partial bullish FVG
            -0.7  — price inside open/partial bearish FVG
            -0.3  — price at inverted FVG (resistance)
             0.0  — no relevant FVG
        """
        for fvg in reversed(self.fvgs):
            if fvg.status in (FVGStatus.OPEN, FVGStatus.PARTIALLY_FILLED):
                if fvg.bottom <= current_price <= fvg.top:
                    return 0.7 if fvg.kind == FVGKind.BULLISH else -0.7
            elif fvg.status == FVGStatus.INVERTED:
                if fvg.bottom <= current_price <= fvg.top:
                    return -0.3
        return 0.0

    def check_unicorn_overlap(self, ob_high: float, ob_low: float) -> bool:
        """
        Check if any open FVG overlaps with the given OB zone.
        Returns True if overlap found — signals ICT Unicorn Setup (1.10x multiplier).
        """
        for fvg in self.fvgs:
            if fvg.status in (FVGStatus.OPEN, FVGStatus.PARTIALLY_FILLED):
                if fvg.bottom <= ob_high and fvg.top >= ob_low:
                    return True
        return False

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

        Bullish FVG: fill when price low enters [bottom, top]; FILLED when close < bottom.
        Bearish FVG: fill when price high enters [bottom, top]; FILLED when close > top.
        """
        for fvg in self.fvgs:
            if fvg.status in (FVGStatus.FILLED, FVGStatus.INVERTED):
                continue

            fvg_ts = pd.Timestamp(fvg.timestamp)
            # Align timezone
            if candles.index.tz is not None and fvg_ts.tz is None:
                fvg_ts = fvg_ts.tz_localize(candles.index.tz)
            elif candles.index.tz is None and fvg_ts.tz is not None:
                fvg_ts = fvg_ts.tz_localize(None)

            post = candles[candles.index > fvg_ts]
            if len(post) == 0:
                continue

            zone_size = fvg.top - fvg.bottom
            if zone_size <= 0:
                continue

            if fvg.kind == FVGKind.BULLISH:
                # Fill: price descends into gap from above
                for low, close in zip(post["low"], post["close"]):
                    low, close = float(low), float(close)
                    if close < fvg.bottom:
                        fvg.status = FVGStatus.FILLED
                        fvg.fill_pct = 1.0
                        break
                    elif low < fvg.top:
                        depth = fvg.top - max(low, fvg.bottom)
                        fvg.fill_pct = max(fvg.fill_pct, depth / zone_size)
                        fvg.status = FVGStatus.PARTIALLY_FILLED
            else:
                # Fill: price ascends into gap from below
                for high, close in zip(post["high"], post["close"]):
                    high, close = float(high), float(close)
                    if close > fvg.top:
                        fvg.status = FVGStatus.FILLED
                        fvg.fill_pct = 1.0
                        break
                    elif high > fvg.bottom:
                        depth = min(high, fvg.top) - fvg.bottom
                        fvg.fill_pct = max(fvg.fill_pct, depth / zone_size)
                        fvg.status = FVGStatus.PARTIALLY_FILLED
