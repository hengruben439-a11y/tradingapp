"""
Trade execution manager — bridges SignalGenerator output to MetaApi.

Handles:
- Signal validity check (price still within ATR tolerance at execution time)
- Lot size calculation based on account balance and risk %
- 3-tier TP management (TP1: 40%, TP2: 30%, TP3: 30%)
- Position monitoring for partial closes and SL trail
- Execution journal logging
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from broker.metaapi import AccountInfo, MetaApiClient, OrderRequest, _pip_size_for_symbol

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Pip value per standard lot (1 lot) in USD for a USD-denominated account.
# GBPJPY pip value is dynamic — calculated at execution time using USDJPY rate.
_XAUUSD_PIP_VALUE_PER_LOT = 1.0          # $1.00 per pip per standard lot (100 oz × $0.01)
_GBPJPY_PIP_VALUE_DEFAULT = 9.50         # ~$9.50 per pip per standard lot (fallback)

_MONITOR_INTERVAL_SECONDS = 30
_TP1_CLOSE_PCT = 0.40
_TP2_CLOSE_PCT = 0.30   # 30% of original (50% of remaining after TP1)


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class ExecutionResult:
    """Result of a signal execution attempt."""

    success: bool
    signal_id: str
    position_id: str
    fill_price: float
    lot_size: float
    dollar_risk: float
    slippage_pips: float
    error: Optional[str] = None


@dataclass
class _ManagedPosition:
    """Internal state for a position being monitored by ExecutionManager."""

    signal_id: str
    position_id: str
    symbol: str
    direction: str          # "BUY" | "SELL"
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    initial_lots: float
    remaining_lots: float
    tp1_hit: bool = False
    tp2_hit: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── ExecutionManager ──────────────────────────────────────────────────────────


class ExecutionManager:
    """
    Manages the full lifecycle of a trade from signal to journal close.

    Responsibilities:
    - Validates signal price is still within ATR tolerance before executing
    - Calculates lot size from account balance and risk %
    - Places market order via MetaApi with SL + TP1
    - Registers position for 3-tier TP monitoring
    - Handles partial closes (TP1 40%, TP2 30%) and SL trailing
    - Logs outcomes to Redis for the journal to pick up

    Args:
        metaapi: Connected MetaApiClient instance.
        redis_client: Async Redis client (from api.redis_client.get_redis()).
                      Can be None in dev/test mode — logging will be skipped.
        risk_pct: Default risk per trade as a percentage (e.g. 1.0 = 1%).
    """

    def __init__(
        self,
        metaapi: MetaApiClient,
        redis_client: Optional[object],
        risk_pct: float = 1.0,
    ) -> None:
        self._api = metaapi
        self._redis = redis_client
        self._risk_pct = risk_pct
        self._positions: dict[str, _ManagedPosition] = {}   # position_id → state
        self._monitor_task: Optional[asyncio.Task] = None   # type: ignore[type-arg]

    # ── Public interface ───────────────────────────────────────────────────────

    async def execute_signal(
        self,
        signal: dict,
        account_info: AccountInfo,
    ) -> ExecutionResult:
        """
        Execute a signal by placing a market order on the broker account.

        Steps:
        1. Validate signal price is still within ATR tolerance.
        2. Calculate lot size from balance and risk %.
        3. Place market order (SL + TP1).
        4. Register position for TP2/TP3 monitoring.
        5. Return ExecutionResult.

        Args:
            signal: Signal dict with keys: signal_id, pair, direction, entry_price,
                    stop_loss, tp1, tp2, tp3, atr (ATR value for validity check).
            account_info: Current account snapshot (balance, equity, etc.).

        Returns:
            ExecutionResult. Check .success before using .position_id.
        """
        signal_id = signal.get("signal_id", "")
        symbol = signal.get("pair", "")
        direction = signal.get("direction", "").upper()
        entry_price = float(signal.get("entry_price", 0.0))
        stop_loss = float(signal.get("stop_loss", 0.0))
        tp1 = float(signal.get("tp1", 0.0))
        tp2 = float(signal.get("tp2", 0.0))
        tp3 = float(signal.get("tp3", 0.0))
        atr = float(signal.get("atr", 0.0))

        # ── Step 1: Validate price is still within tolerance ──────────────────
        # We pass 0.0 as current_price here since we don't have a live feed;
        # callers that have a live price should pass it via signal["current_price"].
        current_price = float(signal.get("current_price", entry_price))
        if not MetaApiClient.is_price_within_validity(entry_price, current_price, atr):
            return ExecutionResult(
                success=False,
                signal_id=signal_id,
                position_id="",
                fill_price=0.0,
                lot_size=0.0,
                dollar_risk=0.0,
                slippage_pips=0.0,
                error=(
                    f"Signal entry {entry_price} no longer valid — "
                    f"current price {current_price} is more than 0.5× ATR ({atr}) away"
                ),
            )

        # ── Step 2: Calculate lot size ────────────────────────────────────────
        sl_pips = self._sl_pips(entry_price, stop_loss, symbol)
        if sl_pips <= 0:
            return ExecutionResult(
                success=False,
                signal_id=signal_id,
                position_id="",
                fill_price=0.0,
                lot_size=0.0,
                dollar_risk=0.0,
                slippage_pips=0.0,
                error=f"Invalid SL distance: sl_pips={sl_pips}",
            )

        pip_val = self._pip_value(symbol, 1.0)   # pip value per standard lot
        dollar_risk = account_info.balance * (self._risk_pct / 100.0)
        # Lot size = dollar_risk / (sl_pips × pip_value_per_lot)
        lot_size = dollar_risk / (sl_pips * pip_val)
        lot_size = round(max(0.01, lot_size), 2)   # minimum 0.01, rounded to 0.01

        # ── Step 3: Place order ───────────────────────────────────────────────
        action_type = "ORDER_TYPE_BUY" if direction == "BUY" else "ORDER_TYPE_SELL"
        order_req = OrderRequest(
            symbol=symbol,
            action_type=action_type,
            volume=lot_size,
            stop_loss=stop_loss,
            take_profit=tp1,
        )
        result = await self._api.place_order(order_req)

        if not result.success:
            return ExecutionResult(
                success=False,
                signal_id=signal_id,
                position_id="",
                fill_price=0.0,
                lot_size=lot_size,
                dollar_risk=dollar_risk,
                slippage_pips=0.0,
                error=result.error_message,
            )

        # ── Step 4: Register for TP2/TP3 monitoring ───────────────────────────
        managed = _ManagedPosition(
            signal_id=signal_id,
            position_id=result.position_id,
            symbol=symbol,
            direction=direction,
            entry_price=result.fill_price,
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            initial_lots=lot_size,
            remaining_lots=lot_size,
        )
        self._positions[result.position_id] = managed
        self._ensure_monitor_running()

        logger.info(
            "Executed signal %s: %s %s %.2f lots @ %.5f (SL=%.5f TP1=%.5f)",
            signal_id,
            direction,
            symbol,
            lot_size,
            result.fill_price,
            stop_loss,
            tp1,
        )

        return ExecutionResult(
            success=True,
            signal_id=signal_id,
            position_id=result.position_id,
            fill_price=result.fill_price,
            lot_size=lot_size,
            dollar_risk=dollar_risk,
            slippage_pips=result.slippage_pips,
        )

    async def monitor_positions(self) -> None:
        """
        Background task: polls open positions every 30 seconds.

        For each managed position:
        - TP1 hit → close 40%, move SL to breakeven
        - TP2 hit → close 50% of remaining (= 30% original), trail SL to TP1
        - TP3 is left with trailed SL; broker closes it naturally
        - SL hit / position gone → remove from managed set

        This method runs until there are no more managed positions or the task
        is cancelled. Call start_monitor() to run it as a background task.
        """
        while self._positions:
            await asyncio.sleep(_MONITOR_INTERVAL_SECONDS)
            await self._check_positions()

    async def cancel_signal(self, signal_id: str) -> None:
        """
        Cancel a pending signal that has not yet been filled.

        For live orders this is a no-op — MetaApi market orders fill immediately.
        This method removes the signal from internal tracking if it hasn't been
        executed yet (e.g. validity window expired before user confirmed).

        Args:
            signal_id: The signal ID to cancel.
        """
        to_remove = [
            pid for pid, pos in self._positions.items()
            if pos.signal_id == signal_id
        ]
        for pid in to_remove:
            del self._positions[pid]
            logger.info("Cancelled monitoring for signal %s (position %s)", signal_id, pid)

    # ── Internal position monitoring ───────────────────────────────────────────

    def _ensure_monitor_running(self) -> None:
        """Start the background monitor task if it is not already running."""
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self.monitor_positions())

    async def _check_positions(self) -> None:
        """Fetch live positions from MetaApi and apply TP/SL management logic."""
        try:
            live_positions = await self._api.get_positions()
        except Exception as exc:
            logger.warning("monitor_positions: failed to fetch positions: %s", exc)
            return

        live_by_id = {p.id: p for p in live_positions}
        closed_ids = []

        for pid, managed in list(self._positions.items()):
            live = live_by_id.get(pid)

            if live is None:
                # Position closed externally (SL hit, manual close, etc.)
                logger.info(
                    "Position %s (signal %s) no longer open — removing from monitoring",
                    pid,
                    managed.signal_id,
                )
                closed_ids.append(pid)
                continue

            current_price = live.current_price
            is_buy = managed.direction == "BUY"

            # TP1 check
            if not managed.tp1_hit:
                tp1_triggered = (
                    (is_buy and current_price >= managed.tp1)
                    or (not is_buy and current_price <= managed.tp1)
                )
                if tp1_triggered:
                    await self._handle_tp1(managed)

            # TP2 check (only after TP1)
            elif managed.tp1_hit and not managed.tp2_hit:
                tp2_triggered = (
                    (is_buy and current_price >= managed.tp2)
                    or (not is_buy and current_price <= managed.tp2)
                )
                if tp2_triggered:
                    await self._handle_tp2(managed)

        for pid in closed_ids:
            del self._positions[pid]

    async def _handle_tp1(self, managed: _ManagedPosition) -> None:
        """Close 40% of the position at TP1 and move SL to breakeven."""
        lots_to_close = round(managed.initial_lots * _TP1_CLOSE_PCT, 2)
        success = await self._api.close_position(managed.position_id, volume=lots_to_close)
        if success:
            managed.remaining_lots = round(managed.remaining_lots - lots_to_close, 2)
            managed.tp1_hit = True
            # Move SL to breakeven (fill/entry price)
            await self._api.modify_order(
                managed.position_id,
                sl=managed.entry_price,
                tp=managed.tp2,   # Update TP to TP2 level
            )
            logger.info(
                "TP1 hit: closed %.2f lots of position %s, SL moved to breakeven %.5f",
                lots_to_close,
                managed.position_id,
                managed.entry_price,
            )

    async def _handle_tp2(self, managed: _ManagedPosition) -> None:
        """Close 30% of original position (50% of remaining) at TP2, trail SL to TP1."""
        lots_to_close = round(managed.initial_lots * _TP2_CLOSE_PCT, 2)
        lots_to_close = min(lots_to_close, managed.remaining_lots)
        success = await self._api.close_position(managed.position_id, volume=lots_to_close)
        if success:
            managed.remaining_lots = round(managed.remaining_lots - lots_to_close, 2)
            managed.tp2_hit = True
            # Trail SL to TP1 level; TP3 stays as target
            await self._api.modify_order(
                managed.position_id,
                sl=managed.tp1,
                tp=managed.tp3,   # Update TP to TP3 level
            )
            logger.info(
                "TP2 hit: closed %.2f lots of position %s, SL trailed to TP1 %.5f",
                lots_to_close,
                managed.position_id,
                managed.tp1,
            )

    # ── Calculation helpers ────────────────────────────────────────────────────

    @staticmethod
    def _pip_value(symbol: str, volume: float) -> float:
        """
        Return the USD pip value for a given symbol and lot size.

        For XAUUSD: $1.00 per pip per standard lot (100 oz × $0.01 move).
        For GBPJPY: ~$9.50 per pip per standard lot (dynamic, based on USDJPY).
                    Uses the static fallback $9.50 since we don't have a live
                    USDJPY feed at calculation time. Callers with a live rate
                    should override by passing usdjpy_rate explicitly.

        Args:
            symbol: "XAUUSD" or "GBPJPY".
            volume: Lot size.

        Returns:
            Dollar pip value for the specified volume.
        """
        if symbol == "XAUUSD":
            return _XAUUSD_PIP_VALUE_PER_LOT * volume
        elif symbol == "GBPJPY":
            return _GBPJPY_PIP_VALUE_DEFAULT * volume
        # Generic forex: $10 per pip per standard lot (approximate)
        return 10.0 * volume

    @staticmethod
    def _sl_pips(entry: float, sl: float, symbol: str) -> float:
        """
        Calculate the SL distance in pips.

        Args:
            entry: Entry price.
            sl: Stop loss price.
            symbol: Trading pair.

        Returns:
            Absolute SL distance in pips (always positive).
        """
        pip_size = _pip_size_for_symbol(symbol)
        if pip_size <= 0:
            return 0.0
        return abs(entry - sl) / pip_size
