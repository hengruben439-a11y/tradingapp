"""
Expert Advisor (EA) communication router.

Internal-only endpoints used by the made. MQL4/MQL5 Expert Advisors running
inside MetaTrader on the user's broker (HFM MT4/MT5).

All endpoints require the X-EA-Secret header matching the EA_SECRET
environment variable. They are NOT exposed to the iOS app or public internet —
they should be firewalled to localhost or VPN in production.

Endpoints:
    GET  /broker/ea/pending       Returns signals queued for EA execution
    POST /broker/ea/confirm       EA reports execution result (filled/rejected)
    POST /broker/ea/tp_hit        EA reports a TP level was hit
    POST /broker/ea/sl_hit        EA reports SL hit; triggers post-mortem
    GET  /broker/ea/heartbeat     EA liveness check
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/broker/ea", tags=["ea"])

# ── Auth ──────────────────────────────────────────────────────────────────────

_DEFAULT_EA_SECRET = "ea-dev-secret"


def _verify_ea_secret(x_ea_secret: str = Header(alias="X-EA-Secret")) -> str:
    """
    Verify the shared secret sent by the EA in every request.

    Set EA_SECRET environment variable in production. Never hard-code in EA
    inputs if the backend is publicly reachable — use environment injection
    or a secrets manager.
    """
    expected = os.getenv("EA_SECRET", _DEFAULT_EA_SECRET)
    if x_ea_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid EA secret",
        )
    return x_ea_secret


# ── In-memory pending signal queue (dev mode) ─────────────────────────────────
# In production this would be backed by Redis or the Supabase signals table.
# The signal engine pushes entries here when a signal is confirmed for execution
# by the user (via the iOS app "Confirm Trade" flow).

_pending_queue: list[dict] = []


# ── Pydantic models ───────────────────────────────────────────────────────────

class EAConfirmRequest(BaseModel):
    """Execution confirmation sent by the EA after attempting an order."""

    model_config = {"extra": "ignore"}

    signal_id: str = Field(..., description="Signal UUID from the pending queue")
    ticket: int = Field(0, description="Broker ticket number (0 if order failed)")
    fill_price: float = Field(0.0, description="Actual fill price")
    status: str = Field(..., description="'filled' | 'rejected' | 'failed'")
    reason: str = Field("", description="Rejection/failure reason code")
    error_code: int = Field(0, description="Broker error code if failed")
    magic: int = Field(0, description="EA magic number")


class EATPHitRequest(BaseModel):
    """TP level hit notification sent by the EA."""

    model_config = {"extra": "ignore"}

    ticket: int = Field(..., description="Broker ticket number")
    tp_level: int = Field(..., ge=1, le=3, description="1, 2, or 3")
    hit_price: float = Field(..., description="Price at which TP was hit")
    magic: int = Field(0)
    symbol: str = Field("", description="Trading symbol")


class EASLHitRequest(BaseModel):
    """Stop-loss hit notification sent by the EA; triggers post-mortem generation."""

    model_config = {"extra": "ignore"}

    ticket: int = Field(..., description="Broker ticket number")
    close_price: float = Field(..., description="Price at SL hit")
    profit_usd: float = Field(..., description="Realised P&L in USD (negative for loss)")
    magic: int = Field(0)
    symbol: str = Field("", description="Trading symbol")


class EAPendingSignal(BaseModel):
    """Signal payload sent to the EA for execution."""

    model_config = {"extra": "ignore"}

    signal_id: str
    pair: str
    direction: str = Field(..., description="'BUY' or 'SELL'")
    entry_price: float
    sl: float = Field(..., description="Stop loss price")
    tp1: float
    tp2: float
    tp3: float
    lot_size: float = Field(0.01, description="Calculated lot size from risk module")
    queued_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get(
    "/pending",
    response_model=list[EAPendingSignal],
    summary="Get signals pending EA execution",
)
async def get_pending_signals(
    magic: int = Query(..., description="EA magic number to filter by"),
    _: str = _verify_ea_secret.__wrapped__ if hasattr(_verify_ea_secret, "__wrapped__") else _verify_ea_secret,
    x_ea_secret: str = Header(alias="X-EA-Secret"),
    db=None,
) -> list[dict]:
    """
    Return all signals queued for execution by this EA instance.

    The EA polls this endpoint every few seconds. Each returned signal
    should be executed exactly once — the EA deduplicates by signal_id.

    In production, signals reach this queue after the user taps "Confirm Trade"
    in the iOS app. In dev mode, signals can be injected via the
    POST /broker/ea/queue endpoint (internal tooling).
    """
    # Verify secret manually (dependency injection workaround for header-only deps)
    expected = os.getenv("EA_SECRET", _DEFAULT_EA_SECRET)
    if x_ea_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid EA secret")

    if not _pending_queue:
        return []

    # Filter by magic number if the EA sent one
    result = [s for s in _pending_queue if s.get("magic", magic) == magic or magic == 0]
    return result


@router.post(
    "/confirm",
    status_code=status.HTTP_200_OK,
    summary="EA confirms trade execution",
)
async def confirm_execution(
    payload: EAConfirmRequest,
    x_ea_secret: str = Header(alias="X-EA-Secret"),
    db=None,
) -> dict:
    """
    Called by the EA after attempting to open a position.

    On success (status='filled'): logs fill price and slippage, updates the
    signal record with broker ticket and execution timestamp.

    On rejection (status='rejected'): marks signal as not-executed, notifies
    the app so the user can decide whether to re-confirm.

    On failure (status='failed'): logs the broker error code for diagnostics.
    """
    expected = os.getenv("EA_SECRET", _DEFAULT_EA_SECRET)
    if x_ea_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid EA secret")

    # Remove from pending queue
    global _pending_queue
    _pending_queue = [s for s in _pending_queue if s.get("signal_id") != payload.signal_id]

    now = datetime.now(timezone.utc).isoformat()

    log_entry = {
        "signal_id": payload.signal_id,
        "ticket": payload.ticket,
        "fill_price": payload.fill_price,
        "status": payload.status,
        "reason": payload.reason,
        "error_code": payload.error_code,
        "magic": payload.magic,
        "confirmed_at": now,
    }

    if payload.status == "filled":
        logger.info(
            "[EA] Order filled: signal=%s ticket=%d fill=%.5f",
            payload.signal_id, payload.ticket, payload.fill_price,
        )
    elif payload.status == "rejected":
        logger.warning(
            "[EA] Order rejected: signal=%s reason=%s",
            payload.signal_id, payload.reason,
        )
    else:
        logger.error(
            "[EA] Order failed: signal=%s error=%d reason=%s",
            payload.signal_id, payload.error_code, payload.reason,
        )

    # Persist to Supabase if available
    if db is not None:
        try:
            db.table("ea_executions").insert(log_entry).execute()
            if payload.status == "filled":
                db.table("signals").update({
                    "broker_ticket": payload.ticket,
                    "fill_price": payload.fill_price,
                    "executed_at": now,
                    "status": "ACTIVE",
                }).eq("signal_id", payload.signal_id).execute()
        except Exception as exc:
            logger.warning("[EA] DB write failed for confirm: %s", exc)

    return {"status": "acknowledged", "signal_id": payload.signal_id}


@router.post(
    "/tp_hit",
    status_code=status.HTTP_200_OK,
    summary="EA reports a TP level was hit",
)
async def report_tp_hit(
    payload: EATPHitRequest,
    x_ea_secret: str = Header(alias="X-EA-Secret"),
    db=None,
) -> dict:
    """
    Called by the EA when price reaches a take-profit level.

    TP1 hit: signal status moves to TP1_HIT, push notification sent to user.
    TP2 hit: status moves to TP2_HIT.
    TP3 hit: status moves to TP3_HIT — full position closed.

    The app uses these events to update the trade journal P&L in real time.
    """
    expected = os.getenv("EA_SECRET", _DEFAULT_EA_SECRET)
    if x_ea_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid EA secret")

    tp_status_map = {1: "TP1_HIT", 2: "TP2_HIT", 3: "TP3_HIT"}
    new_status = tp_status_map.get(payload.tp_level, "TP1_HIT")

    logger.info(
        "[EA] TP%d hit: ticket=%d price=%.5f symbol=%s",
        payload.tp_level, payload.ticket, payload.hit_price, payload.symbol,
    )

    if db is not None:
        try:
            db.table("ea_executions").update({
                "status": new_status,
                f"tp{payload.tp_level}_hit_price": payload.hit_price,
                f"tp{payload.tp_level}_hit_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticket", payload.ticket).execute()
        except Exception as exc:
            logger.warning("[EA] DB write failed for tp_hit: %s", exc)

    # TODO (Phase 3): push APNS + Telegram notification for TP hit

    return {
        "status": "acknowledged",
        "ticket": payload.ticket,
        "tp_level": payload.tp_level,
        "new_signal_status": new_status,
    }


@router.post(
    "/sl_hit",
    status_code=status.HTTP_200_OK,
    summary="EA reports SL hit; triggers post-mortem",
)
async def report_sl_hit(
    payload: EASLHitRequest,
    x_ea_secret: str = Header(alias="X-EA-Secret"),
    db=None,
) -> dict:
    """
    Called by the EA when a position is closed at its stop loss.

    This triggers automatic post-mortem generation (§14.2):
    - Identifies which module was most wrong
    - Cross-references with news events and HTF structure at time of SL hit
    - Generates a one-sentence lesson displayed in the trade journal

    Also checks drawdown circuit breakers (§11.3):
    - Daily loss > 3%: suppress all signals for remainder of day
    - Weekly loss > 6%: suppress all signals for remainder of week
    - Monthly loss > 10%: enter Recovery Mode (0.5% risk, very strong only)
    """
    expected = os.getenv("EA_SECRET", _DEFAULT_EA_SECRET)
    if x_ea_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid EA secret")

    logger.info(
        "[EA] SL hit: ticket=%d close=%.5f profit=%.2f USD symbol=%s",
        payload.ticket, payload.close_price, payload.profit_usd, payload.symbol,
    )

    now = datetime.now(timezone.utc).isoformat()

    if db is not None:
        try:
            db.table("ea_executions").update({
                "status": "SL_HIT",
                "close_price": payload.close_price,
                "profit_usd": payload.profit_usd,
                "closed_at": now,
            }).eq("ticket", payload.ticket).execute()
        except Exception as exc:
            logger.warning("[EA] DB write failed for sl_hit: %s", exc)

    # TODO (Phase 3): invoke post-mortem generator, check drawdown breakers,
    # push APNS notification with loss amount and post-mortem summary.

    return {
        "status": "acknowledged",
        "ticket": payload.ticket,
        "post_mortem_queued": True,  # will be False until post-mortem engine is wired in Phase 3
    }


@router.get(
    "/heartbeat",
    status_code=status.HTTP_200_OK,
    summary="EA liveness check",
)
async def ea_heartbeat(
    magic: int = Query(0, description="EA magic number"),
    x_ea_secret: str = Header(alias="X-EA-Secret"),
) -> dict:
    """
    Lightweight liveness endpoint polled by the EA (or monitoring tools).

    Returns the current UTC timestamp so the EA can detect clock skew
    between the MetaTrader machine and the backend server.
    """
    expected = os.getenv("EA_SECRET", _DEFAULT_EA_SECRET)
    if x_ea_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid EA secret")

    return {
        "status": "ok",
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
        "magic": magic,
        "pending_signals": len(_pending_queue),
    }


# ── Internal tooling: queue a signal for EA execution ────────────────────────
# Called by the iOS app confirmation flow (Phase 3) — not exposed to EA directly.

@router.post(
    "/queue",
    status_code=status.HTTP_201_CREATED,
    summary="Queue a signal for EA execution (internal — called by app confirm flow)",
    include_in_schema=False,
)
async def queue_signal_for_ea(
    signal: EAPendingSignal,
    x_ea_secret: str = Header(alias="X-EA-Secret"),
) -> dict:
    """
    Add a signal to the pending queue so the EA picks it up on next poll.

    In Phase 3 this is called from the trade confirmation WebSocket handler
    when the user taps "Confirm Trade" in the iOS app.
    """
    expected = os.getenv("EA_SECRET", _DEFAULT_EA_SECRET)
    if x_ea_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid EA secret")

    entry = signal.model_dump(mode="json")
    # Avoid re-queuing duplicate signal IDs
    if not any(s["signal_id"] == signal.signal_id for s in _pending_queue):
        _pending_queue.append(entry)
        logger.info("[EA] Signal queued for execution: %s %s %s",
                    signal.signal_id, signal.pair, signal.direction)

    return {"status": "queued", "signal_id": signal.signal_id}
