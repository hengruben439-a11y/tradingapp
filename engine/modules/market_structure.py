"""
Market Structure Module — Weight: 25% (XAU + GJ)

Detects Break of Structure (BOS) and Change of Character (CHoCH) by tracking
swing highs and lows. Maintains a state machine per timeframe.

Sprint 2 deliverable: full implementation with 200+ labeled test cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class TrendState(str, Enum):
    UNKNOWN = "UNKNOWN"            # Insufficient history to establish trend
    BULLISH_TREND = "BULLISH_TREND"
    BEARISH_TREND = "BEARISH_TREND"
    RANGING = "RANGING"
    TRANSITIONING = "TRANSITIONING"


class StructureEvent(str, Enum):
    BOS_BULLISH = "BOS_BULLISH"      # Continuation break up
    BOS_BEARISH = "BOS_BEARISH"      # Continuation break down
    CHOCH_BULLISH = "CHOCH_BULLISH"  # Reversal: bearish → bullish
    CHOCH_BEARISH = "CHOCH_BEARISH"  # Reversal: bullish → bearish


@dataclass
class SwingPoint:
    timestamp: datetime
    price: float
    kind: str          # "high" | "low"
    confirmed: bool    # True once N candles on both sides have been seen


@dataclass
class StructureEventRecord:
    event: StructureEvent
    price: float
    timestamp: datetime
    swing_ref: SwingPoint
    displacement_size: float  # size of the candle that caused the break (in ATR multiples)


# Module score lookup by state and last event
_SCORE_MAP: dict[tuple[TrendState, Optional[StructureEvent]], float] = {
    (TrendState.UNKNOWN, None): 0.0,
    (TrendState.BULLISH_TREND, StructureEvent.BOS_BULLISH): 0.8,
    (TrendState.BULLISH_TREND, StructureEvent.CHOCH_BULLISH): 1.0,   # pre-cap; aggregator caps to 0.85
    (TrendState.BEARISH_TREND, StructureEvent.BOS_BEARISH): -0.8,
    (TrendState.BEARISH_TREND, StructureEvent.CHOCH_BEARISH): -1.0,  # pre-cap
    (TrendState.RANGING, None): 0.0,
    (TrendState.TRANSITIONING, None): 0.3,   # sign determined by pending direction
}

# Lookback N per timeframe for swing point confirmation
_SWING_LOOKBACK: dict[str, int] = {
    "1m":  3,
    "5m":  3,
    "15m": 5,
    "30m": 5,
    "1H":  5,
    "4H":  5,
    "1D":  7,
    "1W":  10,
}

# Default lookback if timeframe not found
_DEFAULT_LOOKBACK = 5

# CHoCH displacement filter: must be >= this many ATR multiples
CHOCH_MIN_DISPLACEMENT_ATR = 1.5

# Ranging detection: 3+ swing points within this ATR band width
RANGING_ATR_BAND = 1.5
RANGING_MIN_SWINGS = 3

# Maximum swing points to retain (prevents unbounded memory growth)
MAX_SWING_HISTORY = 20


class MarketStructureModule:
    """
    Swing-point based trend tracker with BOS/CHoCH detection.

    Usage:
        module = MarketStructureModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df)
        score = module.score()
    """

    def __init__(self, timeframe: str, pair: str):
        self.timeframe = timeframe
        self.pair = pair
        self.state: TrendState = TrendState.UNKNOWN
        self.swing_highs: list[SwingPoint] = []
        self.swing_lows: list[SwingPoint] = []
        self.events: list[StructureEventRecord] = []
        self._atr_series: Optional[pd.Series] = None
        self._n = _SWING_LOOKBACK.get(timeframe, _DEFAULT_LOOKBACK)

    # ── Public API ───────────────────────────────────────────────────────────

    def update(self, candles: pd.DataFrame) -> None:
        """
        Process new candle data and update internal state.

        Args:
            candles: OHLCV DataFrame with columns [open, high, low, close, volume].
                     Must be sorted ascending by timestamp index.
                     Minimum length: _n * 2 + 1 candles.
        """
        if len(candles) < self._n * 2 + 1:
            return   # Insufficient history; stay UNKNOWN

        # Step 1: Compute ATR(14) for displacement and ranging checks
        self._atr_series = _compute_atr(candles, period=14)

        # Step 2: Detect all confirmed swing points
        self._detect_swing_points(candles)

        # Step 3: Not enough swing points yet — stay UNKNOWN
        if len(self.swing_highs) < 2 or len(self.swing_lows) < 2:
            return

        # Step 4: Check for RANGING state
        if self._check_ranging():
            self.state = TrendState.RANGING
            return

        # Step 5: Establish initial trend if UNKNOWN
        if self.state == TrendState.UNKNOWN:
            self._initialize_trend()

        # Step 6: Scan for BOS and CHoCH events on recent bars
        self._scan_for_events(candles)

    def score(self) -> float:
        """
        Return the module's directional score in range [-1.0, +1.0].
        Values > 0.85 are valid (aggregator applies the 0.85 cap).

        Returns:
            float: Positive = bullish bias, Negative = bearish bias, 0.0 = neutral.
        """
        return self._score_from_state()

    def latest_event(self) -> Optional[StructureEventRecord]:
        """Return the most recent structural event, or None."""
        return self.events[-1] if self.events else None

    # ── Swing Point Detection ────────────────────────────────────────────────

    def _detect_swing_points(self, candles: pd.DataFrame) -> None:
        """
        Find swing highs and lows using N-candle lookback.
        A swing high at index i is confirmed when:
            all highs[i-N:i] < highs[i]  AND  all highs[i+1:i+N+1] < highs[i]
        A swing low at index i: symmetric with lows.

        Uses vectorized rolling min/max for efficiency.
        Only processes newly confirmed points (avoids reprocessing history).
        """
        highs = candles["high"].values
        lows = candles["low"].values
        n = self._n

        # We can only confirm swing points up to index (len - n - 1)
        # because we need N candles on the right side
        max_confirmable = len(candles) - n - 1

        # Track which indices we've already processed
        existing_high_ts = {sp.timestamp for sp in self.swing_highs}
        existing_low_ts = {sp.timestamp for sp in self.swing_lows}

        new_highs: list[SwingPoint] = []
        new_lows: list[SwingPoint] = []

        for i in range(n, max_confirmable + 1):
            ts = candles.index[i]
            if isinstance(ts, pd.Timestamp):
                ts = ts.to_pydatetime()

            # Swing High: highs[i] is the highest in window [i-n, i+n]
            if ts not in existing_high_ts:
                left = highs[i - n : i]
                right = highs[i + 1 : i + n + 1]
                if len(left) == n and len(right) == n:
                    if highs[i] > np.max(left) and highs[i] > np.max(right):
                        new_highs.append(SwingPoint(
                            timestamp=ts,
                            price=float(highs[i]),
                            kind="high",
                            confirmed=True,
                        ))

            # Swing Low: lows[i] is the lowest in window [i-n, i+n]
            if ts not in existing_low_ts:
                left_l = lows[i - n : i]
                right_l = lows[i + 1 : i + n + 1]
                if len(left_l) == n and len(right_l) == n:
                    if lows[i] < np.min(left_l) and lows[i] < np.min(right_l):
                        new_lows.append(SwingPoint(
                            timestamp=ts,
                            price=float(lows[i]),
                            kind="low",
                            confirmed=True,
                        ))

        self.swing_highs.extend(new_highs)
        self.swing_lows.extend(new_lows)

        # Trim to max history
        if len(self.swing_highs) > MAX_SWING_HISTORY:
            self.swing_highs = self.swing_highs[-MAX_SWING_HISTORY:]
        if len(self.swing_lows) > MAX_SWING_HISTORY:
            self.swing_lows = self.swing_lows[-MAX_SWING_HISTORY:]

    # ── State Machine ────────────────────────────────────────────────────────

    def _initialize_trend(self) -> None:
        """
        Establish initial trend direction from the first two confirmed
        swing highs and lows.

        Bullish structure: most recent swing low > previous swing low
                          AND most recent swing high > previous swing high
        Bearish structure: mirror
        """
        if len(self.swing_highs) < 2 or len(self.swing_lows) < 2:
            return

        # Compare last two of each
        sh_curr, sh_prev = self.swing_highs[-1], self.swing_highs[-2]
        sl_curr, sl_prev = self.swing_lows[-1], self.swing_lows[-2]

        hh = sh_curr.price > sh_prev.price   # Higher High
        hl = sl_curr.price > sl_prev.price   # Higher Low
        lh = sh_curr.price < sh_prev.price   # Lower High
        ll = sl_curr.price < sl_prev.price   # Lower Low

        if hh and hl:
            self.state = TrendState.BULLISH_TREND
        elif lh and ll:
            self.state = TrendState.BEARISH_TREND
        # Otherwise stay UNKNOWN

    def _scan_for_events(self, candles: pd.DataFrame) -> None:
        """
        Scan recent candle closes for BOS and CHoCH events.
        Only checks candles that are more recent than the last recorded event
        to avoid duplicate detections.
        """
        if not self.swing_highs or not self.swing_lows:
            return

        last_event_ts = self.events[-1].timestamp if self.events else None
        atr = self._atr_series

        closes = candles["close"]
        candle_range = candles["high"] - candles["low"]

        for i in range(len(candles)):
            ts = candles.index[i]
            if isinstance(ts, pd.Timestamp):
                ts = ts.to_pydatetime()

            # Skip bars at or before the last event (already processed)
            if last_event_ts is not None and ts <= last_event_ts:
                continue

            close = float(closes.iloc[i])
            bar_range = float(candle_range.iloc[i])
            current_atr = float(atr.iloc[i]) if atr is not None and i < len(atr) else bar_range

            if current_atr == 0:
                current_atr = bar_range if bar_range > 0 else 1.0

            displacement = bar_range / current_atr

            if self.state == TrendState.BULLISH_TREND:
                # BOS: close above most recent confirmed swing high → continuation
                ref_high = self.swing_highs[-1]
                if close > ref_high.price:
                    self._record_event(
                        StructureEvent.BOS_BULLISH,
                        close, ts, ref_high, displacement,
                    )
                    last_event_ts = ts

                # CHoCH: close below most recent confirmed swing low → reversal
                # Requires displacement >= 1.5x ATR
                ref_low = self.swing_lows[-1]
                if close < ref_low.price and displacement >= CHOCH_MIN_DISPLACEMENT_ATR:
                    self._record_event(
                        StructureEvent.CHOCH_BEARISH,
                        close, ts, ref_low, displacement,
                    )
                    self.state = TrendState.TRANSITIONING
                    last_event_ts = ts

            elif self.state == TrendState.BEARISH_TREND:
                # BOS: close below most recent swing low → continuation
                ref_low = self.swing_lows[-1]
                if close < ref_low.price:
                    self._record_event(
                        StructureEvent.BOS_BEARISH,
                        close, ts, ref_low, displacement,
                    )
                    last_event_ts = ts

                # CHoCH: close above most recent swing high → reversal
                ref_high = self.swing_highs[-1]
                if close > ref_high.price and displacement >= CHOCH_MIN_DISPLACEMENT_ATR:
                    self._record_event(
                        StructureEvent.CHOCH_BULLISH,
                        close, ts, ref_high, displacement,
                    )
                    self.state = TrendState.TRANSITIONING
                    last_event_ts = ts

            elif self.state == TrendState.TRANSITIONING:
                last_choch = self._last_choch()
                if last_choch is None:
                    continue

                if last_choch.event == StructureEvent.CHOCH_BEARISH:
                    # Awaiting confirmation of new bearish trend
                    ref_low = self.swing_lows[-1]
                    if close < ref_low.price:
                        self._record_event(
                            StructureEvent.BOS_BEARISH,
                            close, ts, ref_low, displacement,
                        )
                        self.state = TrendState.BEARISH_TREND
                        last_event_ts = ts

                elif last_choch.event == StructureEvent.CHOCH_BULLISH:
                    # Awaiting confirmation of new bullish trend
                    ref_high = self.swing_highs[-1]
                    if close > ref_high.price:
                        self._record_event(
                            StructureEvent.BOS_BULLISH,
                            close, ts, ref_high, displacement,
                        )
                        self.state = TrendState.BULLISH_TREND
                        last_event_ts = ts

    def _check_ranging(self) -> bool:
        """
        RANGING state: 3+ swing points (highs and lows combined) within
        a 1.5x ATR band.
        """
        if self._atr_series is None or len(self._atr_series) == 0:
            return False

        current_atr = float(self._atr_series.iloc[-1])
        if current_atr == 0:
            return False

        band_width = RANGING_ATR_BAND * current_atr

        # Collect all recent swing prices
        recent_swings = (
            [sp.price for sp in self.swing_highs[-5:]]
            + [sp.price for sp in self.swing_lows[-5:]]
        )
        if len(recent_swings) < RANGING_MIN_SWINGS:
            return False

        price_range = max(recent_swings) - min(recent_swings)
        return price_range <= band_width

    def _record_event(
        self,
        event: StructureEvent,
        price: float,
        timestamp: datetime,
        swing_ref: SwingPoint,
        displacement_size: float,
    ) -> None:
        self.events.append(StructureEventRecord(
            event=event,
            price=price,
            timestamp=timestamp,
            swing_ref=swing_ref,
            displacement_size=displacement_size,
        ))

    def _last_choch(self) -> Optional[StructureEventRecord]:
        """Return the most recent CHoCH event, or None."""
        for ev in reversed(self.events):
            if ev.event in (StructureEvent.CHOCH_BULLISH, StructureEvent.CHOCH_BEARISH):
                return ev
        return None

    # ── Scoring ──────────────────────────────────────────────────────────────

    def _score_from_state(self) -> float:
        """Map current state + latest event to a directional score."""
        event = self.latest_event()
        event_type = event.event if event else None
        key = (self.state, event_type)
        base = _SCORE_MAP.get(key, 0.0)
        # TRANSITIONING: sign determined by direction of the CHoCH that triggered it
        if self.state == TrendState.TRANSITIONING and event:
            base = _SCORE_MAP.get((TrendState.TRANSITIONING, None), 0.3)
            sign = 1.0 if event.event == StructureEvent.CHOCH_BULLISH else -1.0
            return sign * abs(base)
        return base


# ── ATR Helper ───────────────────────────────────────────────────────────────

def _compute_atr(candles: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Wilder's ATR(period) using True Range.
    TR = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
    ATR = Wilder smoothed TR (equivalent to EWM with com=period-1)
    """
    high = candles["high"]
    low = candles["low"]
    close = candles["close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(com=period - 1, adjust=False).mean()
    return atr
