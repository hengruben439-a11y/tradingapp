"""
Signal Generator — wires all 9 engine modules into the confluence pipeline.

This is the main integration point called by the backtesting harness on each
bar close of the entry timeframe.

Pipeline:
    1. Update all modules with current candle slice
    2. Collect raw scores from each module
    3. Build AggregatorInput with flags (unicorn, OTE confluence, KZ active)
    4. Run ConfluenceAggregator → AggregatorResult
    5. If passes_threshold → run TPSLEngine → build TradeRecord

Trading style → timeframe mapping:
    scalping:         entry="5m",  htf=["15m", "1H"]
    day_trading:      entry="15m", htf=["1H",  "4H"]
    swing_trading:    entry="4H",  htf=["1D",  "1W"]
    position_trading: entry="1D",  htf=["1W"]
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from engine.aggregator import AggregatorInput, ConfluenceAggregator
from engine.modules.bollinger import BollingerModule
from engine.modules.ema import EMAModule
from engine.modules.fvg import FVGModule
from engine.modules.kill_zones import KillZoneModule
from engine.modules.macd import MACDModule
from engine.modules.market_structure import MarketStructureModule, TrendState
from engine.modules.order_blocks import OrderBlockModule
from engine.modules.ote import OTEModule
from engine.modules.rsi import RSIModule
from engine.modules.support_resistance import SupportResistanceModule
from engine.regime import MarketRegime, RegimeDetector
from engine.signal import MarketRegime as SignalRegime
from engine.tp_sl import TPSLEngine
from backtest.executor import TradeRecord, TradeStatus


# Maps trading style → (entry_tf, htf_list)
STYLE_TIMEFRAMES: dict[str, tuple[str, list[str]]] = {
    "scalping":         ("5m",  ["15m", "1H"]),
    "day_trading":      ("15m", ["1H",  "4H"]),
    "swing_trading":    ("4H",  ["1D",  "1W"]),
    "position_trading": ("1D",  ["1W"]),
}

# Minimum warmup candles on entry TF before signals can be generated
MIN_WARMUP_BARS = 200


def _compute_atr(candles: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR(14) using True Range and Wilder smoothing."""
    high = candles["high"]
    low = candles["low"]
    close = candles["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


class SignalGenerator:
    """
    Wires all 9 confluence modules into a single bar-driven pipeline.

    Usage:
        gen = SignalGenerator(pair="XAUUSD", trading_style="day_trading")
        trade = gen.process_bar(candles_dict, bar_index)
        # trade is a TradeRecord in PENDING status, or None if no signal

    The caller is responsible for:
        - Providing candles_dict keyed by timeframe (all TFs pre-resampled)
        - Passing bar_index = current bar in the entry TF
        - Filling the trade at the next bar's open (next-bar-open execution)
    """

    def __init__(self, pair: str, trading_style: str):
        self.pair = pair
        self.trading_style = trading_style

        if trading_style not in STYLE_TIMEFRAMES:
            raise ValueError(f"Unknown trading_style: {trading_style!r}")

        self.entry_tf, self.htf_list = STYLE_TIMEFRAMES[trading_style]

        # Entry TF modules
        self.market_structure = MarketStructureModule(self.entry_tf, pair)
        self.order_blocks = OrderBlockModule(self.entry_tf, pair)
        self.fvg = FVGModule(self.entry_tf, pair)
        self.ote = OTEModule(self.entry_tf, pair)
        self.ema = EMAModule(self.entry_tf, pair)
        self.rsi = RSIModule(self.entry_tf, pair)
        self.macd = MACDModule(self.entry_tf, pair)
        self.bollinger = BollingerModule(self.entry_tf, pair)
        self.kill_zones = KillZoneModule(pair)
        self.support_resistance = SupportResistanceModule(self.entry_tf, pair)
        self.regime_detector = RegimeDetector(self.entry_tf, pair)

        # HTF market structure module (first HTF only, for conflict detection)
        htf_primary = self.htf_list[0] if self.htf_list else self.entry_tf
        self.htf_market_structure = MarketStructureModule(htf_primary, pair)
        self.htf_regime_detector = RegimeDetector(htf_primary, pair)

        # Aggregator and TP/SL engine
        self.aggregator = ConfluenceAggregator(pair)
        self.tpsl_engine = TPSLEngine(pair)

        self._bar_count = 0

    def process_bar(
        self,
        candles_dict: dict[str, pd.DataFrame],
        bar_index: int,
        news_proximity: bool = False,
        day_of_week_modifier: float = 1.0,
    ) -> Optional[TradeRecord]:
        """
        Run the full signal pipeline on one bar.

        Args:
            candles_dict: Pre-resampled candles keyed by timeframe.
                          Each value is a full DataFrame sliced up to and
                          including the current bar (iloc[:bar_index+1]).
            bar_index: Current bar index in the entry TF (0-based).
            news_proximity: True if high-impact news is within 15 minutes.
            day_of_week_modifier: Day-of-week multiplier (default 1.0x).

        Returns:
            TradeRecord in PENDING status, or None if no signal.
        """
        self._bar_count += 1

        entry_candles = candles_dict.get(self.entry_tf)
        if entry_candles is None or len(entry_candles) < MIN_WARMUP_BARS:
            return None

        # ── Step 1: Update all entry TF modules ──────────────────────────────
        atr = _compute_atr(entry_candles)
        current_close = float(entry_candles["close"].iloc[-1])
        bar_ts = entry_candles.index[-1]
        if isinstance(bar_ts, pd.Timestamp):
            bar_ts_dt = bar_ts.to_pydatetime()
            if bar_ts_dt.tzinfo is None:
                bar_ts_dt = bar_ts_dt.replace(tzinfo=timezone.utc)
        else:
            bar_ts_dt = bar_ts

        self.market_structure.update(entry_candles)
        self.ema.update(entry_candles)
        self.rsi.update(entry_candles)
        self.macd.update(entry_candles)
        self.bollinger.update(entry_candles, atr)
        self.order_blocks.update(entry_candles, atr)
        self.fvg.update(entry_candles, atr)
        self.ote.update(entry_candles, self.market_structure.swing_highs, self.market_structure.swing_lows)
        self.support_resistance.update(
            entry_candles,
            self.market_structure.swing_highs,
            self.market_structure.swing_lows,
            atr,
        )
        self.kill_zones.update_bar(bar_ts_dt)
        self.regime_detector.update(entry_candles)

        # ── Step 2: Update HTF modules ────────────────────────────────────────
        htf_primary = self.htf_list[0] if self.htf_list else self.entry_tf
        htf_candles = candles_dict.get(htf_primary)
        if htf_candles is not None and len(htf_candles) >= 29:
            self.htf_market_structure.update(htf_candles)
            self.htf_regime_detector.update(htf_candles)

        # ── Step 3: Collect raw scores ────────────────────────────────────────
        is_bullish_trend = self.market_structure.state == TrendState.BULLISH_TREND

        ms_score = self.market_structure.score()
        ob_fvg_score = self._compute_ob_fvg_score(current_close)
        ote_score = self.ote.score(current_close)
        ema_score = self.ema.score()
        rsi_score = self.rsi.score()
        macd_score = self.macd.score()
        bollinger_score = self.bollinger.score(
            macd_is_bullish=(macd_score > 0),
            rsi_is_oversold=(rsi_score > 0.3),
        )
        kz_score = self.kill_zones.score(is_bullish_trend)
        sr_score = self.support_resistance.score(current_close, is_bullish_trend)

        # ── Step 4: Determine confluence flags ────────────────────────────────
        regime = self._map_regime(self.regime_detector.regime)
        htf_conflict = self._detect_htf_conflict(ms_score)
        unicorn_setup = self._check_unicorn(current_close)
        ote_ob_confluence = self._check_ote_ob_confluence(current_close)
        ote_fvg_confluence = self._check_ote_fvg_confluence(current_close)
        kz_active = self.kill_zones.active_kill_zone is not None

        # ── Step 5: Aggregate ─────────────────────────────────────────────────
        agg_input = AggregatorInput(
            market_structure=ms_score,
            order_blocks_fvg=ob_fvg_score,
            ote=ote_score,
            ema=ema_score,
            rsi=rsi_score,
            macd=macd_score,
            bollinger=bollinger_score,
            kill_zone=kz_score,
            support_resistance=sr_score,
            unicorn_setup=unicorn_setup,
            ote_ob_confluence=ote_ob_confluence,
            ote_fvg_confluence=ote_fvg_confluence,
            kill_zone_active=kz_active,
            htf_conflict=htf_conflict,
            news_proximity=news_proximity,
            regime=regime,
            day_of_week_modifier=day_of_week_modifier,
        )

        agg_result = self.aggregator.aggregate(agg_input)

        if not agg_result.passes_threshold:
            return None

        # ── Step 6: TP/SL calculation ─────────────────────────────────────────
        atr_val = float(atr.iloc[-1]) if not atr.empty and not pd.isna(atr.iloc[-1]) else 1.0

        support_prices = [lvl.price for lvl in self.support_resistance.levels
                          if lvl.kind.value == "SUPPORT"]
        resistance_prices = [lvl.price for lvl in self.support_resistance.levels
                              if lvl.kind.value == "RESISTANCE"]
        fib_extensions = self.ote.get_tp_levels() if self.ote.current_range else {}
        swing_invalidation = self._get_swing_invalidation(agg_result.direction.value)

        tpsl = self.tpsl_engine.calculate(
            entry_price=current_close,
            direction=agg_result.direction,
            atr=atr_val,
            support_levels=support_prices,
            resistance_levels=resistance_prices,
            fib_extensions=fib_extensions,
            swing_invalidation=swing_invalidation,
        )

        if tpsl is None:
            return None  # TP1 cannot achieve 1:1 R:R; signal suppressed

        # ── Step 7: Lot size ──────────────────────────────────────────────────
        lot_size, dollar_risk = self.tpsl_engine.calculate_lot_size(
            account_balance=10_000.0,
            risk_pct=1.0,
            sl_distance_pips=tpsl.sl_distance_pips,
        )

        # ── Step 8: Build TradeRecord (PENDING) ───────────────────────────────
        return TradeRecord(
            signal_id=str(uuid.uuid4()),
            pair=self.pair,
            direction=agg_result.direction,
            signal_time=bar_ts_dt,
            entry_time=None,
            entry_price=tpsl.entry_price,
            fill_price=None,
            spread_applied=0.0,
            stop_loss=tpsl.stop_loss,
            tp1=tpsl.tp1.price,
            tp2=tpsl.tp2.price,
            tp3=tpsl.tp3.price,
            initial_lot_size=lot_size,
            current_lot_size=lot_size,
            status=TradeStatus.PENDING,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _compute_ob_fvg_score(self, current_price: float) -> float:
        """Combined OB + FVG module score (20%/18% weight module)."""
        ob_score = self.order_blocks.score(current_price)
        fvg_score = self.fvg.score(current_price)
        # Unicorn setup (OB + FVG overlap) is max-scored here
        if abs(ob_score) > 0 and abs(fvg_score) > 0 and (ob_score * fvg_score) > 0:
            return max(ob_score, fvg_score, key=abs)  # already +1.0 from OB if unicorn
        return ob_score if abs(ob_score) >= abs(fvg_score) else fvg_score

    def _check_unicorn(self, current_price: float) -> bool:
        """True if price is at an OB zone that overlaps with an FVG (unicorn setup)."""
        for ob in self.order_blocks.active_obs:
            if ob.status.value == "ACTIVE":
                if self.fvg.check_unicorn_overlap(ob.high, ob.low):
                    # Check that current price is near the OB zone
                    if ob.low <= current_price <= ob.high:
                        return True
        return False

    def _check_ote_ob_confluence(self, current_price: float) -> bool:
        """True if any active OB overlaps with the current OTE zone."""
        for ob in self.order_blocks.active_obs:
            if ob.status.value == "ACTIVE":
                if self.ote.has_ob_confluence(ob.high, ob.low):
                    return True
        return False

    def _check_ote_fvg_confluence(self, current_price: float) -> bool:
        """True if any open/partial FVG overlaps with the current OTE zone."""
        from engine.modules.fvg import FVGStatus
        for fvg in self.fvg.fvgs:
            if fvg.status in (FVGStatus.OPEN, FVGStatus.PARTIALLY_FILLED):
                if self.ote.has_fvg_confluence(fvg.top, fvg.bottom):
                    return True
        return False

    def _map_regime(self, regime: MarketRegime) -> SignalRegime:
        """Map engine.regime.MarketRegime to engine.signal.MarketRegime."""
        mapping = {
            MarketRegime.TRENDING: SignalRegime.TRENDING,
            MarketRegime.RANGING: SignalRegime.RANGING,
            MarketRegime.TRANSITIONAL: SignalRegime.TRANSITIONAL,
            MarketRegime.UNKNOWN: SignalRegime.UNKNOWN,
        }
        return mapping.get(regime, SignalRegime.UNKNOWN)

    def _detect_htf_conflict(self, entry_score: float) -> bool:
        """True if entry TF and primary HTF have opposing directional bias."""
        htf_score = self.htf_market_structure.score()
        if entry_score == 0.0 or htf_score == 0.0:
            return False
        return (entry_score > 0) != (htf_score > 0)

    def _get_swing_invalidation(self, direction: str) -> Optional[float]:
        """Return the nearest swing point that would invalidate the trade."""
        if direction == "BUY":
            lows = self.market_structure.swing_lows
            if lows:
                return lows[-1].price
        else:
            highs = self.market_structure.swing_highs
            if highs:
                return highs[-1].price
        return None
