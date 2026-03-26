"""
RSI Module — Weight: 8% (XAU + GJ)

14-period RSI with overbought/oversold detection and divergence detection.
Thresholds are timeframe-dependent (scalping: 65/35, others: 70/30 etc.)

Sprint 4 deliverable: full implementation including divergence detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd


class DivergenceKind(str, Enum):
    BULLISH_REGULAR = "BULLISH_REGULAR"     # Price LL, RSI HL → reversal buy
    BEARISH_REGULAR = "BEARISH_REGULAR"     # Price HH, RSI LH → reversal sell
    BULLISH_HIDDEN = "BULLISH_HIDDEN"       # Price HL, RSI LL → continuation buy
    BEARISH_HIDDEN = "BEARISH_HIDDEN"       # Price LH, RSI HH → continuation sell


@dataclass
class DivergenceRecord:
    kind: DivergenceKind
    timestamp: datetime
    price_level: float
    rsi_level: float


# RSI thresholds per timeframe group (from config/parameters.yaml)
RSI_THRESHOLDS: dict[str, tuple[float, float]] = {
    "1m":  (65.0, 35.0),
    "5m":  (65.0, 35.0),
    "15m": (70.0, 30.0),
    "30m": (70.0, 30.0),
    "1H":  (70.0, 30.0),
    "4H":  (70.0, 30.0),
    "1D":  (75.0, 25.0),
    "1W":  (80.0, 20.0),
}

# Divergence lookback bars per timeframe group
DIVERGENCE_LOOKBACK: dict[str, int] = {
    "1m":  5,
    "5m":  8,
    "15m": 10,
    "30m": 12,
    "1H":  15,
    "4H":  18,
    "1D":  20,
    "1W":  20,
}


class RSIModule:
    """
    RSI-based momentum and divergence scoring.

    Score logic:
        RSI oversold (< lower threshold): +0.6 to +1.0 (scaled by extremity)
        RSI overbought (> upper threshold): -0.6 to -1.0
        Neutral zone (40–60): 0.0
        Bullish Regular Divergence: +0.8
        Bearish Regular Divergence: -0.8
        Bullish Hidden Divergence (trend continuation): +0.5
        Bearish Hidden Divergence: -0.5

    Usage:
        module = RSIModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df)
        score = module.score()
    """

    def __init__(self, timeframe: str, pair: str, period: int = 14):
        self.timeframe = timeframe
        self.pair = pair
        self.period = period
        self._rsi: Optional[pd.Series] = None
        self._latest_rsi: float = 50.0
        self._divergences: list[DivergenceRecord] = []

        # Get thresholds for this timeframe
        thresholds = RSI_THRESHOLDS.get(timeframe, (70.0, 30.0))
        self.overbought = thresholds[0]
        self.oversold = thresholds[1]
        self.lookback = DIVERGENCE_LOOKBACK.get(timeframe, 14)

    def update(self, candles: pd.DataFrame) -> None:
        """
        Calculate RSI and scan for divergences.

        Args:
            candles: OHLCV DataFrame sorted ascending. Min length: period + lookback.
        """
        if len(candles) < self.period + 1:
            return

        closes = candles["close"]
        self._rsi = self._calculate_rsi(closes)
        self._latest_rsi = float(self._rsi.iloc[-1])
        self._detect_divergence(candles, self._rsi)

    def score(self) -> float:
        """
        Return directional score based on RSI level and detected divergences.

        Divergence scores take precedence over raw OB/OS readings.
        """
        if self._rsi is None:
            return 0.0

        # Divergence takes precedence
        div = self.latest_divergence()
        if div is not None:
            if div.kind == DivergenceKind.BULLISH_REGULAR:
                return 0.8
            elif div.kind == DivergenceKind.BEARISH_REGULAR:
                return -0.8
            elif div.kind == DivergenceKind.BULLISH_HIDDEN:
                return 0.5
            elif div.kind == DivergenceKind.BEARISH_HIDDEN:
                return -0.5

        rsi = self._latest_rsi

        # Overbought / oversold
        if rsi < self.oversold:
            return self._scale_extreme_score(rsi)
        if rsi > self.overbought:
            return self._scale_extreme_score(rsi)

        # Neutral zone
        if 40.0 <= rsi <= 60.0:
            return 0.0

        # Between threshold and neutral — mild bias
        if rsi < 40.0:
            return 0.2   # mild bullish lean
        if rsi > 60.0:
            return -0.2  # mild bearish lean

        return 0.0

    @property
    def latest_rsi(self) -> float:
        """Return the most recently calculated RSI value."""
        return self._latest_rsi

    def is_oversold(self) -> bool:
        return self._latest_rsi < self.oversold

    def is_overbought(self) -> bool:
        return self._latest_rsi > self.overbought

    def latest_divergence(self) -> Optional[DivergenceRecord]:
        """Return the most recent divergence signal, or None."""
        return self._divergences[-1] if self._divergences else None

    def _calculate_rsi(self, closes: pd.Series) -> pd.Series:
        """
        Wilder's smoothed RSI calculation.
        Returns RSI series aligned to closes index.
        """
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = delta.clip(upper=0).abs()

        # Wilder's smoothing: com = period - 1
        avg_gain = gain.ewm(com=self.period - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=self.period - 1, adjust=False).mean()

        # Handle division edge cases:
        # - avg_loss = 0 AND avg_gain > 0 → RS = ∞ → RSI = 100
        # - avg_loss = 0 AND avg_gain = 0 → no movement → RSI = 50
        # - normal case: RSI = 100 - 100/(1+RS)
        rsi = pd.Series(50.0, index=closes.index, dtype=float)
        both_zero = (avg_gain <= 0) & (avg_loss <= 0)
        only_gain = (avg_gain > 0) & (avg_loss <= 0)
        normal = ~both_zero & ~only_gain

        if normal.any():
            rs_normal = avg_gain[normal] / avg_loss[normal]
            rsi[normal] = 100.0 - (100.0 / (1.0 + rs_normal))

        rsi[only_gain] = 100.0
        # both_zero stays at 50.0 (initial fill)

        return rsi.fillna(50.0)

    def _detect_divergence(self, candles: pd.DataFrame, rsi: pd.Series) -> None:
        """
        Scan recent bars for regular and hidden RSI divergence.

        Uses the last `lookback` bars. Finds the two most recent local
        highs (for bearish divergence) or lows (for bullish divergence)
        and compares price vs RSI direction.
        """
        if len(candles) < 6:
            return

        closes = candles["close"]
        # Use a wider scan window (lookback * 6, min 60 bars) to find pivot pairs.
        # self.lookback represents the minimum bar separation between pivots, not window size.
        window = min(len(candles), max(self.lookback * 6, 60))
        recent_closes = closes.iloc[-window:]
        recent_rsi = rsi.iloc[-window:]

        if len(recent_closes) < 4:
            return

        # Find local lows (for bullish divergence).
        # Use strict < on left (must be lower than previous bar) and <= on right
        # (allows flat-bottom pivots where next bar equals the low).
        lows_idx = []
        for i in range(1, len(recent_closes) - 1):
            if (recent_closes.iloc[i] < recent_closes.iloc[i - 1]
                    and recent_closes.iloc[i] <= recent_closes.iloc[i + 1]):
                lows_idx.append(i)
        # Also treat the last bar as a potential pivot (current bar in live context).
        last = len(recent_closes) - 1
        if last >= 1 and recent_closes.iloc[last] < recent_closes.iloc[last - 1]:
            lows_idx.append(last)

        # Find local highs (for bearish divergence).
        highs_idx = []
        for i in range(1, len(recent_closes) - 1):
            if (recent_closes.iloc[i] > recent_closes.iloc[i - 1]
                    and recent_closes.iloc[i] >= recent_closes.iloc[i + 1]):
                highs_idx.append(i)
        # Also treat the last bar as a potential pivot.
        if last >= 1 and recent_closes.iloc[last] > recent_closes.iloc[last - 1]:
            highs_idx.append(last)

        # Need at least 2 pivots with >= 3 bar separation
        if len(lows_idx) >= 2:
            i1, i2 = lows_idx[-2], lows_idx[-1]
            if i2 - i1 >= 3:
                p1 = float(recent_closes.iloc[i1])
                p2 = float(recent_closes.iloc[i2])
                r1 = float(recent_rsi.iloc[i1])
                r2 = float(recent_rsi.iloc[i2])

                ts = candles.index[-1]
                if isinstance(ts, pd.Timestamp):
                    ts = ts.to_pydatetime()

                if p2 < p1 and r2 > r1:
                    # Regular bullish: price LL, RSI HL
                    self._divergences.append(DivergenceRecord(
                        kind=DivergenceKind.BULLISH_REGULAR,
                        timestamp=ts,
                        price_level=p2,
                        rsi_level=r2,
                    ))
                elif p2 > p1 and r2 < r1:
                    # Hidden bullish: price HL, RSI LL
                    self._divergences.append(DivergenceRecord(
                        kind=DivergenceKind.BULLISH_HIDDEN,
                        timestamp=ts,
                        price_level=p2,
                        rsi_level=r2,
                    ))

        if len(highs_idx) >= 2:
            i1, i2 = highs_idx[-2], highs_idx[-1]
            if i2 - i1 >= 3:
                p1 = float(recent_closes.iloc[i1])
                p2 = float(recent_closes.iloc[i2])
                r1 = float(recent_rsi.iloc[i1])
                r2 = float(recent_rsi.iloc[i2])

                ts = candles.index[-1]
                if isinstance(ts, pd.Timestamp):
                    ts = ts.to_pydatetime()

                if p2 > p1 and r2 < r1:
                    # Regular bearish: price HH, RSI LH
                    self._divergences.append(DivergenceRecord(
                        kind=DivergenceKind.BEARISH_REGULAR,
                        timestamp=ts,
                        price_level=p2,
                        rsi_level=r2,
                    ))
                elif p2 < p1 and r2 > r1:
                    # Hidden bearish: price LH, RSI HH
                    self._divergences.append(DivergenceRecord(
                        kind=DivergenceKind.BEARISH_HIDDEN,
                        timestamp=ts,
                        price_level=p2,
                        rsi_level=r2,
                    ))

    def _scale_extreme_score(self, rsi_value: float) -> float:
        """
        Scale oversold/overbought intensity to a 0.6–1.0 score.
        More extreme RSI = higher score magnitude.

        Oversold: 0.6 at threshold, 1.0 at 10 (absolute extreme)
        Overbought: -0.6 at threshold, -1.0 at 90
        """
        if rsi_value <= self.oversold:
            # Map [oversold..10] → [0.6..1.0]
            extreme_low = 10.0
            if rsi_value <= extreme_low:
                return 1.0
            fraction = (self.oversold - rsi_value) / (self.oversold - extreme_low)
            return 0.6 + 0.4 * fraction
        else:
            # Map [overbought..90] → [-0.6..-1.0]
            extreme_high = 90.0
            if rsi_value >= extreme_high:
                return -1.0
            fraction = (rsi_value - self.overbought) / (extreme_high - self.overbought)
            return -(0.6 + 0.4 * fraction)
