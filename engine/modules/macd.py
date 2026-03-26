"""
MACD Module — Weight: 7% (XAU + GJ)

Standard MACD (12, 26, 9) with crossover and histogram divergence detection.
Prioritizes crossovers near the zero line (stronger momentum shifts).

Sprint 4 deliverable: full implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd


class MACDSignalKind(str, Enum):
    BULLISH_CROSSOVER_NEAR_ZERO = "BULLISH_CROSSOVER_NEAR_ZERO"   # Strongest
    BULLISH_CROSSOVER_FAR_ZERO = "BULLISH_CROSSOVER_FAR_ZERO"     # Weaker
    BEARISH_CROSSOVER_NEAR_ZERO = "BEARISH_CROSSOVER_NEAR_ZERO"
    BEARISH_CROSSOVER_FAR_ZERO = "BEARISH_CROSSOVER_FAR_ZERO"
    HISTOGRAM_BULLISH_DIVERGENCE = "HISTOGRAM_BULLISH_DIVERGENCE"
    HISTOGRAM_BEARISH_DIVERGENCE = "HISTOGRAM_BEARISH_DIVERGENCE"
    HISTOGRAM_RISING = "HISTOGRAM_RISING"
    HISTOGRAM_FALLING = "HISTOGRAM_FALLING"
    NEUTRAL = "NEUTRAL"


@dataclass
class MACDState:
    macd_line: float
    signal_line: float
    histogram: float
    latest_signal: MACDSignalKind


# Threshold for "near zero line" classification
NEAR_ZERO_THRESHOLD_ATR_PCT = 0.05   # Within 5% of ATR range from zero


class MACDModule:
    """
    MACD momentum scoring.

    Score logic:
        Bullish crossover near zero line: +0.8
        Bullish crossover far from zero: +0.4
        Histogram increasing (positive, getting larger): +0.3
        Histogram bearish divergence (price HH, histogram LH): -0.6
        Bearish crossover near zero: -0.8
        Bearish crossover far: -0.4
        No crossover, flat histogram: 0.0

    Usage:
        module = MACDModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df)
        score = module.score()
    """

    def __init__(
        self,
        timeframe: str,
        pair: str,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ):
        self.timeframe = timeframe
        self.pair = pair
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self._state: Optional[MACDState] = None
        self._macd_line: Optional[pd.Series] = None
        self._signal_line: Optional[pd.Series] = None
        self._histogram: Optional[pd.Series] = None

    def update(self, candles: pd.DataFrame) -> None:
        """
        Calculate MACD components and detect crossover/divergence events.

        Args:
            candles: OHLCV DataFrame sorted ascending.
                     Minimum length: slow + signal + divergence_lookback bars.
        """
        if len(candles) < self.slow + self.signal_period:
            return

        closes = candles["close"]
        ema_fast = closes.ewm(span=self.fast, adjust=False).mean()
        ema_slow = closes.ewm(span=self.slow, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        self._macd_line = macd_line
        self._signal_line = signal_line
        self._histogram = histogram

        curr_macd = float(macd_line.iloc[-1])
        curr_sig = float(signal_line.iloc[-1])
        curr_hist = float(histogram.iloc[-1])

        # Determine ATR approximation for near-zero threshold
        bar_range = candles["high"] - candles["low"]
        atr_approx = float(bar_range.rolling(14).mean().iloc[-1]) if len(candles) >= 14 else float(bar_range.mean())
        if pd.isna(atr_approx) or atr_approx <= 0:
            atr_approx = abs(curr_macd) + 1.0
        near_zero_threshold = NEAR_ZERO_THRESHOLD_ATR_PCT * atr_approx

        # Detect crossover
        signal_kind = MACDSignalKind.NEUTRAL
        if len(macd_line) >= 2:
            prev_macd = float(macd_line.iloc[-2])
            prev_sig = float(signal_line.iloc[-2])
            prev_hist = float(histogram.iloc[-2])

            bullish_cross = prev_macd <= prev_sig and curr_macd > curr_sig
            bearish_cross = prev_macd >= prev_sig and curr_macd < curr_sig

            if bullish_cross:
                signal_kind = (
                    MACDSignalKind.BULLISH_CROSSOVER_NEAR_ZERO
                    if abs(curr_macd) < near_zero_threshold
                    else MACDSignalKind.BULLISH_CROSSOVER_FAR_ZERO
                )
            elif bearish_cross:
                signal_kind = (
                    MACDSignalKind.BEARISH_CROSSOVER_NEAR_ZERO
                    if abs(curr_macd) < near_zero_threshold
                    else MACDSignalKind.BEARISH_CROSSOVER_FAR_ZERO
                )
            elif curr_hist > 0 and curr_hist > prev_hist:
                signal_kind = MACDSignalKind.HISTOGRAM_RISING
            elif curr_hist < 0 and curr_hist < prev_hist:
                signal_kind = MACDSignalKind.HISTOGRAM_FALLING
            else:
                # Check for histogram divergence
                div = self._detect_histogram_divergence(candles, histogram)
                if div is not None:
                    signal_kind = div

        self._state = MACDState(
            macd_line=curr_macd,
            signal_line=curr_sig,
            histogram=curr_hist,
            latest_signal=signal_kind,
        )

    def score(self) -> float:
        """
        Return directional MACD score.

        Returns:
            float in [-1.0, +1.0]
        """
        if self._state is None:
            return 0.0

        kind = self._state.latest_signal
        hist = self._state.histogram

        score_map = {
            MACDSignalKind.BULLISH_CROSSOVER_NEAR_ZERO: 0.8,
            MACDSignalKind.BULLISH_CROSSOVER_FAR_ZERO: 0.4,
            MACDSignalKind.BEARISH_CROSSOVER_NEAR_ZERO: -0.8,
            MACDSignalKind.BEARISH_CROSSOVER_FAR_ZERO: -0.4,
            # Bearish divergence: price HH but histogram LH → momentum weakening → -0.6
            MACDSignalKind.HISTOGRAM_BEARISH_DIVERGENCE: -0.6,
            # Bullish divergence: price LL but histogram HL → momentum turning → +0.6
            MACDSignalKind.HISTOGRAM_BULLISH_DIVERGENCE: 0.6,
            MACDSignalKind.HISTOGRAM_RISING: 0.3,
            MACDSignalKind.HISTOGRAM_FALLING: -0.3,
            MACDSignalKind.NEUTRAL: 0.0,
        }

        return score_map.get(kind, 0.0)

    @property
    def current_state(self) -> Optional[MACDState]:
        """Return the most recently computed MACD state."""
        return self._state

    def is_bullish_momentum(self) -> bool:
        """True if histogram is positive and increasing."""
        if self._state is None:
            return False
        return (
            self._state.histogram > 0
            and self._state.latest_signal in (
                MACDSignalKind.HISTOGRAM_RISING,
                MACDSignalKind.BULLISH_CROSSOVER_NEAR_ZERO,
                MACDSignalKind.BULLISH_CROSSOVER_FAR_ZERO,
            )
        )

    def _detect_histogram_divergence(
        self,
        candles: pd.DataFrame,
        histogram: pd.Series,
        lookback: int = 10,
    ) -> Optional[MACDSignalKind]:
        """
        Detect MACD histogram divergence by comparing price extremes
        vs histogram extremes over the last `lookback` bars.

        Bearish divergence: price makes higher high but histogram makes lower high → -0.6
        Bullish divergence: price makes lower low but histogram makes higher low → +0.6
        """
        if len(candles) < lookback + 2:
            return None

        recent_closes = candles["close"].iloc[-lookback:]
        recent_hist = histogram.iloc[-lookback:]

        if len(recent_closes) < 4:
            return None

        # Find local highs in price (for bearish divergence)
        price_highs = []
        hist_at_highs = []
        for i in range(1, len(recent_closes) - 1):
            if recent_closes.iloc[i] > recent_closes.iloc[i - 1] and recent_closes.iloc[i] > recent_closes.iloc[i + 1]:
                price_highs.append(float(recent_closes.iloc[i]))
                hist_at_highs.append(float(recent_hist.iloc[i]))

        if len(price_highs) >= 2:
            if price_highs[-1] > price_highs[-2] and hist_at_highs[-1] < hist_at_highs[-2]:
                return MACDSignalKind.HISTOGRAM_BEARISH_DIVERGENCE

        # Find local lows in price (for bullish divergence)
        price_lows = []
        hist_at_lows = []
        for i in range(1, len(recent_closes) - 1):
            if recent_closes.iloc[i] < recent_closes.iloc[i - 1] and recent_closes.iloc[i] < recent_closes.iloc[i + 1]:
                price_lows.append(float(recent_closes.iloc[i]))
                hist_at_lows.append(float(recent_hist.iloc[i]))

        if len(price_lows) >= 2:
            if price_lows[-1] < price_lows[-2] and hist_at_lows[-1] > hist_at_lows[-2]:
                return MACDSignalKind.HISTOGRAM_BULLISH_DIVERGENCE

        return None
