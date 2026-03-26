"""
Broker integration router — MetaApi account, execution, and risk endpoints.

All routes require authentication (JWT bearer token via get_current_user).
Dev mode: returns mock data when MetaApi credentials are not configured.

Endpoints:
    GET  /broker/account          — balance, equity, positions count
    GET  /broker/positions        — list open positions
    POST /broker/execute          — execute a confirmed signal
    POST /broker/close/{id}       — close a position
    PUT  /broker/position/{id}/sl — modify stop loss on open position
    GET  /broker/risk-status      — current risk guards state
    POST /broker/paper/execute    — paper trading execution (simulated)
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field

from api.auth import get_current_user
from api.redis_client import get_redis
from broker.correlation import CorrelationEngine, CorrelationWarning
from broker.execution import ExecutionManager, ExecutionResult
from broker.metaapi import AccountInfo, MetaApiClient, OrderRequest, Position
from broker.risk_guards import RiskGuards

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/broker", tags=["broker"])

# ── Singletons (per-process — replaced with Redis-backed state in production) ──

_risk_guards = RiskGuards(initial_equity_peak=10_000.0)
_correlation_engine = CorrelationEngine()

# ── In-memory paper trading journal (dev/test) ─────────────────────────────────
_paper_trades: list[dict] = []


# ── Request / response models ──────────────────────────────────────────────────


class AccountSummaryResponse(BaseModel):
    """Condensed account snapshot for the dashboard header."""

    model_config = ConfigDict(populate_by_name=True)

    balance: float
    equity: float
    free_margin: float
    margin_level: float
    currency: str
    open_positions_count: int
    is_configured: bool = Field(
        ...,
        description="False when MetaApi credentials are not set (dev mode)",
    )


class ExecuteSignalRequest(BaseModel):
    """Request body for POST /broker/execute."""

    model_config = ConfigDict(populate_by_name=True)

    signal_id: str = Field(..., description="UUID of the confirmed signal to execute")
    pair: str = Field(..., description="'XAUUSD' or 'GBPJPY'")
    direction: str = Field(..., description="'BUY' or 'SELL'")
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    atr: float = Field(..., description="ATR(14) value used for validity window check")
    current_price: float = Field(
        ..., description="Live price at the time the user taps Confirm"
    )
    risk_pct: Optional[float] = Field(
        None, description="Risk % override. Defaults to server-side default (1%)."
    )


class ExecuteSignalResponse(BaseModel):
    """Response from POST /broker/execute."""

    model_config = ConfigDict(populate_by_name=True)

    success: bool
    signal_id: str
    position_id: str
    fill_price: float
    lot_size: float
    dollar_risk: float
    slippage_pips: float
    error: Optional[str] = None
    correlation_warning: Optional[dict] = Field(
        None,
        description="Populated if a macro conflict was detected but trade was allowed",
    )


class ModifySlRequest(BaseModel):
    """Request body for PUT /broker/position/{id}/sl."""

    model_config = ConfigDict(populate_by_name=True)

    stop_loss: float = Field(..., description="New stop loss price")
    take_profit: Optional[float] = Field(
        None, description="Updated take profit (optional — omit to leave unchanged)"
    )


class PaperExecuteRequest(BaseModel):
    """Request body for POST /broker/paper/execute."""

    model_config = ConfigDict(populate_by_name=True)

    signal_id: str
    pair: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    lot_size: float
    account_balance: float = Field(10_000.0, description="Paper account balance")


class PaperExecuteResponse(BaseModel):
    """Response from POST /broker/paper/execute."""

    model_config = ConfigDict(populate_by_name=True)

    success: bool
    paper_trade_id: str
    signal_id: str
    fill_price: float      # Simulated at entry_price (no real spread in paper mode)
    lot_size: float
    dollar_risk: float
    created_at: datetime


# ── Helper: build MetaApi client from env ──────────────────────────────────────


def _is_metaapi_configured() -> bool:
    return bool(os.getenv("METAAPI_TOKEN")) and bool(os.getenv("METAAPI_ACCOUNT_ID"))


async def _get_execution_manager(redis: object) -> Optional[ExecutionManager]:
    """Build an ExecutionManager if MetaApi credentials are available."""
    if not _is_metaapi_configured():
        return None
    client = MetaApiClient()
    await client.connect()
    return ExecutionManager(client, redis, risk_pct=1.0)


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get(
    "/account",
    response_model=AccountSummaryResponse,
    summary="Get broker account summary",
)
async def get_account(
    current_user: dict = Depends(get_current_user),
    redis: object = Depends(get_redis),
) -> AccountSummaryResponse:
    """
    Return the live balance, equity, and open positions count.

    Returns mock data when MetaApi credentials are not configured (dev mode).
    """
    if not _is_metaapi_configured():
        return AccountSummaryResponse(
            balance=10_000.0,
            equity=10_250.0,
            free_margin=9_800.0,
            margin_level=9800.0,
            currency="USD",
            open_positions_count=0,
            is_configured=False,
        )

    async with MetaApiClient() as client:
        try:
            info = await client.get_account_info()
            positions = await client.get_positions()
        except Exception as exc:
            logger.error("get_account failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"MetaApi unavailable: {exc}",
            )

    return AccountSummaryResponse(
        balance=info.balance,
        equity=info.equity,
        free_margin=info.free_margin,
        margin_level=info.margin_level,
        currency=info.currency,
        open_positions_count=len(positions),
        is_configured=True,
    )


@router.get(
    "/positions",
    response_model=list[Position],
    summary="List open positions",
)
async def get_positions(
    current_user: dict = Depends(get_current_user),
) -> list[Position]:
    """
    Return all currently open positions on the linked broker account.

    Returns an empty list in dev mode (no MetaApi credentials).
    """
    if not _is_metaapi_configured():
        return []

    async with MetaApiClient() as client:
        try:
            return await client.get_positions()
        except Exception as exc:
            logger.error("get_positions failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"MetaApi unavailable: {exc}",
            )


@router.post(
    "/execute",
    response_model=ExecuteSignalResponse,
    summary="Execute a confirmed signal",
    status_code=status.HTTP_201_CREATED,
)
async def execute_signal(
    body: ExecuteSignalRequest,
    current_user: dict = Depends(get_current_user),
    redis: object = Depends(get_redis),
) -> ExecuteSignalResponse:
    """
    Execute a signal on the linked HFM MT4/MT5 account via MetaApi.

    Pre-execution checks (in order):
    1. Risk guards: daily risk, weekly/monthly drawdown, max signals per pair
    2. Correlation check: macro conflict warning
    3. Price validity: signal entry still within 0.5× ATR of current price
    4. Lot size calculation and order placement

    HTTP 403 is returned if any hard risk limit is breached.
    HTTP 400 is returned if the price validity check fails.
    A 201 with a correlation_warning field is returned for soft conflicts (warning only).
    """
    global _risk_guards

    # ── 1. Risk guards ────────────────────────────────────────────────────────
    risk_pct = body.risk_pct or 1.0
    effective_risk = _risk_guards.get_effective_risk_pct(risk_pct)

    allowed, reason = _risk_guards.can_trade(body.pair, effective_risk, news_flag=False)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    # ── 2. Correlation check ──────────────────────────────────────────────────
    # Build active signals list from Redis or in-memory (simplified for now)
    active_signals: list[dict] = []
    correlation_warning_dict: Optional[dict] = None

    # Estimate account balance for exposure calculation
    account_balance = 10_000.0
    if _is_metaapi_configured():
        try:
            async with MetaApiClient() as client:
                info = await client.get_account_info()
                account_balance = info.balance
        except Exception:
            pass  # Use fallback balance

    from broker.execution import ExecutionManager as _EM
    sl_pips = _EM._sl_pips(body.entry_price, body.stop_loss, body.pair)
    from broker.execution import ExecutionManager as _EM2
    pip_val = _EM2._pip_value(body.pair, 1.0)
    lot_size_estimate = (
        (account_balance * effective_risk / 100.0) / (sl_pips * pip_val)
        if sl_pips > 0 and pip_val > 0
        else 0.01
    )

    warning = _correlation_engine.check_new_signal(
        pair=body.pair,
        direction=body.direction,
        lot_size=lot_size_estimate,
        account_balance=account_balance,
        active_signals=active_signals,
    )

    if warning is not None and warning.severity == "block":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=warning.message,
        )

    if warning is not None:
        correlation_warning_dict = {
            "type": warning.type,
            "message": warning.message,
            "severity": warning.severity,
        }

    # ── 3 & 4. Execute via MetaApi ────────────────────────────────────────────
    if not _is_metaapi_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "MetaApi credentials not configured. "
                "Use POST /broker/paper/execute for paper trading."
            ),
        )

    async with MetaApiClient() as api_client:
        try:
            info = await api_client.get_account_info()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to fetch account info: {exc}",
            )

        manager = ExecutionManager(api_client, redis, risk_pct=effective_risk)
        result = await manager.execute_signal(body.model_dump(), info)

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Execution failed",
        )

    # Update risk state
    _risk_guards.record_signal_open(body.pair, effective_risk)
    _risk_guards.update_equity_peak(info.equity)

    return ExecuteSignalResponse(
        success=True,
        signal_id=result.signal_id,
        position_id=result.position_id,
        fill_price=result.fill_price,
        lot_size=result.lot_size,
        dollar_risk=result.dollar_risk,
        slippage_pips=result.slippage_pips,
        correlation_warning=correlation_warning_dict,
    )


@router.post(
    "/close/{position_id}",
    summary="Close a position",
    status_code=status.HTTP_200_OK,
)
async def close_position(
    position_id: str = Path(..., description="MetaApi position ID"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Close a position by its MetaApi position ID.

    Closes the full position. For partial closes, the ExecutionManager handles
    those automatically at TP1/TP2 levels during position monitoring.
    """
    if not _is_metaapi_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaApi credentials not configured.",
        )

    async with MetaApiClient() as client:
        success = await client.close_position(position_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to close position {position_id}. It may already be closed.",
        )

    return {"success": True, "position_id": position_id}


