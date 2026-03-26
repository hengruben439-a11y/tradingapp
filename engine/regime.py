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
        """
        min_bars = 2 * ADX_PERIOD + 1
        if len(candles) < min_bars:
            return

        high = candles["high"]
        low = candles["low"]
        close = candles["close"]

        # True Range
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)

        # Directional Movement
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm = pd.Series(0.0, index=candles.index)
        minus_dm = pd.Series(0.0, index=candles.index)
        plus_dm[(up_move > down_move) & (up_move > 0)] = up_move[(up_move > down_move) & (up_move > 0)]
        minus_dm[(down_move > up_move) & (down_move > 0)] = down_move[(down_move > up_move) & (down_move > 0)]

        # Wilder smoothing: com = period - 1
        com = ADX_PERIOD - 1
        atr_wilder = tr.ewm(com=com, adjust=False).mean()
        plus_dm_smooth = plus_dm.ewm(com=com, adjust=False).mean()
        minus_dm_smooth = minus_dm.ewm(com=com, adjust=False).mean()

        # Directional Indicators
        plus_di = 100.0 * plus_dm_smooth / atr_wilder.replace(0, float("nan"))
        minus_di = 100.0 * minus_dm_smooth / atr_wilder.replace(0, float("nan"))

        # DX and ADX
        di_sum = plus_di + minus_di
        dx = 100.0 * (plus_di - minus_di).abs() / di_sum.replace(0, float("nan"))
        adx = dx.ewm(com=com, adjust=False).mean()

        self._last_adx = float(adx.iloc[-1]) if not adx.empty and not pd.isna(adx.iloc[-1]) else 0.0
        adx_regime = self._classify_from_adx(self._last_adx)

        # BB width secondary confirmation
        bb_squeeze = False
        if len(candles) >= 70:  # Need 20 bars for BB + 50 bars for MA
            bb_period = 20
            sma = close.rolling(bb_period).mean()
            std = close.rolling(bb_period).std()
            upper = sma + 2.0 * std
            lower = sma - 2.0 * std
            width = (upper - lower) / sma.replace(0, float("nan"))
            width_ma50 = width.rolling(50).mean()
            if not width.empty and not width_ma50.empty:
                curr_w = width.iloc[-1]
                avg_w = width_ma50.iloc[-1]
                if not pd.isna(curr_w) and not pd.isna(avg_w) and avg_w > 0:
                    bb_squeeze = curr_w < avg_w * 0.8   # Width well below average = squeeze
                    self._bb_confirming = not bb_squeeze  # expansion = trending confirmation

        self._regime = self._combine_with_bb_confirmation(adx_regime, bb_squeeze)

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
        BB expansion + ADX near threshold → lean toward TRENDING.
        ADX clearly above/below thresholds → ADX wins regardless.
        """
        # If ADX is decisive (not in transitional zone), trust it
        if adx_regime == MarketRegime.TRENDING or adx_regime == MarketRegime.RANGING:
            # BB can only confirm, not override a decisive ADX reading
            if adx_regime == MarketRegime.TRENDING and bb_squeeze:
                return MarketRegime.TRANSITIONAL  # Conflicting signals
            return adx_regime

        # ADX is TRANSITIONAL (20-25): BB breaks the tie
        if bb_squeeze:
            return MarketRegime.RANGING
        if self._bb_confirming:
            return MarketRegime.TRENDING
        return MarketRegime.TRANSITIONAL
