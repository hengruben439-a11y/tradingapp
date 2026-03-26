"""
Trade Executor — Next-bar-open execution model.

All signals generated at bar close are filled at the OPEN of the following bar
plus spread. This prevents look-ahead bias and matches live HFM execution.

Execution assumptions (from config/spreads.yaml):
    - Next-bar-open fill: signal_bar.close → next_bar.open + spread
    - Dynamic spread: session/news-dependent (2–15 pips XAU, 3–10 pips GJ)
    - Slippage: 1 pip additional
    - Latency: 50ms (cosmetic for simulation, bar-level granularity)
    - Commission: $0 (spread-only model)

Trade lifecycle:
    PENDING  → signal created at bar close
    OPEN     → filled at next bar open
    TP1_HIT  → 40% closed, SL moved to breakeven
    TP2_HIT  → 30% closed, SL trailed to TP1 level
    TP3_HIT  → final 30% closed
    SL_HIT   → full position closed
    EXPIRED  → signal validity window elapsed without fill
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd
import yaml

from engine.signal import Direction


class TradeStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    TP1_HIT = "TP1_HIT"
    TP2_HIT = "TP2_HIT"
    TP3_HIT = "TP3_HIT"
    SL_HIT = "SL_HIT"
    EXPIRED = "EXPIRED"


@dataclass
class TradeRecord:
    """Full record of a single simulated trade."""
    signal_id: str
    pair: str
    direction: Direction
    signal_time: datetime           # Bar close when signal was generated
    entry_time: Optional[datetime]  # Next bar open when filled
    entry_price: float              # signal.entry_price
    fill_price: Optional[float]     # Actual fill = next_bar.open + spread
    spread_applied: float           # Pips of spread at execution
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    initial_lot_size: float
    current_lot_size: float         # Decreases as partial closes happen
    status: TradeStatus = TradeStatus.PENDING
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    pnl_pips: float = 0.0
    pnl_usd: float = 0.0
    r_multiple: float = 0.0         # Final P&L / initial risk
    tp1_hit_at: Optional[datetime] = None
    tp2_hit_at: Optional[datetime] = None
    slippage_pips: float = 1.0      # Fixed 1-pip slippage


# Spread model — loads from config/spreads.yaml at runtime
_spread_config: Optional[dict] = None


def _load_spread_config() -> dict:
    global _spread_config
    if _spread_config is None:
        try:
            with open("config/spreads.yaml") as f:
                _spread_config = yaml.safe_load(f)
        except FileNotFoundError:
            _spread_config = {"XAUUSD": {"default": 3}, "GBPJPY": {"default": 4}}
    return _spread_config


def get_spread_pips(
    pair: str,
    bar_time: datetime,
    is_news_bar: bool = False,
) -> float:
    """
    Return the dynamic spread in pips for the given bar.

    Session classification (UTC):
        London/NY overlap (07:00–16:00): lowest spread
        Asian session (23:00–07:00): moderate spread
        News first 5 minutes: highest spread
        Low liquidity: elevated spread

    Args:
        pair: "XAUUSD" or "GBPJPY"
        bar_time: UTC-aware datetime of the bar.
        is_news_bar: True if bar falls within 5 minutes of high-impact news.

    Returns:
        Spread in pips (float).
    """
    config = _load_spread_config()
    pair_spreads = config.get(pair, config.get("XAUUSD", {}))

    if is_news_bar:
        return float(pair_spreads.get("news_first_5min", 15))

    hour = bar_time.hour
    if 7 <= hour < 16:
        return float(pair_spreads.get("london_ny_hours", 3))
    elif hour >= 23 or hour < 7:
        return float(pair_spreads.get("asian_session", 4))
    else:
        return float(pair_spreads.get("default", 3))


def execute_next_bar_open(
    trade: TradeRecord,
    next_bar: pd.Series,
    is_news_bar: bool = False,
) -> TradeRecord:
    """
    Fill a PENDING trade at the open of the next bar.

    Args:
        trade: Trade record in PENDING status.
        next_bar: The bar immediately after signal generation (has 'open').
        is_news_bar: Whether this bar is during high-impact news.

    Returns:
        Updated TradeRecord with OPEN status and fill_price set.
    """
    spread = get_spread_pips(trade.pair, next_bar.name, is_news_bar)
    slippage = trade.slippage_pips

    pip_size = _pip_size(trade.pair)
    total_cost = (spread + slippage) * pip_size

    if trade.direction == Direction.BUY:
        fill = next_bar["open"] + total_cost
    else:
        fill = next_bar["open"] - total_cost

    trade.fill_price = round(fill, _price_decimals(trade.pair))
    trade.spread_applied = spread
    trade.entry_time = next_bar.name
    trade.status = TradeStatus.OPEN
    return trade


def update_trade(trade: TradeRecord, bar: pd.Series, risk_pips: float) -> TradeRecord:
    """
    Check if a bar triggers any TP or SL levels and update trade accordingly.

    Args:
        trade: Open trade record.
        bar: Current OHLCV bar as pd.Series.
        risk_pips: Initial SL distance in pips (for R multiple calculation).

    Returns:
        Updated TradeRecord.
    """
    if trade.status not in (TradeStatus.OPEN, TradeStatus.TP1_HIT, TradeStatus.TP2_HIT):
        return trade

    high, low = bar["high"], bar["low"]

    if trade.direction == Direction.BUY:
        # Check SL first (pessimistic)
        if low <= trade.stop_loss:
            return _close_trade(trade, trade.stop_loss, bar.name, TradeStatus.SL_HIT, risk_pips)
        if trade.status == TradeStatus.OPEN and high >= trade.tp1:
            trade = _partial_close(trade, trade.tp1, bar.name, TradeStatus.TP1_HIT, 0.40)
            trade.stop_loss = trade.fill_price  # Move SL to breakeven
        if trade.status == TradeStatus.TP1_HIT and high >= trade.tp2:
            trade = _partial_close(trade, trade.tp2, bar.name, TradeStatus.TP2_HIT, 0.30)
            trade.stop_loss = trade.tp1  # Trail SL to TP1
        if trade.status == TradeStatus.TP2_HIT and high >= trade.tp3:
            return _close_trade(trade, trade.tp3, bar.name, TradeStatus.TP3_HIT, risk_pips)
    else:  # SELL
        if high >= trade.stop_loss:
            return _close_trade(trade, trade.stop_loss, bar.name, TradeStatus.SL_HIT, risk_pips)
        if trade.status == TradeStatus.OPEN and low <= trade.tp1:
            trade = _partial_close(trade, trade.tp1, bar.name, TradeStatus.TP1_HIT, 0.40)
            trade.stop_loss = trade.fill_price
        if trade.status == TradeStatus.TP1_HIT and low <= trade.tp2:
            trade = _partial_close(trade, trade.tp2, bar.name, TradeStatus.TP2_HIT, 0.30)
            trade.stop_loss = trade.tp1
        if trade.status == TradeStatus.TP2_HIT and low <= trade.tp3:
            return _close_trade(trade, trade.tp3, bar.name, TradeStatus.TP3_HIT, risk_pips)

    return trade


def _partial_close(
    trade: TradeRecord,
    price: float,
    timestamp: datetime,
    new_status: TradeStatus,
    close_pct: float,
) -> TradeRecord:
    """Record a partial close at a TP level."""
    if new_status == TradeStatus.TP1_HIT:
        trade.tp1_hit_at = timestamp
    elif new_status == TradeStatus.TP2_HIT:
        trade.tp2_hit_at = timestamp

    lots_closed = trade.initial_lot_size * close_pct
    pip_size = _pip_size(trade.pair)
    pip_distance = abs(price - trade.fill_price) / pip_size
    pnl_pips = pip_distance if trade.direction == Direction.BUY else -pip_distance
    trade.pnl_pips += pnl_pips * close_pct
    trade.current_lot_size -= lots_closed
    trade.status = new_status
    return trade


def _close_trade(
    trade: TradeRecord,
    price: float,
    timestamp: datetime,
    status: TradeStatus,
    risk_pips: float,
) -> TradeRecord:
    """Fully close the trade and calculate final P&L."""
    trade.exit_price = price
    trade.exit_time = timestamp
    trade.status = status

    pip_size = _pip_size(trade.pair)
    if trade.fill_price is None:
        return trade

    pip_distance = (price - trade.fill_price) / pip_size
    if trade.direction == Direction.SELL:
        pip_distance = -pip_distance

    remaining_pct = trade.current_lot_size / trade.initial_lot_size
    trade.pnl_pips += pip_distance * remaining_pct
    trade.current_lot_size = 0.0

    if risk_pips > 0:
        trade.r_multiple = trade.pnl_pips / risk_pips

    return trade


def _pip_size(pair: str) -> float:
    """Return the pip decimal value for the pair."""
    if pair == "GBPJPY":
        return 0.01     # 1 pip = 0.01
    elif pair == "XAUUSD":
        return 0.1      # 1 pip = $0.10
    return 0.0001


def _price_decimals(pair: str) -> int:
    """Return decimal places for price rounding."""
    if pair == "GBPJPY":
        return 3
    elif pair == "XAUUSD":
        return 2
    return 5
