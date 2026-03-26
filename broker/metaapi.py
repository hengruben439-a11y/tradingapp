"""
MetaApi Cloud REST API client for HFM MT4/MT5 broker integration.

Docs: https://metaapi.cloud/docs/client/
All operations are async. Account credentials are user-supplied and stored encrypted.

Config (from env):
    METAAPI_TOKEN: MetaApi cloud token
    METAAPI_ACCOUNT_ID: MT4/MT5 account ID in MetaApi

Supports:
- Account validation and connection
- Balance/equity/margin queries
- Open positions and trade history
- Market order placement with SL/TP
- Order modification (SL/TP adjustment)
- Order close
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

METAAPI_TOKEN = os.getenv("METAAPI_TOKEN", "")
METAAPI_ACCOUNT_ID = os.getenv("METAAPI_ACCOUNT_ID", "")

_BASE_URL = "https://mt-client-api-v1.agiliumtrade.agiliumtrade.ai"

_RETRY_STATUS_CODES = {429, 503}
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds; doubles each attempt


# ── Pydantic models ────────────────────────────────────────────────────────────


class AccountInfo(BaseModel):
    """Live account balance, equity, and margin snapshot."""

    model_config = ConfigDict(populate_by_name=True)

    balance: float = Field(..., description="Account balance in account currency")
    equity: float = Field(..., description="Account equity (balance + floating P&L)")
    margin: float = Field(..., description="Used margin")
    free_margin: float = Field(..., description="Free (available) margin")
    margin_level: float = Field(..., description="Margin level % (equity / margin × 100)")
    currency: str = Field(..., description="Account currency (e.g. 'USD')")


class Position(BaseModel):
    """A single open position on the broker account."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="MetaApi position ID")
    symbol: str = Field(..., description="Trading symbol (e.g. 'XAUUSD')")
    type: str = Field(
        ..., description="Direction: 'POSITION_TYPE_BUY' | 'POSITION_TYPE_SELL'"
    )
    volume: float = Field(..., description="Position size in lots")
    open_price: float = Field(..., description="Price at which the position was opened")
    current_price: float = Field(..., description="Current market price")
    stop_loss: Optional[float] = Field(None, description="Current stop loss level")
    take_profit: Optional[float] = Field(None, description="Current take profit level")
    profit: float = Field(..., description="Floating P&L in account currency")
    open_time: datetime = Field(..., description="UTC time when position was opened")


class OrderRequest(BaseModel):
    """Parameters for placing a market order via MetaApi."""

    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(..., description="'XAUUSD' or 'GBPJPY'")
    action_type: str = Field(
        ..., description="'ORDER_TYPE_BUY' | 'ORDER_TYPE_SELL'"
    )
    volume: float = Field(..., gt=0.0, description="Lot size")
    stop_loss: float = Field(..., description="Stop loss price level")
    take_profit: float = Field(
        ..., description="TP1 level — app manages TP2/TP3 via position monitoring"
    )
    comment: str = Field("made.", description="Order comment visible in MT4/MT5 terminal")
    slippage: int = Field(10, description="Max slippage tolerance in pips")


class OrderResult(BaseModel):
    """Result of a market order placement attempt."""

    model_config = ConfigDict(populate_by_name=True)

    order_id: str = Field(..., description="MetaApi order ID")
    position_id: str = Field(..., description="MetaApi position ID for the filled order")
    fill_price: float = Field(..., description="Actual execution price")
    requested_price: float = Field(..., description="Signal entry price at time of request")
    slippage_pips: float = Field(
        ..., description="Difference between requested and fill price in pips"
    )
    success: bool
    error_message: Optional[str] = Field(None, description="Set on failure")


