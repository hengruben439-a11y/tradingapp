"""
Pydantic v2 request/response models for the made. API.

These models define the API contract between the backend and:
- iOS app (React Native)
- Telegram bot
- Internal signal engine

All monetary values are in USD. All timestamps are ISO 8601 UTC.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Shared enums ──────────────────────────────────────────────────────────────

class PairEnum(str, Enum):
    XAUUSD = "XAUUSD"
    GBPJPY = "GBPJPY"


class DirectionEnum(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradingStyleEnum(str, Enum):
    SCALPING = "scalping"
    DAY_TRADING = "day_trading"
    SWING_TRADING = "swing_trading"
    POSITION_TRADING = "position_trading"


class SignalStrengthEnum(str, Enum):
    VERY_STRONG = "very_strong"
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class MarketRegimeEnum(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    TRANSITIONAL = "TRANSITIONAL"
    UNKNOWN = "UNKNOWN"


class SignalStatusEnum(str, Enum):
    ACTIVE = "ACTIVE"
    TP1_HIT = "TP1_HIT"
    TP2_HIT = "TP2_HIT"
    TP3_HIT = "TP3_HIT"
    SL_HIT = "SL_HIT"
    EXPIRED = "EXPIRED"


class ImpactEnum(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SubscriptionTierEnum(str, Enum):
    FREE = "free"
    PREMIUM = "premium"
    PRO = "pro"


class UIModeEnum(str, Enum):
    SIMPLE = "simple"
    PRO = "pro"
    MAX = "max"


class JournalStatusEnum(str, Enum):
    OPEN = "OPEN"
    TP1_HIT = "TP1_HIT"
    TP2_HIT = "TP2_HIT"
    TP3_HIT = "TP3_HIT"
    SL_HIT = "SL_HIT"
    MANUALLY_CLOSED = "MANUALLY_CLOSED"


# ── Signal models ─────────────────────────────────────────────────────────────

class ModuleScoreResponse(BaseModel):
    """Score and metadata from a single confluence analysis module."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="Module name (e.g. 'market_structure')")
    weight: float = Field(..., ge=0.0, le=1.0, description="Module weight for this pair")
    raw_score: float = Field(..., ge=-1.0, le=1.0, description="Pre-cap score")
    capped_score: float = Field(..., ge=-0.85, le=0.85, description="After 0.85 cap")
    weighted_contribution: float = Field(..., description="capped_score * weight")
    aligned: bool = Field(..., description="True if score direction matches signal direction")
    note: Optional[str] = Field(None, description="Human-readable explanation for dissent UI")


class TPLevelResponse(BaseModel):
    """A single take-profit level."""

    model_config = ConfigDict(populate_by_name=True)

    level: int = Field(..., ge=1, le=3, description="TP level (1, 2, or 3)")
    price: float = Field(..., description="Target price")
    rr_ratio: float = Field(..., ge=0.0, description="Risk:Reward ratio (e.g. 2.0 = 1:2)")
    close_pct: float = Field(..., ge=0.0, le=1.0, description="Fraction of position to close here")
    source: str = Field(..., description="'structural' | 'atr_fallback' | 'fibonacci_extension'")


