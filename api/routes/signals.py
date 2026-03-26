"""
Signals router — active and historical trading signal endpoints.

Signals are the core product output of the made. confluence engine.
Each signal includes entry, SL, 3 TP levels, module scores, and context flags.

Dev mode (no Supabase): returns in-memory mock signals so the iOS app can
be developed and tested without a live database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from api.auth import get_optional_user
from api.database import get_db
from api.models import (
    DirectionEnum,
    MarketRegimeEnum,
    ModuleScoreResponse,
    PairEnum,
    SignalResponse,
    SignalStatusEnum,
    SignalStrengthEnum,
    TPLevelResponse,
    TradingStyleEnum,
)

router = APIRouter(prefix="/signals", tags=["signals"])

# ── Dev mode in-memory signal store ──────────────────────────────────────────
# Populated with one mock signal per pair so the app renders on first launch.
# Cleared and replaced by the live engine in production.
_mock_signals: dict[str, dict] = {}


def _build_mock_signals() -> dict[str, dict]:
    """Build a small set of realistic-looking mock signals for dev mode."""
    now = datetime.now(timezone.utc)

    def make_module_scores(direction: str) -> list[dict]:
        aligned = direction == "BUY"
        return [
            {"name": "market_structure", "weight": 0.25, "raw_score": 0.80 if aligned else -0.80,
             "capped_score": 0.80 if aligned else -0.80, "weighted_contribution": 0.20 if aligned else -0.20,
             "aligned": True, "note": "Bullish BOS confirmed on 15m" if aligned else "Bearish CHoCH confirmed on 15m"},
            {"name": "order_blocks_fvg", "weight": 0.20, "raw_score": 0.90 if aligned else -0.70,
             "capped_score": 0.85 if aligned else -0.70, "weighted_contribution": 0.17 if aligned else -0.14,
             "aligned": True, "note": "Price at unmitigated bullish OB" if aligned else "Price at unmitigated bearish OB"},
            {"name": "ote_fibonacci", "weight": 0.15, "raw_score": 0.80 if aligned else 0.0,
             "capped_score": 0.80 if aligned else 0.0, "weighted_contribution": 0.12 if aligned else 0.0,
             "aligned": aligned, "note": "Price in OTE zone (61.8%–78.6%)" if aligned else "Price not in OTE zone"},
            {"name": "ema_alignment", "weight": 0.10, "raw_score": 1.0 if aligned else -1.0,
             "capped_score": 0.85 if aligned else -0.85, "weighted_contribution": 0.085 if aligned else -0.085,
             "aligned": True, "note": "Perfect bullish EMA stack" if aligned else "Perfect bearish EMA stack"},
            {"name": "rsi", "weight": 0.08, "raw_score": 0.60 if aligned else -0.60,
             "capped_score": 0.60 if aligned else -0.60, "weighted_contribution": 0.048 if aligned else -0.048,
             "aligned": True, "note": "RSI at 38 — approaching oversold" if aligned else "RSI at 68 — approaching overbought"},
            {"name": "macd", "weight": 0.07, "raw_score": 0.80 if aligned else -0.40,
             "capped_score": 0.80 if aligned else -0.40, "weighted_contribution": 0.056 if aligned else -0.028,
             "aligned": True, "note": "Bullish MACD crossover near zero line" if aligned else "MACD histogram declining"},
            {"name": "bollinger_bands", "weight": 0.05, "raw_score": 0.50 if aligned else 0.0,
             "capped_score": 0.50 if aligned else 0.0, "weighted_contribution": 0.025 if aligned else 0.0,
             "aligned": aligned, "note": "BB squeeze breakout upward" if aligned else "No squeeze detected"},
            {"name": "kill_zone", "weight": 0.05, "raw_score": 0.80 if aligned else 0.80,
             "capped_score": 0.80, "weighted_contribution": 0.04,
             "aligned": True, "note": "London Kill Zone active"},
            {"name": "support_resistance", "weight": 0.05, "raw_score": 0.70 if aligned else -0.50,
             "capped_score": 0.70 if aligned else -0.50, "weighted_contribution": 0.035 if aligned else -0.025,
             "aligned": True, "note": "Price bouncing from strong S/R cluster" if aligned else "Price rejected at resistance"},
        ]

    xau_id = str(uuid.uuid4())
    gj_id = str(uuid.uuid4())

    signals = {
        xau_id: {
            "signal_id": xau_id,
            "pair": "XAUUSD",
            "direction": "BUY",
            "trading_style": "day_trading",
            "entry_timeframe": "15m",
            "entry_price": 3045.50,
            "stop_loss": 3032.00,
            "tp1": {"level": 1, "price": 3059.00, "rr_ratio": 1.0, "close_pct": 0.40, "source": "structural"},
            "tp2": {"level": 2, "price": 3072.50, "rr_ratio": 2.0, "close_pct": 0.30, "source": "structural"},
            "tp3": {"level": 3, "price": 3091.00, "rr_ratio": 3.37, "close_pct": 0.30, "source": "fibonacci_extension"},
            "sl_distance_pips": 135.0,
            "confluence_score": 0.78,
            "strength": "strong",
            "module_scores": make_module_scores("BUY"),
            "regime": "TRENDING",
            "kill_zone_active": "London",
            "htf_conflict": False,
            "htf_conflict_description": None,
            "news_risk": False,
            "news_event_name": None,
            "unicorn_setup": True,
            "applied_multipliers": ["ICT Unicorn (OB+FVG): 1.10x", "Kill Zone (London): 1.05x"],
            "generated_at": now.isoformat(),
            "expiry_bars": 8,
            "status": "ACTIVE",
            "decayed_score": 0.78,
        },
        gj_id: {
            "signal_id": gj_id,
            "pair": "GBPJPY",
            "direction": "SELL",
            "trading_style": "day_trading",
            "entry_timeframe": "15m",
            "entry_price": 195.420,
            "stop_loss": 195.820,
            "tp1": {"level": 1, "price": 195.020, "rr_ratio": 1.0, "close_pct": 0.40, "source": "structural"},
            "tp2": {"level": 2, "price": 194.620, "rr_ratio": 2.0, "close_pct": 0.30, "source": "structural"},
            "tp3": {"level": 3, "price": 194.020, "rr_ratio": 3.5, "close_pct": 0.30, "source": "structural"},
            "sl_distance_pips": 40.0,
            "confluence_score": 0.71,
            "strength": "strong",
            "module_scores": make_module_scores("SELL"),
            "regime": "TRENDING",
            "kill_zone_active": "London",
            "htf_conflict": False,
            "htf_conflict_description": None,
            "news_risk": False,
            "news_event_name": None,
            "unicorn_setup": False,
            "applied_multipliers": ["Kill Zone (London): 1.05x"],
            "generated_at": now.isoformat(),
            "expiry_bars": 8,
            "status": "ACTIVE",
            "decayed_score": 0.71,
        },
    }
    return signals


_mock_signals = _build_mock_signals()

# ── Internal API key for engine → API communication ──────────────────────────
_INTERNAL_API_KEY = "internal-dev-key"


def _verify_internal_key(x_internal_key: str = Header(alias="X-Internal-Key")) -> str:
    """Verify the internal API key used by the signal engine."""
    import os
    expected = os.getenv("INTERNAL_API_KEY", _INTERNAL_API_KEY)
    if x_internal_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key",
        )
    return x_internal_key


def _strength_from_score(pair: str, score: float) -> str:
    """Map a raw confluence score to strength label."""
    abs_score = abs(score)
    if abs_score >= 0.80:
        return "very_strong"
    elif abs_score >= 0.65:
        return "strong"
    elif abs_score >= 0.50:
        return "moderate"
    else:
        return "weak"


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SignalResponse], summary="List active signals")
async def list_signals(
    pair: Optional[PairEnum] = Query(None, description="Filter by pair"),
    style: Optional[TradingStyleEnum] = Query(None, description="Filter by trading style"),
    min_strength: Optional[SignalStrengthEnum] = Query(None, description="Minimum signal strength"),
    db=Depends(get_db),
    user: Optional[dict] = Depends(get_optional_user),
) -> list[dict]:
    """
    Return all currently active signals.

    Ordered by confluence_score descending (strongest first).
    In dev mode (no Supabase), returns mock signals.

    Simple-tier users receive at most 2 signals (filtered server-side when
    the X-UI-Mode header indicates simple mode — enforcement deferred to Phase 2).
    """
    _strength_order = {"very_strong": 4, "strong": 3, "moderate": 2, "weak": 1}
    min_strength_val = _strength_order.get(min_strength.value, 0) if min_strength else 0

    if db is None:
        # Dev mode — return in-memory mock signals
        results = list(_mock_signals.values())
    else:
        try:
            query = db.table("signals").select("*").eq("status", "ACTIVE").order(
                "confluence_score", desc=True
            )
            response = query.execute()
            results = response.data or []
        except Exception:
            results = list(_mock_signals.values())

    # Apply filters
    if pair:
        results = [s for s in results if s.get("pair") == pair.value]
    if style:
        results = [s for s in results if s.get("trading_style") == style.value]
    if min_strength_val > 0:
        results = [
            s for s in results
            if _strength_order.get(s.get("strength", "weak"), 0) >= min_strength_val
        ]

    return results


@router.get("/history", response_model=list[SignalResponse], summary="Signal history (paginated)")
async def signal_history(
    pair: Optional[PairEnum] = Query(None),
    style: Optional[TradingStyleEnum] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    db=Depends(get_db),
    user: dict = Depends(get_optional_user),
) -> list[dict]:
    """
    Return historical (non-active) signals with pagination.

    Requires authentication for full signal data.
    Anonymous users receive an empty list (free-tier gate).
    """
    if user is None:
        return []

    if db is None:
        # Dev mode — return mock signals as "historical" with SL_HIT status
        results = [dict(s, status="SL_HIT") for s in list(_mock_signals.values())]
        return results[offset : offset + limit]

    try:
        query = (
            db.table("signals")
            .select("*")
            .neq("status", "ACTIVE")
            .order("generated_at", desc=True)
            .limit(limit)
            .offset(offset)
        )
        if pair:
            query = query.eq("pair", pair.value)
        if style:
            query = query.eq("trading_style", style.value)
        if from_date:
            query = query.gte("generated_at", from_date.isoformat())
        if to_date:
            query = query.lte("generated_at", to_date.isoformat())

        response = query.execute()
        return response.data or []
    except Exception:
        return []


@router.get("/{signal_id}", response_model=SignalResponse, summary="Get single signal detail")
async def get_signal(
    signal_id: str,
    db=Depends(get_db),
    user: Optional[dict] = Depends(get_optional_user),
) -> dict:
    """
    Return full detail for a single signal, including all 9 module scores.

    Used by the Signal Detail screen in the iOS app (Pro and Max modes).
    """
    # Check in-memory cache first (covers dev mode and hot signals)
    if signal_id in _mock_signals:
        return _mock_signals[signal_id]

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal '{signal_id}' not found",
        )

    try:
        response = db.table("signals").select("*").eq("signal_id", signal_id).execute()
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal '{signal_id}' not found",
            )
        return response.data[0]
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal '{signal_id}' not found",
        )


@router.post(
    "/shadow",
    status_code=status.HTTP_201_CREATED,
    summary="Record shadow mode signal (internal use)",
)
async def record_shadow_signal(
    signal: SignalResponse,
    _: str = Depends(_verify_internal_key),
    db=Depends(get_db),
) -> dict:
    """
    Internal endpoint — called by the signal engine during shadow mode validation.

    Logs the signal without pushing it to any user. Used to track shadow mode
    performance against actual market outcomes (Phase 1.5).
    """
    signal_dict = signal.model_dump(mode="json")
    signal_dict["is_shadow"] = True

    # Store in memory for dev mode
    _mock_signals[signal.signal_id] = signal_dict

    if db is not None:
        try:
            db.table("shadow_signals").insert(signal_dict).execute()
        except Exception:
            pass  # Shadow logging failure should not block the engine

    return {"status": "recorded", "signal_id": signal.signal_id}


@router.delete(
    "/{signal_id}",
    status_code=status.HTTP_200_OK,
    summary="Expire a signal (internal use)",
)
async def expire_signal(
    signal_id: str,
    _: str = Depends(_verify_internal_key),
    db=Depends(get_db),
) -> dict:
    """
    Internal endpoint — called by the signal engine to mark a signal as EXPIRED.

    Triggered when: signal_expiry_bars elapsed, price moved too far from entry,
    or a newer conflicting signal supersedes it.
    """
    # Remove from in-memory store
    _mock_signals.pop(signal_id, None)

    if db is not None:
        try:
            db.table("signals").update({"status": "EXPIRED"}).eq(
                "signal_id", signal_id
            ).execute()
        except Exception:
            pass

    return {"status": "expired", "signal_id": signal_id}
