"""
TP/SL Hybrid Calculation Engine — Sprint 5 deliverable.

Calculates entry price, stop loss, and three take-profit levels using a hybrid
of structural (swing-based) and ATR-based methods.

Stop Loss Algorithm:
    Method 1 (Structural): SL beyond nearest structural invalidation point
    Method 2 (ATR-based):  SL = Entry ± 1.5x ATR(14)
    Final SL: whichever is tighter, but bounded to [1x ATR, 3x ATR]
    Buffer: 5–10 pips (GBPJPY) or 0.03–0.07% of price (XAUUSD)
    If SL > 3x ATR: downgrade signal strength by 20%

Take Profit Algorithm:
    TP1 (40%): MIN(nearest S/R, 1.0x risk) — must be >= 1:1 R:R
    TP2 (30%): MIN(next S/R or opposing OB, 2.0x risk)
    TP3 (30%): MAX(major liquidity, Fib -0.618 extension, 3.0x risk)
    Fallback:  TP1=1.5xATR, TP2=2.5xATR, TP3=4.0xATR
    Validation: TP1 < 1:1 R:R → suppress signal entirely
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from engine.signal import Direction, TPLevel


# SL multiplier bounds
SL_MIN_ATR_MULTIPLE = 1.0
SL_MAX_ATR_MULTIPLE = 3.0
SL_DEFAULT_ATR_MULTIPLE = 1.5

# SL stop-hunt buffers
SL_BUFFER_GBPJPY_PIPS = 7       # Mid-range of 5–10 pips
SL_BUFFER_XAUUSD_PCT = 0.0005   # 0.05% of price (mid-range of 0.03–0.07%)

# TP ATR fallback multiples
TP1_ATR_FALLBACK = 1.5
TP2_ATR_FALLBACK = 2.5
TP3_ATR_FALLBACK = 4.0

# TP partial close percentages
TP1_CLOSE_PCT = 0.40
TP2_CLOSE_PCT = 0.30
TP3_CLOSE_PCT = 0.30

# Minimum R:R for TP1 (else suppress signal)
MIN_TP1_RR = 1.0

# SL downgrade threshold
SL_DOWNGRADE_ATR_THRESHOLD = 3.0
SL_DOWNGRADE_FACTOR = 0.80   # Reduce score by 20%

# Pip values for lot size calculations
PIP_VALUES: dict[str, float] = {
    "XAUUSD": 1.0,    # $1.00 per pip per 0.1 lot (tick size = $0.01)
    "GBPJPY": 0.70,   # ~$0.70 per pip per 0.01 lot at standard JPY rates
}


@dataclass
class TPSLResult:
    entry_price: float
    stop_loss: float
    tp1: TPLevel
    tp2: TPLevel
    tp3: TPLevel
    sl_distance_pips: float
    sl_distance_atr_multiple: float
    used_structural_sl: bool
    sl_is_excessive: bool    # True if SL > 3x ATR (signal should be downgraded)
    used_fallback_tp: bool   # True if structural TPs weren't found


class TPSLEngine:
    """
    Hybrid TP/SL calculator that combines structural levels with ATR bounds.

    Usage:
        engine = TPSLEngine(pair="XAUUSD")
        result = engine.calculate(
            entry_price=2050.0,
            direction=Direction.BUY,
            atr=15.0,
            support_levels=[2035.0, 2020.0],
            resistance_levels=[2075.0, 2100.0],
            fib_extensions={"tp_ext_0.618": 2080.0},
            swing_invalidation=2028.0,
        )
    """

    def __init__(self, pair: str):
        self.pair = pair

    def calculate(
        self,
        entry_price: float,
        direction: Direction,
        atr: float,
        support_levels: list[float],
        resistance_levels: list[float],
        fib_extensions: dict[str, float],
        swing_invalidation: Optional[float] = None,
    ) -> Optional[TPSLResult]:
        """
        Calculate entry, SL, and three TP levels.

        Returns None if TP1 cannot achieve minimum 1:1 R:R (signal is suppressed).
        """
        # Step 1: Calculate SL
        sl_raw, used_structural, sl_excessive = self._calculate_sl(
            entry_price, direction, atr, swing_invalidation
        )
        sl_price = self._add_sl_buffer(sl_raw, direction, entry_price)

        # Step 2: Risk distance
        risk_distance = abs(entry_price - sl_price)
        if risk_distance <= 0:
            return None

        # Determine TP target levels (above entry for BUY, below for SELL)
        if direction == Direction.BUY:
            tp_levels_src = resistance_levels
            tp_sign = 1.0
        else:
            tp_levels_src = support_levels
            tp_sign = -1.0

        # Filter: TP targets must be in the correct direction from entry
        if direction == Direction.BUY:
            valid_structural = sorted([l for l in tp_levels_src if l > entry_price])
        else:
            valid_structural = sorted([l for l in tp_levels_src if l < entry_price], reverse=True)

        used_fallback = len(valid_structural) == 0

        # TP1: nearest S/R or 1.0x risk
        tp1_atr = entry_price + tp_sign * TP1_ATR_FALLBACK * atr
        if valid_structural:
            tp1_struct = valid_structural[0]
            # Take whichever is closer to entry (more conservative)
            if abs(tp1_struct - entry_price) < abs(tp1_atr - entry_price):
                tp1_price = tp1_struct
                tp1_source = "structural"
            else:
                tp1_price = entry_price + tp_sign * 1.0 * risk_distance
                tp1_source = "atr_fallback"
        else:
            tp1_price = tp1_atr
            tp1_source = "atr_fallback"

        # TP1 must achieve at least 1:1 R:R
        tp1_rr = abs(tp1_price - entry_price) / risk_distance
        if tp1_rr < MIN_TP1_RR:
            return None

        # TP2: next S/R or 2.0x risk
        tp2_atr = entry_price + tp_sign * TP2_ATR_FALLBACK * atr
        if len(valid_structural) >= 2:
            tp2_struct = valid_structural[1]
            tp2_price = tp2_struct
            tp2_source = "structural"
        elif len(valid_structural) == 1 and abs(valid_structural[0] - entry_price) < abs(tp2_atr - entry_price):
            tp2_price = entry_price + tp_sign * 2.0 * risk_distance
            tp2_source = "atr_fallback"
        else:
            tp2_price = tp2_atr
            tp2_source = "atr_fallback"

        # TP3: Fib extension or major liquidity or 3.0x risk
        tp3_atr = entry_price + tp_sign * TP3_ATR_FALLBACK * atr
        fib_key = "tp_ext_0.618"
        if fib_key in fib_extensions:
            fib_val = fib_extensions[fib_key]
            if (direction == Direction.BUY and fib_val > entry_price) or \
               (direction == Direction.SELL and fib_val < entry_price):
                tp3_price = fib_val
                tp3_source = "fibonacci_extension"
            else:
                tp3_price = tp3_atr
                tp3_source = "atr_fallback"
        elif len(valid_structural) >= 3:
            tp3_price = valid_structural[2]
            tp3_source = "structural"
        else:
            tp3_price = tp3_atr
            tp3_source = "atr_fallback"

        # Build result
        sl_pips = self._price_to_pips(risk_distance)
        sl_atr_multiple = risk_distance / atr if atr > 0 else 0.0

        return TPSLResult(
            entry_price=entry_price,
            stop_loss=sl_price,
            tp1=TPLevel(level=1, price=tp1_price, rr_ratio=round(abs(tp1_price - entry_price) / risk_distance, 2),
                        close_pct=TP1_CLOSE_PCT, source=tp1_source),
            tp2=TPLevel(level=2, price=tp2_price, rr_ratio=round(abs(tp2_price - entry_price) / risk_distance, 2),
                        close_pct=TP2_CLOSE_PCT, source=tp2_source),
            tp3=TPLevel(level=3, price=tp3_price, rr_ratio=round(abs(tp3_price - entry_price) / risk_distance, 2),
                        close_pct=TP3_CLOSE_PCT, source=tp3_source),
            sl_distance_pips=round(sl_pips, 1),
            sl_distance_atr_multiple=round(sl_atr_multiple, 2),
            used_structural_sl=used_structural,
            sl_is_excessive=sl_excessive,
            used_fallback_tp=used_fallback,
        )

    def calculate_lot_size(
        self,
        account_balance: float,
        risk_pct: float,
        sl_distance_pips: float,
    ) -> tuple[float, float]:
        """
        Calculate position size and dollar risk.

        Formula: lot_size = (balance × risk_pct) / (sl_pips × pip_value)

        Returns:
            (lot_size, dollar_risk)
        """
        dollar_risk = account_balance * (risk_pct / 100.0)
        pip_value = PIP_VALUES.get(self.pair, 1.0)
        if sl_distance_pips <= 0 or pip_value <= 0:
            return 0.0, dollar_risk
        lot_size = dollar_risk / (sl_distance_pips * pip_value)
        return round(lot_size, 2), round(dollar_risk, 2)

    def _calculate_sl(
        self,
        entry_price: float,
        direction: Direction,
        atr: float,
        swing_invalidation: Optional[float],
    ) -> tuple[float, bool, bool]:
        """
        Calculate stop loss using structural (preferred) and ATR methods.

        Returns:
            (sl_price, used_structural, is_excessive)
        """
        atr_sl_distance = SL_DEFAULT_ATR_MULTIPLE * atr

        if direction == Direction.BUY:
            atr_sl = entry_price - atr_sl_distance
        else:
            atr_sl = entry_price + atr_sl_distance

        structural_sl = None
        if swing_invalidation is not None:
            structural_sl = swing_invalidation

        if structural_sl is not None:
            # Use whichever is tighter (closer to entry)
            struct_dist = abs(entry_price - structural_sl)
            if struct_dist < atr_sl_distance:
                sl_price = structural_sl
                used_structural = True
            else:
                sl_price = atr_sl
                used_structural = False
        else:
            sl_price = atr_sl
            used_structural = False

        # Enforce bounds: [1x ATR, 3x ATR] from entry
        actual_dist = abs(entry_price - sl_price)
        min_dist = SL_MIN_ATR_MULTIPLE * atr
        max_dist = SL_MAX_ATR_MULTIPLE * atr

        if actual_dist < min_dist:
            sl_price = entry_price - min_dist if direction == Direction.BUY else entry_price + min_dist
        elif actual_dist > max_dist:
            sl_price = entry_price - max_dist if direction == Direction.BUY else entry_price + max_dist

        is_excessive = abs(entry_price - sl_price) > SL_DOWNGRADE_ATR_THRESHOLD * atr
        return sl_price, used_structural, is_excessive

    def _add_sl_buffer(self, sl_price: float, direction: Direction, entry_price: float) -> float:
        """
        Add stop hunt buffer beyond the raw SL level.
        XAUUSD: percentage-based (0.05% of price)
        GBPJPY: fixed pip buffer (7 pips)
        """
        if self.pair == "XAUUSD":
            buffer = entry_price * SL_BUFFER_XAUUSD_PCT
        else:
            buffer = SL_BUFFER_GBPJPY_PIPS * 0.01   # 7 pips in GJ decimal

        if direction == Direction.BUY:
            return sl_price - buffer
        else:
            return sl_price + buffer

    def _find_nearest_level(
        self,
        price: float,
        direction: Direction,
        levels: list[float],
        beyond_rr: float,
        risk_distance: float,
    ) -> Optional[float]:
        """
        Find the nearest S/R level in the direction of the trade
        at a target R:R distance. Falls back to ATR multiple if no level found.

        """
        if not levels:
            return None

        target_distance = beyond_rr * risk_distance

        if direction == Direction.BUY:
            candidates = sorted([l for l in levels if l > price + target_distance * 0.5])
        else:
            candidates = sorted([l for l in levels if l < price - target_distance * 0.5], reverse=True)

        return candidates[0] if candidates else None

    def _price_to_pips(self, distance: float) -> float:
        """Convert price distance to pips for the configured pair."""
        if self.pair == "GBPJPY":
            return distance * 100.0   # JPY pair: 0.01 = 1 pip
        elif self.pair == "XAUUSD":
            return distance * 10.0    # Gold: 0.1 = 1 pip ($0.10)
        return distance
