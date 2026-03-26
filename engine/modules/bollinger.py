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

        Sprint 4 implementation notes:
        - Upper = SMA(period) + num_std * StdDev(period)
        - Lower = SMA(period) - num_std * StdDev(period)
        - Width = (Upper - Lower) / SMA
        - Squeeze: width is at its lowest value in the past 20 bars
        - %B = (price - lower) / (upper - lower)
        - High-volatility scaling: if ATR > 2x ATR_20_avg, multiply threshold zones by 1.2
        - Store previous regime to detect transition into breakout
        """
        raise NotImplementedError("Implement in Sprint 4")

    def score(self, macd_is_bullish: bool = False, rsi_is_oversold: bool = False) -> float:
        """
        Return directional BB score with external indicator confirmation.

        Args:
            macd_is_bullish: Whether MACD is in bullish momentum state.
            rsi_is_oversold: Whether RSI is in oversold territory.

        Returns:
            float in [-1.0, +1.0]
        """
        raise NotImplementedError("Implement in Sprint 4")

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
        raise NotImplementedError("Implement in Sprint 4")

    def _classify_regime(self, width_series: pd.Series) -> BBRegime:
        """
        Classify the current BB regime based on recent width history.

        Sprint 4 implementation:
        - SQUEEZE if current width <= min(width_series[-20:])
        - EXPANSION if current width > 1.5x its 20-period average
        - NEUTRAL otherwise
        """
        raise NotImplementedError("Implement in Sprint 4")
