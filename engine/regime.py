"""
Market Regime Detection — ADX-based gate (not a scored module).

Classifies the market as TRENDING, RANGING, or TRANSITIONAL.
Gates signal generation thresholds in the confluence aggregator.

TRENDING    (ADX > 25): Normal generation, standard thresholds
RANGING     (ADX < 20): Raise thresholds, suppress trend-following, allow mean-reversion only
TRANSITIONAL (20–25):  Flag signals with "Regime Uncertain", reduce confidence by 10%

Secondary confirmation: Bollinger Band width vs 50-period BB width MA
    - Squeeze = ranging
    - Expansion = trending
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

import pandas as pd


class MarketRegime(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    TRANSITIONAL = "TRANSITIONAL"
    UNKNOWN = "UNKNOWN"


# ADX thresholds
ADX_TRENDING_THRESHOLD = 25.0
ADX_RANGING_THRESHOLD = 20.0
ADX_PERIOD = 14

# Confidence penalty for TRANSITIONAL regime
TRANSITIONAL_PENALTY = 0.10    # 10% score reduction
RANGING_THRESHOLD_BOOST = 0.20  # Raise minimum threshold by 0.20 in ranging


class RegimeDetector:
    """
    Classifies market regime using ADX(14) with BB width secondary confirmation.

    Usage:
        detector = RegimeDetector(timeframe="15m", pair="XAUUSD")
        detector.update(candles_df)
        regime = detector.regime
        adjusted_threshold = detector.apply_threshold_adjustment(base=0.50)
    """

    def __init__(self, timeframe: str, pair: str):
        self.timeframe = timeframe
        self.pair = pair
        self._regime: MarketRegime = MarketRegime.UNKNOWN
        self._last_adx: float = 0.0
        self._bb_confirming: Optional[bool] = None   # None = no confirmation

    def update(self, candles: pd.DataFrame) -> None:
        """
        Calculate ADX(14) and BB width secondary confirmation.

        Args:
            candles: OHLCV DataFrame sorted ascending.
                     Minimum length: 2 * ADX_PERIOD + 1 bars.

        Sprint 5 implementation notes:
        - +DM = High - prev_High if positive, else 0
        - -DM = prev_Low - Low if positive, else 0
        - TR = max(High-Low, |High-prev_Close|, |Low-prev_Close|)
        - ATR_14 = Wilder smoothed TR
        - +DI = 100 * Wilder_smooth(+DM) / ATR_14
        - -DI = 100 * Wilder_smooth(-DM) / ATR_14
        - DX = 100 * |+DI - -DI| / (+DI + -DI)
        - ADX = Wilder_smooth(DX, 14)
        - BB width secondary: current BB width vs 50-bar BB width MA
        """
        raise NotImplementedError("Implement in Sprint 5")

    @property
    def regime(self) -> MarketRegime:
        """Return the current market regime classification."""
        return self._regime

    @property
    def adx(self) -> float:
        """Return the most recent ADX value."""
        return self._last_adx

    def apply_threshold_adjustment(self, base_threshold: float) -> float:
        """
        Adjust the minimum confluence threshold based on current regime.

        RANGING:       +0.20 boost (e.g., 0.50 → 0.70)
        TRANSITIONAL:  no threshold change (confidence penalty applied separately)
        TRENDING:      no change

        Returns:
            Adjusted minimum threshold.
        """
        if self._regime == MarketRegime.RANGING:
            return min(base_threshold + RANGING_THRESHOLD_BOOST, 1.0)
        return base_threshold

    def apply_score_penalty(self, score: float) -> float:
        """
        Apply regime-based penalty to a confluence score.

        TRANSITIONAL: reduce |score| by TRANSITIONAL_PENALTY (10%)
        Others: no change.

        Returns:
            Penalized score (preserves sign).
        """
        if self._regime == MarketRegime.TRANSITIONAL:
            sign = 1.0 if score >= 0 else -1.0
            return sign * max(0.0, abs(score) - TRANSITIONAL_PENALTY)
        return score

    def is_mean_reversion_allowed(self) -> bool:
        """
        In RANGING regime, only mean-reversion setups are valid.
        Returns True when signal generation should switch to mean-reversion mode.
        """
        return self._regime == MarketRegime.RANGING

    def _classify_from_adx(self, adx_value: float) -> MarketRegime:
        """Classify regime from a single ADX value."""
        if adx_value > ADX_TRENDING_THRESHOLD:
            return MarketRegime.TRENDING
        elif adx_value < ADX_RANGING_THRESHOLD:
            return MarketRegime.RANGING
        else:
            return MarketRegime.TRANSITIONAL

    def _combine_with_bb_confirmation(
        self,
        adx_regime: MarketRegime,
        bb_squeeze: bool,
    ) -> MarketRegime:
        """
        Merge ADX regime with BB width secondary signal.
        BB squeeze + ADX near threshold → lean toward RANGING.

        Sprint 5 implementation.
        """
        raise NotImplementedError("Implement in Sprint 5")