class SignalResponse(BaseModel):
    """
    Full signal object returned by the API.

    The iOS app uses this to render signal cards in Simple, Pro, and Max modes.
    Module scores are always present but the UI selectively shows them based on mode.
    """

    model_config = ConfigDict(populate_by_name=True)

    signal_id: str = Field(..., description="UUID")
    pair: PairEnum
    direction: DirectionEnum
    trading_style: TradingStyleEnum
    entry_timeframe: str = Field(..., description="e.g. '15m'")
    entry_price: float
    stop_loss: float
    tp1: TPLevelResponse
    tp2: TPLevelResponse
    tp3: TPLevelResponse
    sl_distance_pips: float
    confluence_score: float = Field(..., ge=-1.0, le=1.0)
    strength: SignalStrengthEnum
    module_scores: list[ModuleScoreResponse] = Field(
        default_factory=list,
        description="One per module (9 total). Always populated; UI filters by mode.",
    )
    regime: MarketRegimeEnum
    kill_zone_active: Optional[str] = Field(None, description="Name of active KZ, or None")
    htf_conflict: bool = Field(False, description="True if LTF signal conflicts with HTF")
    htf_conflict_description: Optional[str] = None
    news_risk: bool = Field(False, description="True if high-impact news within 15 min")
    news_event_name: Optional[str] = None
    unicorn_setup: bool = Field(False, description="OB + FVG overlap detected (1.10x multiplier)")
    applied_multipliers: list[str] = Field(
        default_factory=list, description="Human-readable list for Max mode display"
    )
    generated_at: datetime
    expiry_bars: int = Field(..., description="Signal valid for N bars from generation")
    status: SignalStatusEnum = SignalStatusEnum.ACTIVE
    decayed_score: Optional[float] = Field(
        None,
        description="Score adjusted for time elapsed (displayed_score = base * (1 - 0.25 * elapsed_fraction))",
    )


# ── Journal models ────────────────────────────────────────────────────────────

class JournalEntryCreate(BaseModel):
    """Request body for creating a new journal entry."""

    model_config = ConfigDict(populate_by_name=True)

    signal_id: Optional[str] = Field(None, description="Link to originating signal (None for manual)")
    pair: PairEnum
    direction: DirectionEnum
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    confluence_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    trading_style: TradingStyleEnum
    notes: Optional[str] = Field(None, max_length=2000)


class JournalEntryResponse(JournalEntryCreate):
    """Journal entry as returned by the API, including outcome data."""

    id: str
    user_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_at: Optional[datetime] = None
    pnl_pips: Optional[float] = None
    pnl_usd: Optional[float] = None
    r_multiple: Optional[float] = Field(
        None, description="R:R achieved (e.g. 1.8 = 1:1.8). Negative for losses."
    )
    status: JournalStatusEnum = JournalStatusEnum.OPEN
    post_mortem: Optional[dict] = Field(
        None,
        description="Auto-generated post-mortem when SL is hit (which module failed, what happened, lesson)",
    )


class JournalUpdateRequest(BaseModel):
    """Request body for updating a journal entry (adding exit data or notes)."""

    model_config = ConfigDict(populate_by_name=True)

    exit_price: Optional[float] = None
    exit_at: Optional[datetime] = None
    pnl_pips: Optional[float] = None
    pnl_usd: Optional[float] = None
    r_multiple: Optional[float] = None
    status: Optional[JournalStatusEnum] = None
    notes: Optional[str] = Field(None, max_length=2000)


# ── Analytics models ──────────────────────────────────────────────────────────

class PairAnalytics(BaseModel):
    """Performance breakdown for a single pair."""

    model_config = ConfigDict(populate_by_name=True)

    pair: PairEnum
    total_trades: int
    win_rate: float = Field(..., ge=0.0, le=1.0)
    profit_factor: Optional[float] = None
    avg_rr: Optional[float] = None
    total_pnl_usd: float


class StyleAnalytics(BaseModel):
    """Performance breakdown for a single trading style."""

    model_config = ConfigDict(populate_by_name=True)

    style: TradingStyleEnum
    total_trades: int
    win_rate: float = Field(..., ge=0.0, le=1.0)
    profit_factor: Optional[float] = None


class AnalyticsSummary(BaseModel):
    """Full analytics summary for a user's journal."""

    model_config = ConfigDict(populate_by_name=True)

    total_trades: int
    win_trades: int
    loss_trades: int
    be_trades: int = Field(0, description="Breakeven trades")
    win_rate: float = Field(..., ge=0.0, le=1.0)
    profit_factor: Optional[float] = None
    avg_rr: Optional[float] = None
    total_pnl_usd: float
    max_drawdown_pct: Optional[float] = Field(None, description="Max drawdown as fraction (0.0–1.0)")
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    by_pair: list[PairAnalytics] = Field(default_factory=list)
    by_style: list[StyleAnalytics] = Field(default_factory=list)
    by_day_of_week: dict[str, float] = Field(
        default_factory=dict,
        description="Win rate by day name (e.g. {'Monday': 0.62, 'Tuesday': 0.58})",
    )
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None