@router.put(
    "/position/{position_id}/sl",
    summary="Modify stop loss on open position",
    status_code=status.HTTP_200_OK,
)
async def modify_stop_loss(
    body: ModifySlRequest,
    position_id: str = Path(..., description="MetaApi position ID"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Modify the stop loss (and optionally take profit) on an open position.

    Used for manual SL adjustments, breakeven moves, or trailing from the app.
    The ExecutionManager handles automated SL trailing at TP1/TP2 internally.
    """
    if not _is_metaapi_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MetaApi credentials not configured.",
        )

    async with MetaApiClient() as client:
        # Fetch current TP if not provided
        if body.take_profit is None:
            positions = await client.get_positions()
            pos_map = {p.id: p for p in positions}
            current_pos = pos_map.get(position_id)
            tp = current_pos.take_profit if current_pos and current_pos.take_profit else 0.0
        else:
            tp = body.take_profit

        success = await client.modify_order(position_id, sl=body.stop_loss, tp=tp)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to modify position {position_id}.",
        )

    return {
        "success": True,
        "position_id": position_id,
        "new_stop_loss": body.stop_loss,
        "new_take_profit": tp,
    }


@router.get(
    "/risk-status",
    summary="Get current risk guards state",
)
async def get_risk_status(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Return the full risk guard state including drawdown counters, cooldown status,
    suppressed patterns, and active signal counts.

    Used by the app's risk dashboard and the Max mode signal filter panel.
    """
    return _risk_guards.get_status()


@router.post(
    "/paper/execute",
    response_model=PaperExecuteResponse,
    summary="Paper trading execution (simulated)",
    status_code=status.HTTP_201_CREATED,
)
async def paper_execute(
    body: PaperExecuteRequest,
    current_user: dict = Depends(get_current_user),
) -> PaperExecuteResponse:
    """
    Simulate trade execution for paper trading mode.

    Fills at the signal's entry_price with no real spread applied.
    All paper trades are logged separately and never mixed with live trades.
    The paper trade is stored in-memory (dev) or in Supabase with a paper=True flag.

    Risk guards are NOT enforced for paper trading — the purpose of paper mode
    is to practice and validate the engine without financial consequences.
    """
    from broker.execution import ExecutionManager as _EM

    paper_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    sl_pips = _EM._sl_pips(body.entry_price, body.stop_loss, body.pair)
    pip_val = _EM._pip_value(body.pair, 1.0)
    dollar_risk = body.lot_size * sl_pips * pip_val

    trade = {
        "paper_trade_id": paper_id,
        "signal_id": body.signal_id,
        "user_id": current_user.get("sub", "unknown"),
        "pair": body.pair,
        "direction": body.direction,
        "entry_price": body.entry_price,
        "stop_loss": body.stop_loss,
        "tp1": body.tp1,
        "tp2": body.tp2,
        "tp3": body.tp3,
        "lot_size": body.lot_size,
        "dollar_risk": dollar_risk,
        "fill_price": body.entry_price,   # paper mode: fill at signal price
        "status": "OPEN",
        "paper": True,
        "created_at": now.isoformat(),
    }

    _paper_trades.append(trade)

    logger.info(
        "Paper trade executed: %s %s %s %.2f lots @ %.5f",
        body.direction,
        body.pair,
        paper_id,
        body.lot_size,
        body.entry_price,
    )

    return PaperExecuteResponse(
        success=True,
        paper_trade_id=paper_id,
        signal_id=body.signal_id,
        fill_price=body.entry_price,
        lot_size=body.lot_size,
        dollar_risk=round(dollar_risk, 2),
        created_at=now,
    )
