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
        """
        if len(atr) == 0 or atr.dropna().empty:
            return

        self._last_atr = float(atr.dropna().iloc[-1])
        cluster_tolerance = 0.5 * self._last_atr
        current_close = float(candles["close"].iloc[-1]) if not candles.empty else 0.0
        current_ts = candles.index[-1] if not candles.empty else None
        if hasattr(current_ts, "to_pydatetime"):
            current_ts = current_ts.to_pydatetime()

        # Build resistance levels from swing high clusters
        resistance_levels = self._cluster_swing_points(swing_highs, cluster_tolerance, SRKind.RESISTANCE)
        # Build support levels from swing low clusters
        support_levels = self._cluster_swing_points(swing_lows, cluster_tolerance, SRKind.SUPPORT)

        # Detect equal highs / lows (liquidity pools)
        eq_highs = self._detect_equal_highs(swing_highs)
        eq_lows = self._detect_equal_lows(swing_lows)

        # Merge all levels — keep existing levels and update; add new ones
        new_levels = resistance_levels + support_levels + eq_highs + eq_lows
        self.levels = new_levels

        # Update statuses based on current close
        if current_ts is not None:
            for level in self.levels:
                if level.status == SRStatus.BROKEN:
                    continue
                if level.kind == SRKind.RESISTANCE:
                    if current_close > level.price:
                        level.status = SRStatus.BROKEN
                        level.last_tested = current_ts
                    elif abs(current_close - level.price) <= cluster_tolerance:
                        level.status = SRStatus.TESTED
                        level.last_tested = current_ts
                elif level.kind == SRKind.SUPPORT:
                    if current_close < level.price:
                        level.status = SRStatus.BROKEN
                        level.last_tested = current_ts
                    elif abs(current_close - level.price) <= cluster_tolerance:
                        level.status = SRStatus.TESTED
                        level.last_tested = current_ts

    def score(self, current_price: float, is_bullish_trend: bool) -> float:
        """
        Score based on current price's position relative to S/R levels.

        Args:
            current_price: Most recent close price.
            is_bullish_trend: Direction from MarketStructureModule HTF state.

        Returns:
            float in [-1.0, +1.0]
        """
        if not self.levels:
            return 0.0

        tolerance = 0.5 * self._last_atr

        if is_bullish_trend:
            # Looking for buy setups: price bouncing at support
            support = self.nearest_support(current_price)
            if support and self._is_near_level(current_price, support):
                if support.strength >= 3:
                    return 0.7   # Strong support bounce
                return 0.5       # Weaker support or price breaking through

            # Price near equal lows (liquidity grab — risky but can signal reversal)
            eq_lows = [l for l in self.levels if l.kind == SRKind.LIQUIDITY_POOL_LOW
                       and self._is_near_level(current_price, l)]
            if eq_lows:
                return 0.4   # Potential liquidity grab (risky)

            # Price broke through resistance (momentum confirmation)
            resistance = self.nearest_resistance(current_price + tolerance)
            if resistance and resistance.status == SRStatus.BROKEN:
                return 0.5
        else:
            # Bearish: price bouncing at resistance
            resistance = self.nearest_resistance(current_price)
            if resistance and self._is_near_level(current_price, resistance):
                if resistance.strength >= 3:
                    return -0.7
                return -0.5

            # Price near equal highs (liquidity grab)
            eq_highs = [l for l in self.levels if l.kind == SRKind.LIQUIDITY_POOL_HIGH
                        and self._is_near_level(current_price, l)]
            if eq_highs:
                return -0.4

            # Price broke through support (bearish momentum)
            support = self.nearest_support(current_price - tolerance)
            if support and support.status == SRStatus.BROKEN:
                return -0.5

        return 0.0

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
        XAUUSD: tolerance = 0.03% of price. GBPJPY: 5 pips (0.05).
        """
        pools: list[SRLevel] = []
        if len(swing_highs) < 2:
            return pools

        for i in range(len(swing_highs) - 1):
            p1 = swing_highs[i].price
            p2 = swing_highs[i + 1].price
            if self.pair == "XAUUSD":
                tol = p1 * EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT
            else:
                tol = EQUAL_HIGHS_TOLERANCE_GBPJPY_PIPS * 0.01

            if abs(p1 - p2) <= tol:
                avg_price = (p1 + p2) / 2.0
                ts = swing_highs[i].timestamp
                pools.append(SRLevel(
                    price=avg_price,
                    kind=SRKind.LIQUIDITY_POOL_HIGH,
                    status=SRStatus.INTACT,
                    strength=2,
                    first_seen=ts,
                    tolerance_atr=0.5,
                ))
        return pools

    def _detect_equal_lows(self, swing_lows: list) -> list[SRLevel]:
        """Find consecutive swing lows within tolerance = liquidity pool below."""
        pools: list[SRLevel] = []
        if len(swing_lows) < 2:
            return pools

        for i in range(len(swing_lows) - 1):
            p1 = swing_lows[i].price
            p2 = swing_lows[i + 1].price
            if self.pair == "XAUUSD":
                tol = p1 * EQUAL_HIGHS_TOLERANCE_XAUUSD_PCT
            else:
                tol = EQUAL_HIGHS_TOLERANCE_GBPJPY_PIPS * 0.01

            if abs(p1 - p2) <= tol:
                avg_price = (p1 + p2) / 2.0
                ts = swing_lows[i].timestamp
                pools.append(SRLevel(
                    price=avg_price,
                    kind=SRKind.LIQUIDITY_POOL_LOW,
                    status=SRStatus.INTACT,
                    strength=2,
                    first_seen=ts,
                    tolerance_atr=0.5,
                ))
        return pools

    def _cluster_swing_points(
        self, swing_points: list, tolerance: float, kind: SRKind
    ) -> list[SRLevel]:
        """
        Group swing points within tolerance of each other into cluster levels.
        Returns one SRLevel per cluster with strength = number of points in cluster.
        """
        if not swing_points:
            return []

        levels: list[SRLevel] = []
        used = [False] * len(swing_points)

        for i, sp in enumerate(swing_points):
            if used[i]:
                continue
            cluster = [sp]
            used[i] = True
            for j in range(i + 1, len(swing_points)):
                if not used[j] and abs(swing_points[j].price - sp.price) <= tolerance:
                    cluster.append(swing_points[j])
                    used[j] = True

            avg_price = sum(p.price for p in cluster) / len(cluster)
            levels.append(SRLevel(
                price=avg_price,
                kind=kind,
                status=SRStatus.INTACT,
                strength=len(cluster),
                first_seen=cluster[0].timestamp,
                tolerance_atr=0.5,
            ))
        return levels