# ── Calendar models ───────────────────────────────────────────────────────────

class CalendarEvent(BaseModel):
    """A single economic calendar event."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str = Field(..., description="Event name (e.g. 'Non-Farm Payrolls')")
    impact: ImpactEnum
    scheduled_at: datetime = Field(..., description="UTC datetime of event")
    actual: Optional[str] = Field(None, description="Actual value (available after event)")
    forecast: Optional[str] = Field(None, description="Analyst forecast value")
    previous: Optional[str] = Field(None, description="Previous period value")
    currency: str = Field(..., description="Affected currency (e.g. 'USD', 'GBP', 'JPY')")
    pairs_affected: list[PairEnum] = Field(
        default_factory=list,
        description="Which trading pairs are likely affected",
    )
    description: Optional[str] = None


class TodayCalendarResponse(BaseModel):
    """Today's calendar events grouped for the daily rundown."""

    model_config = ConfigDict(populate_by_name=True)

    date: str = Field(..., description="Date in SGT (YYYY-MM-DD)")
    timezone: str = "SGT (UTC+8)"
    events: list[CalendarEvent]
    high_impact_count: int
    next_high_impact: Optional[CalendarEvent] = Field(
        None, description="The next upcoming high-impact event"
    )


# ── Auth models ───────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """
    Login via Apple Sign In (production) or email+password (dev/testing).

    In production, provide apple_identity_token.
    In dev mode, provide email + password.
    """

    model_config = ConfigDict(populate_by_name=True)

    apple_identity_token: Optional[str] = Field(
        None, description="Apple Sign In identity token (production)"
    )
    email: Optional[str] = Field(None, description="Email (dev/testing only)")
    password: Optional[str] = Field(None, description="Password (dev/testing only)")


class TokenResponse(BaseModel):
    """JWT token pair returned on successful authentication."""

    model_config = ConfigDict(populate_by_name=True)

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds")


class RefreshRequest(BaseModel):
    """Request body for token refresh."""

    model_config = ConfigDict(populate_by_name=True)

    refresh_token: str


class UserProfile(BaseModel):
    """User profile as returned by GET /auth/me."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: str
    email: Optional[str] = None
    subscription_tier: SubscriptionTierEnum = SubscriptionTierEnum.FREE
    ui_mode: UIModeEnum = UIModeEnum.SIMPLE
    trading_style: TradingStyleEnum = TradingStyleEnum.DAY_TRADING
    pairs: list[PairEnum] = Field(
        default_factory=lambda: [PairEnum.XAUUSD, PairEnum.GBPJPY],
        description="Pairs the user has enabled",
    )
    created_at: Optional[datetime] = None


class UserProfileUpdate(BaseModel):
    """Request body for updating user profile settings."""

    model_config = ConfigDict(populate_by_name=True)

    ui_mode: Optional[UIModeEnum] = None
    trading_style: Optional[TradingStyleEnum] = None
    pairs: Optional[list[PairEnum]] = None


# ── WebSocket message models ──────────────────────────────────────────────────

class WSMessageType(str, Enum):
    SIGNAL_NEW = "signal_new"
    SIGNAL_UPDATE = "signal_update"
    SIGNAL_EXPIRED = "signal_expired"
    TP_HIT = "tp_hit"
    SL_HIT = "sl_hit"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"


class WSMessage(BaseModel):
    """WebSocket message envelope."""

    model_config = ConfigDict(populate_by_name=True)

    type: WSMessageType
    payload: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
