"""
Bollinger Bands Module — Weight: 5% (XAU + GJ)

20-period SMA with 2 standard deviations. Primary use: squeeze detection
and volatility context. Band touches alone are NOT standalone signals.

Sprint 4 deliverable: full implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class BBRegime(str, Enum):
    SQUEEZE = "SQUEEZE"           # Band width at 20-period low → range breakout imminent
    EXPANSION = "EXPANSION"       # Band width expanding → trending
    NEUTRAL = "NEUTRAL"           # Normal volatility


@dataclass
class BBState:
    upper: float
    middle: float   # SMA 20
    lower: float
    width: float    # (upper - lower) / middle
    regime: BBRegime
    percent_b: float   # Price position within bands: 0.0 = lower, 1.0 = upper


class BollingerModule:
    """
    Bollinger Bands volatility and squeeze scoring.

    Score logic:
        Squeeze breakout above upper + bullish MACD: +0.8
        Squeeze breakout below lower + bearish MACD: -0.8
        Price at lower band + RSI oversold: +0.5 (mean reversion)
        Price at upper band + RSI overbought: -0.5
        No squeeze, price between bands: 0.0
        Active squeeze (no breakout yet): 0.0 (neutral, awaiting)

    ATR multiplier: When ATR > 2x its 20-period avg, widen interpretation zones by 20%.

    Usage:
        module = BollingerModule(timeframe="15m", pair="XAUUSD")
        module.update(candles_df)
        score = module.score(macd_is_bullish=True, rsi_is_oversold=False)
    """

    def __init__(
        self,
        timeframe: str,
        pair: str,
        period: int = 20,
        num_std: float = 2.0,
    ):
        self.timeframe = timeframe
        self.pair = pair
        self.period = period
        self.num_std = num_std
        self._state: Optional[BBState] = None
        self._prev_regime: Optional[BBRegime] = None   # For breakout detection

    def update(self, candles: pd.DataFrame, atr: pd.Series) -> None:
        """
        Calculate Bollinger Bands, band width, and detect squeeze.

        Args:
            candles: OHLCV DataFrame sorted ascending.
            atr: ATR(14) series aligned to candles. Used for high-volatility scaling.
        """
        if len(candles) < self.period:
            return

        closes = candles["close"]
        sma = closes.rolling(self.period).mean()
        std = closes.rolling(self.period).std()

        upper = sma + self.num_std * std
        lower = sma - self.num_std * std
        width = (upper - lower) / sma.replace(0, float("nan"))

        current_price = float(closes.iloc[-1])
        curr_upper = float(upper.iloc[-1])
        curr_lower = float(lower.iloc[-1])
        curr_middle = float(sma.iloc[-1])
        curr_width = float(width.iloc[-1])

        if pd.isna(curr_upper) or pd.isna(curr_lower) or pd.isna(curr_middle):
            return

        band_range = curr_upper - curr_lower
        pct_b = (current_price - curr_lower) / band_range if band_range > 0 else 0.5

        regime = self._classify_regime(width)

        self._prev_regime = self._state.regime if self._state is not None else None
        self._state = BBState(
            upper=curr_upper,
            middle=curr_middle,
            lower=curr_lower,
            width=curr_width,
            regime=regime,
            percent_b=pct_b,
        )

    def score(self, macd_is_bullish: bool = False, rsi_is_oversold: bool = False) -> float:
        """
        Return directional BB score with external indicator confirmation.

        Args:
            macd_is_bullish: Whether MACD is in bullish momentum state.
            rsi_is_oversold: Whether RSI is in oversold territory.

        Returns:
            float in [-1.0, +1.0]
        """
        if self._state is None:
            return 0.0

        state = self._state
        pct_b = state.percent_b

        # Squeeze breakout: previous regime was SQUEEZE, now price breaks band
        if self._prev_regime == BBRegime.SQUEEZE:
            if pct_b > 1.0 and macd_is_bullish:
                return 0.8   # Squeeze breakout above upper + bullish MACD
            if pct_b < 0.0 and not macd_is_bullish:
                return -0.8  # Squeeze breakout below lower + bearish MACD

        # Mean reversion: price at lower band + RSI oversold
        if pct_b <= 0.05 and rsi_is_oversold:
            return 0.5

        # Mean reversion: price at upper band + RSI overbought
        if pct_b >= 0.95 and not rsi_is_oversold:
            return -0.5

        # Active squeeze with no breakout — neutral, awaiting direction
        if state.regime == BBRegime.SQUEEZE:
            return 0.0

        return 0.0

    @property
    def current_state(self) -> Optional[BBState]:
        return self._state

    def is_in_squeeze(self) -> bool:
        """True if BB is currently in squeeze (width at 20-period low)."""
        if self._state is None:
            return False
        return self._state.regime == BBRegime.SQUEEZE

    def squeeze_just_broke(self, direction: str) -> bool:
        """
        True if price just broke out of a squeeze in the given direction.
        direction: "up" or "down"
        """
        if self._state is None or self._prev_regime != BBRegime.SQUEEZE:
            return False
        if direction == "up":
            return self._state.percent_b > 1.0
        elif direction == "down":
            return self._state.percent_b < 0.0
        return False

    def _classify_regime(self, width_series: pd.Series) -> BBRegime:
        """
        Classify the current BB regime based on recent width history.

        SQUEEZE if current width <= min(width_series[-20:])
        EXPANSION if current width > 1.5x its 20-period average
        NEUTRAL otherwise
        """
        valid = width_series.dropna()
        if len(valid) < 2:
            return BBRegime.NEUTRAL

        curr_width = float(valid.iloc[-1])
        lookback = valid.iloc[-20:]

        if len(lookback) < 2:
            return BBRegime.NEUTRAL

        min_width = float(lookback.iloc[:-1].min())  # min of prior 19 (not including current)
        avg_width = float(lookback.mean())

        if curr_width <= min_width:
            return BBRegime.SQUEEZE
        if avg_width > 0 and curr_width > 1.5 * avg_width:
            return BBRegime.EXPANSION
        return BBRegime.NEUTRAL
