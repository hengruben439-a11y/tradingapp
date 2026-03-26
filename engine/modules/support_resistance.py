"""
Support & Resistance / Liquidity Levels Module — Weight: 5% (XAU + GJ)

Identifies key S/R zones from swing clusters and equal highs/lows (liquidity pools).
Prices approaching strong S/R in trade direction and bouncing score higher.

Sprint 5 deliverable: full implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd


class SRKind(str, Enum):
    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"
    LIQUIDITY_POOL_HIGH = "LIQUIDITY_POOL_HIGH"   # Equal highs = buy stops resting above
    LIQUIDITY_POOL_LOW = "LIQUIDITY_POOL_LOW"     # Equal lows = sell stops resting below


class SRStatus(str, Enum):
    INTACT = "INTACT"       # Price has not touched this level
    TESTED = "TESTED"       # Price touched but didn't break
    BROKEN = "BROKEN"       # Price closed through this level
    FLIPPED = "FLIPPED"     # Resistance became support (or vice versa)


@dataclass
class SRLevel:
    price: float
    kind: SRKind
    status: SRStatus
    strength: int             # Number of swing point touches (3+ = strong)
    first_seen: datetime
    last_tested: Optional[datetime] = None
    tolerance_atr: float = 0.5  # Price tolerance for "near" detection (in ATR)


# Equal highs/lows proximity thresholds (from config)
EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT = 0.0003   # 0.03% of price
EQUAL_HIGHS_TOLERANCE_GBPJPY_PIPS = 5       # 5 pips


class SupportResistanceModule:
    """
    Identifies swing-based S/R clusters and equal high/low liquidity pools.

    Score logic:
        Price approaching strong S/R in trend direction and bouncing: +0.7
        Price breaking through S/R (confirms momentum): +0.5
        Price near equal highs/lows (liquidity grab risk): +0.4 (flagged as risky)
        No relevant S/R near current price: 0.0

    Usage:
        module = SupportResistanceModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df, swing_highs, swing_lows, atr)
        score = module.score(current_price, is_bullish_trend=True)
    """

    def __init__(self, timeframe: str, pair: str):
        self.timeframe = timeframe
        self.pair = pair
        self.levels: list[SRLevel] = []
        self._last_atr: float = 1.0

    def update(
        self,
        candles: pd.DataFrame,
        swing_highs: list,
        swing_lows: list,
        atr: pd.Series,
    ) -> None:
        """
        Build and update S/R levels from swing point clusters.

        Args:
            candles: OHLCV DataFrame sorted ascending.
            swing_highs: List of SwingPoint from MarketStructureModule.
            swing_lows: List of SwingPoint from MarketStructureModule.
            atr: ATR(14) series for tolerance calculations.

        Sprint 5 implementation notes:
        - Cluster swing points within 0.5x ATR of each other → strong S/R
        - 3+ touches in cluster = strong level (strength >= 3)
        - Detect equal highs: consecutive swing highs within tolerance = liquidity pool
        - Update status: BROKEN when price closes through level
        - Flip support→resistance or vice versa on confirmed break
        """
        raise NotImplementedError("Implement in Sprint 5")

    def score(self, current_price: float, is_bullish_trend: bool) -> float:
        """
        Score based on current price's position relative to S/R levels.

        Args:
            current_price: Most recent close price.
            is_bullish_trend: Direction from MarketStructureModule HTF state.

        Returns:
            float in [-1.0, +1.0]
        """
        raise NotImplementedError("Implement in Sprint 5")

    def nearest_support(self, price: float) -> Optional[SRLevel]:
        """Return the nearest intact support level below current price."""
        supports = [l for l in self.levels if l.kind == SRKind.SUPPORT and l.status == SRStatus.INTACT and l.price < price]
        return max(supports, key=lambda l: l.price) if supports else None

    def nearest_resistance(self, price: float) -> Optional[SRLevel]:
        """Return the nearest intact resistance level above current price."""
        resistances = [l for l in self.levels if l.kind == SRKind.RESISTANCE and l.status == SRStatus.INTACT and l.price > price]
        return min(resistances, key=lambda l: l.price) if resistances else None

    def get_liquidity_pools(self) -> list[SRLevel]:
        """Return all identified liquidity pool levels (equal highs/lows)."""
        return [l for l in self.levels if l.kind in (SRKind.LIQUIDITY_POOL_HIGH, SRKind.LIQUIDITY_POOL_LOW)]

    def _is_near_level(self, price: float, level: SRLevel) -> bool:
        """True if price is within tolerance_atr * ATR of the level."""
        return abs(price - level.price) <= level.tolerance_atr * self._last_atr

    def _detect_equal_highs(self, swing_highs: list) -> list[SRLevel]:
        """
        Find consecutive swing highs within tolerance = liquidity pool above.

        Sprint 5 implementation:
        - XAUUSD: tolerance = EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT * price
        - GBPJPY: tolerance = EQUAL_HIGHS_TOLERANCE_GBPJPY_PIPS * pip_value
        """
        raise NotImplementedError("Implement in Sprint 5")