class HistoricalOrder(BaseModel):
    """A closed order from the broker's trade history."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    symbol: str
    type: str
    volume: float
    open_price: float
    close_price: Optional[float] = None
    profit: float
    open_time: datetime
    close_time: Optional[datetime] = None
    comment: Optional[str] = None


# ── Client ─────────────────────────────────────────────────────────────────────


class MetaApiClient:
    """
    Async HTTP client wrapping the MetaApi Cloud REST API.

    Usage:
        async with MetaApiClient() as client:
            info = await client.get_account_info()

    Alternatively, call connect() / close() manually.
    Exponential backoff is applied on HTTP 429 and 503 (max 3 retries).
    """

    def __init__(
        self,
        token: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> None:
        self._token = token or METAAPI_TOKEN
        self._account_id = account_id or METAAPI_ACCOUNT_ID
        self._client: Optional[httpx.AsyncClient] = None

    # ── Context manager ────────────────────────────────────────────────────────

    async def __aenter__(self) -> "MetaApiClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Initialise the underlying httpx client."""
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30.0),
        )

    async def close(self) -> None:
        """Close the underlying httpx client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _assert_connected(self) -> None:
        if self._client is None:
            raise RuntimeError(
                "MetaApiClient not connected. Use 'async with MetaApiClient()' or call connect() first."
            )

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: object,
    ) -> httpx.Response:
        """
        Execute an HTTP request with exponential backoff retry on 429/503.

        Raises httpx.HTTPStatusError on non-retriable failure after exhausting retries.
        """
        self._assert_connected()
        assert self._client is not None  # type narrowing

        for attempt in range(_MAX_RETRIES):
            try:
                response = await self._client.request(method, path, **kwargs)

                if response.status_code in _RETRY_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "MetaApi %s %s → HTTP %d, retrying in %.1fs (attempt %d/%d)",
                        method,
                        path,
                        response.status_code,
                        delay,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError:
                if attempt == _MAX_RETRIES - 1:
                    raise
                # Non-retriable HTTP errors propagate immediately
                if response.status_code not in _RETRY_STATUS_CODES:
                    raise

        # Unreachable but satisfies type checker
        raise RuntimeError("Retry loop exhausted unexpectedly")

    def _account_path(self, suffix: str) -> str:
        """Build the standard account-scoped path."""
        return f"/users/current/accounts/{self._account_id}/{suffix}"

    # ── Public API ─────────────────────────────────────────────────────────────

    async def connect_account(self, account_id: str) -> dict:
        """
        Validate that an account ID exists in MetaApi and return its metadata.

        Args:
            account_id: The MetaApi account ID to look up.

        Returns:
            Raw account metadata dict from MetaApi.

        Raises:
            httpx.HTTPStatusError: If the account ID is not found or token is invalid.
        """
        response = await self._request(
            "GET", f"/users/current/accounts/{account_id}"
        )
        return response.json()

    async def get_account_info(self) -> AccountInfo:
        """
        Return the live balance, equity, and margin snapshot for the configured account.

        Returns:
            AccountInfo with balance, equity, margin, free_margin, margin_level, currency.
        """
        response = await self._request(
            "GET", self._account_path("account-information")
        )
        data = response.json()
        return AccountInfo(
            balance=data["balance"],
            equity=data["equity"],
            margin=data.get("margin", 0.0),
            free_margin=data.get("freeMargin", data.get("free_margin", 0.0)),
            margin_level=data.get("marginLevel", data.get("margin_level", 0.0)),
            currency=data.get("currency", "USD"),
        )

    async def get_positions(self) -> list[Position]:
        """
        Return all currently open positions on the account.

        Returns:
            List of Position objects (empty list if no open positions).
        """
        response = await self._request("GET", self._account_path("positions"))
        positions = []
        for raw in response.json():
            positions.append(
                Position(
                    id=raw["id"],
                    symbol=raw["symbol"],
                    type=raw["type"],
                    volume=raw["volume"],
                    open_price=raw["openPrice"],
                    current_price=raw.get("currentPrice", raw.get("current_price", 0.0)),
                    stop_loss=raw.get("stopLoss") or raw.get("stop_loss"),
                    take_profit=raw.get("takeProfit") or raw.get("take_profit"),
                    profit=raw.get("profit", 0.0),
                    open_time=datetime.fromisoformat(
                        raw["time"].replace("Z", "+00:00")
                        if isinstance(raw["time"], str)
                        else raw["time"]
                    ),
                )
            )
        return positions

    async def get_history_orders(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HistoricalOrder]:
        """
        Return closed orders between start_time and end_time (UTC).

        Args:
            start_time: Start of the query range (UTC-aware datetime).
            end_time: End of the query range (UTC-aware datetime).

        Returns:
            List of HistoricalOrder objects, sorted by open_time ascending.
        """
        path = self._account_path("history-orders/time") + (
            f"/{start_time.isoformat()}/{end_time.isoformat()}"
        )
        response = await self._request("GET", path)
        orders = []
        for raw in response.json():
            orders.append(
                HistoricalOrder(
                    id=raw["id"],
                    symbol=raw["symbol"],
                    type=raw["type"],
                    volume=raw["volume"],
                    open_price=raw.get("openPrice", 0.0),
                    close_price=raw.get("closePrice") or raw.get("close_price"),
                    profit=raw.get("profit", 0.0),
                    open_time=datetime.fromisoformat(
                        raw["time"].replace("Z", "+00:00")
                        if isinstance(raw["time"], str)
                        else raw["time"]
                    ),
                    close_time=(
                        datetime.fromisoformat(
                            raw["doneTime"].replace("Z", "+00:00")
                            if isinstance(raw.get("doneTime"), str)
                            else raw["doneTime"]
                        )
                        if raw.get("doneTime")
                        else None
                    ),
                    comment=raw.get("comment"),
                )
            )
        return orders

    async def place_order(self, order: OrderRequest) -> OrderResult:
        """
        Place a market order on the configured account.

        Args:
            order: OrderRequest containing symbol, direction, volume, SL, TP.

        Returns:
            OrderResult with fill details. Check success field before using position_id.

        Note:
            TP is set to TP1 only. The ExecutionManager monitors the position and
            handles TP2/TP3 partial closes directly.
        """
        payload = {
            "actionType": order.action_type,
            "symbol": order.symbol,
            "volume": order.volume,
            "stopLoss": order.stop_loss,
            "takeProfit": order.take_profit,
            "comment": order.comment,
            "slippage": order.slippage,
        }

        try:
            response = await self._request(
                "POST", self._account_path("trade"), json=payload
            )
            data = response.json()
            fill_price = data.get("openPrice", data.get("open_price", 0.0))
            requested = data.get("requestedPrice", fill_price)
            pip_size = _pip_size_for_symbol(order.symbol)
            slippage_pips = abs(fill_price - requested) / pip_size if pip_size > 0 else 0.0

            return OrderResult(
                order_id=data.get("orderId", data.get("order_id", "")),
                position_id=data.get("positionId", data.get("position_id", "")),
                fill_price=fill_price,
                requested_price=requested,
                slippage_pips=round(slippage_pips, 2),
                success=True,
            )
        except httpx.HTTPStatusError as exc:
            logger.error("place_order failed: %s", exc)
            return OrderResult(
                order_id="",
                position_id="",
                fill_price=0.0,
                requested_price=0.0,
                slippage_pips=0.0,
                success=False,
                error_message=str(exc),
            )

    async def modify_order(
        self,
        position_id: str,
        sl: float,
        tp: float,
    ) -> bool:
        """
        Modify the SL and TP on an open position.

        Args:
            position_id: MetaApi position ID.
            sl: New stop loss price.
            tp: New take profit price.

        Returns:
            True on success, False on failure.
        """
        payload = {
            "actionType": "POSITION_MODIFY",
            "positionId": position_id,
            "stopLoss": sl,
            "takeProfit": tp,
        }
        try:
            await self._request(
                "POST", self._account_path("trade"), json=payload
            )
            return True
        except httpx.HTTPStatusError as exc:
            logger.error("modify_order(%s) failed: %s", position_id, exc)
            return False

    async def close_position(
        self,
        position_id: str,
        volume: Optional[float] = None,
    ) -> bool:
        """
        Close a position fully, or partially if volume is specified.

        Args:
            position_id: MetaApi position ID to close.
            volume: Lots to close. None = close entire position.

        Returns:
            True on success, False on failure.
        """
        payload: dict = {
            "actionType": "POSITION_CLOSE_ID",
            "positionId": position_id,
        }
        if volume is not None:
            payload["volume"] = volume

        try:
            await self._request(
                "POST", self._account_path("trade"), json=payload
            )
            return True
        except httpx.HTTPStatusError as exc:
            logger.error("close_position(%s) failed: %s", position_id, exc)
            return False

    async def close_all_positions(self) -> int:
        """
        Close every open position on the account.

        Returns:
            Number of positions successfully closed.
        """
        positions = await self.get_positions()
        closed = 0
        for pos in positions:
            success = await self.close_position(pos.id)
            if success:
                closed += 1
        return closed

    # ── Utility ────────────────────────────────────────────────────────────────

    @staticmethod
    def is_price_within_validity(
        signal_entry: float,
        current_price: float,
        atr: float,
        tolerance: float = 0.5,
    ) -> bool:
        """
        Check whether current_price is still close enough to signal_entry to execute.

        A signal's entry is valid only while price is within tolerance × ATR of the
        original entry price. Beyond that the setup is considered stale.

        Args:
            signal_entry: Entry price from the signal at generation time.
            current_price: Live price at the moment of execution attempt.
            atr: ATR(14) value for the pair/timeframe at signal time.
            tolerance: Multiplier of ATR for acceptable deviation (default 0.5).

        Returns:
            True if |current_price - signal_entry| <= tolerance * atr.
        """
        if atr <= 0:
            return False
        return abs(current_price - signal_entry) <= tolerance * atr


# ── Module-level helpers (used by broker.execution) ───────────────────────────


def _pip_size_for_symbol(symbol: str) -> float:
    """Return the pip decimal size for a given symbol."""
    if symbol == "GBPJPY":
        return 0.01
    elif symbol == "XAUUSD":
        return 0.1
    return 0.0001
