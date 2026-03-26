"""
Order Blocks Module — Weight: 20% (XAU) / 18% (GJ)

Detects institutional entry zones (Order Blocks) and their mitigation status.
An OB is the last opposing candle before a displacement move.

Sprint 3 deliverable: full implementation with OB + FVG overlap detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd


class OBKind(str, Enum):
    BULLISH = "BULLISH"   # Last bearish candle before bullish displacement
    BEARISH = "BEARISH"   # Last bullish candle before bearish displacement


class OBStatus(str, Enum):
    ACTIVE = "ACTIVE"           # Unmitigated, still valid
    MITIGATED = "MITIGATED"     # Price returned and filled >50% of zone
    EXPIRED = "EXPIRED"         # Exceeded max active OB count or age limit


@dataclass
class OrderBlock:
    timestamp: datetime
    kind: OBKind
    high: float
    low: float
    body_high: float          # Open/close max (tighter zone)
    body_low: float           # Open/close min
    displacement_size: float  # Displacement candle range in ATR multiples
    volume_above_avg: bool    # True if displacement had above-average volume
    caused_bos: bool          # True if OB preceded a BOS/CHoCH
    has_fvg: bool             # True if OB left an associated FVG
    status: OBStatus = OBStatus.ACTIVE
    mitigation_pct: float = 0.0  # 0.0–1.0, how much of zone has been filled


# Maximum number of active OBs tracked per timeframe
MAX_ACTIVE_OBS = 5

# Displacement threshold in ATR multiples
DISPLACEMENT_ATR_MULTIPLE = 2.0

# OB scan lookback: how far back to look for the opposing candle
OB_LOOKBACK = 20


class OrderBlockModule:
    """
    Detects and tracks Order Blocks across a timeframe.

    Usage:
        module = OrderBlockModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df, atr_series)
        score = module.score(current_price)
    """

    def __init__(self, timeframe: str, pair: str):
        self.timeframe = timeframe
        self.pair = pair
        self.active_obs: list[OrderBlock] = []

    def update(self, candles: pd.DataFrame, atr: pd.Series) -> None:
        """
        Detect new Order Blocks and update mitigation status of existing ones.

        Args:
            candles: OHLCV DataFrame sorted ascending.
            atr: ATR(14) series aligned to candles index.
        """
        existing_ts = {ob.timestamp for ob in self.active_obs}
        displacement_mask = self._detect_displacement(candles, atr)

        opens = candles["open"].values
        closes = candles["close"].values
        highs = candles["high"].values
        lows = candles["low"].values

        has_volume = "volume" in candles.columns
        volumes = candles["volume"].values if has_volume else None

        new_obs: list[OrderBlock] = []

        for i in range(1, len(candles)):
            if not bool(displacement_mask.iloc[i]):
                continue

            is_bullish_disp = float(closes[i]) > float(opens[i])
            atr_val = float(atr.iloc[i]) if i < len(atr) else 1.0
            if atr_val <= 0:
                atr_val = 1.0
            displacement_size = (float(highs[i]) - float(lows[i])) / atr_val

            # Find last opposing candle before this displacement
            ob_idx = None
            scan_start = max(0, i - OB_LOOKBACK)
            for j in range(i - 1, scan_start - 1, -1):
                if is_bullish_disp:
                    if float(closes[j]) < float(opens[j]):  # bearish = bullish OB
                        ob_idx = j
                        break
                else:
                    if float(closes[j]) > float(opens[j]):  # bullish = bearish OB
                        ob_idx = j
                        break

            if ob_idx is None:
                continue

            ob_ts = candles.index[ob_idx]
            if isinstance(ob_ts, pd.Timestamp):
                ob_ts = ob_ts.to_pydatetime()

            if ob_ts in existing_ts:
                continue

            # Check has_fvg: three-candle FVG where OB=C1, displacement=C2, next=C3
            has_fvg = False
            if i + 1 < len(candles):
                if is_bullish_disp:
                    has_fvg = float(lows[i + 1]) > float(highs[ob_idx])
                else:
                    has_fvg = float(highs[i + 1]) < float(lows[ob_idx])

            # Volume check: displacement volume vs rolling average
            if has_volume and volumes is not None:
                window_start = max(0, i - 20)
                avg_vol = float(candles["volume"].iloc[window_start:i].mean()) if i > window_start else 1.0
                volume_above_avg = avg_vol > 0 and float(volumes[i]) > avg_vol
            else:
                volume_above_avg = True  # Cannot verify without volume data

            # caused_bos: approximated by whether displacement broke recent extreme
            lookback_end = max(0, i - 20)
            if is_bullish_disp:
                recent_high = float(candles["high"].iloc[lookback_end:i].max()) if i > lookback_end else 0.0
                caused_bos = float(closes[i]) > recent_high
            else:
                recent_low = float(candles["low"].iloc[lookback_end:i].min()) if i > lookback_end else float("inf")
                caused_bos = float(closes[i]) < recent_low

            ob = OrderBlock(
                timestamp=ob_ts,
                kind=OBKind.BULLISH if is_bullish_disp else OBKind.BEARISH,
                high=float(highs[ob_idx]),
                low=float(lows[ob_idx]),
                body_high=float(max(opens[ob_idx], closes[ob_idx])),
                body_low=float(min(opens[ob_idx], closes[ob_idx])),
                displacement_size=displacement_size,
                volume_above_avg=volume_above_avg,
                caused_bos=caused_bos,
                has_fvg=has_fvg,
            )
            new_obs.append(ob)
            existing_ts.add(ob_ts)

        self.active_obs.extend(new_obs)
        self._update_mitigation(candles)

        # Expire oldest OBs beyond the cap
        active = [ob for ob in self.active_obs if ob.status == OBStatus.ACTIVE]
        if len(active) > MAX_ACTIVE_OBS:
            for ob in active[:-MAX_ACTIVE_OBS]:
                ob.status = OBStatus.EXPIRED

    def score(self, current_price: float) -> float:
        """
        Score based on whether price is at an active, unmitigated OB.

        Returns:
            +0.9  — price at active bullish OB
            +1.0  — price at bullish OB with associated FVG (Unicorn)
            -0.9  — price at active bearish OB
            -1.0  — price at bearish OB with associated FVG
            -0.2  — price at mitigated bullish OB zone (warning)
            +0.2  — price at mitigated bearish OB zone (warning)
             0.0  — no relevant OB near current price
        """
        for ob in reversed(self.active_obs):
            if ob.status == OBStatus.ACTIVE and ob.low <= current_price <= ob.high:
                if ob.kind == OBKind.BULLISH:
                    return 1.0 if ob.has_fvg else 0.9
                else:
                    return -1.0 if ob.has_fvg else -0.9

        # Mitigated zone warning
        for ob in self.active_obs:
            if ob.status == OBStatus.MITIGATED and ob.low <= current_price <= ob.high:
                return -0.2 if ob.kind == OBKind.BULLISH else 0.2

        return 0.0

    def get_active_obs(self) -> list[OrderBlock]:
        """Return list of currently active (unmitigated) OBs."""
        return [ob for ob in self.active_obs if ob.status == OBStatus.ACTIVE]

    def nearest_ob(self, current_price: float) -> Optional[OrderBlock]:
        """Return the nearest unmitigated OB to current price, or None."""
        active = self.get_active_obs()
        if not active:
            return None
        return min(
            active,
            key=lambda ob: min(
                abs(current_price - ob.high),
                abs(current_price - ob.low),
            ),
        )

    def _detect_displacement(self, candles: pd.DataFrame, atr: pd.Series) -> pd.Series:
        """
        Identify displacement candles: range >= 2x ATR(14).
        Returns boolean Series aligned to candles index.
        """
        bar_range = candles["high"] - candles["low"]
        return bar_range >= (DISPLACEMENT_ATR_MULTIPLE * atr)

    def _update_mitigation(self, candles: pd.DataFrame) -> None:
        """
        Update mitigation status for all active OBs.
        An OB is mitigated when price closes through 50%+ of the zone (past midpoint).
        """
        for ob in self.active_obs:
            if ob.status != OBStatus.ACTIVE:
                continue

            midpoint = (ob.high + ob.low) / 2.0
            ob_ts = pd.Timestamp(ob.timestamp)

            if candles.index.tz is not None and ob_ts.tz is None:
                ob_ts = ob_ts.tz_localize(candles.index.tz)
            elif candles.index.tz is None and ob_ts.tz is not None:
                ob_ts = ob_ts.tz_localize(None)

            post = candles[candles.index > ob_ts]
            if len(post) == 0:
                continue

            zone_size = ob.high - ob.low
            if zone_size <= 0:
                continue

            if ob.kind == OBKind.BULLISH:
                # Mitigated when price closes below midpoint (> 50% penetration)
                if (post["close"] < midpoint).any():
                    ob.status = OBStatus.MITIGATED
                    ob.mitigation_pct = 1.0
                else:
                    # Track partial penetration depth
                    min_low = float(post["low"].min())
                    if min_low < ob.high:
                        depth = (ob.high - max(min_low, ob.low)) / zone_size
                        ob.mitigation_pct = max(ob.mitigation_pct, min(depth, 1.0))
            else:
                # BEARISH OB: mitigated when price closes above midpoint
                if (post["close"] > midpoint).any():
                    ob.status = OBStatus.MITIGATED
                    ob.mitigation_pct = 1.0
                else:
                    max_high = float(post["high"].max())
                    if max_high > ob.low:
                        depth = (min(max_high, ob.high) - ob.low) / zone_size
                        ob.mitigation_pct = max(ob.mitigation_pct, min(depth, 1.0))
