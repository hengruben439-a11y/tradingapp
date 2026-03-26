"""
Analytics router.

Provides performance analytics derived from the user's trade journal.
All analytics are computed from closed journal entries.

Endpoints:
- /analytics/summary — overall stats (win rate, profit factor, Sharpe, etc.)
- /analytics/equity-curve — time series of equity + drawdown
- /analytics/monthly-pnl — monthly P&L heatmap data
- /analytics/by-session — performance breakdown by Kill Zone session
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.auth import get_current_user
from api.database import get_db
from api.models import AnalyticsSummary, PairEnum, TradingStyleEnum
from api.routes.journal import _calculate_stats, _mock_journal

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _build_equity_curve(entries: list[dict], initial_balance: float = 10_000.0) -> list[dict]:
    """
    Build an equity curve time series from closed journal entries.

    Each point represents the equity after a trade closed.
    Drawdown is calculated as the percentage fall from the running peak.
    """
    closed = sorted(
        [
            e for e in entries
            if e.get("status") not in {"OPEN"}
            and e.get("exit_at") is not None
        ],
        key=lambda e: e.get("exit_at", ""),
    )

    if not closed:
        # Return a flat starting point so the chart renders
        return [
            {
                "date": datetime.now(timezone.utc).date().isoformat(),
                "equity": initial_balance,
                "drawdown_pct": 0.0,
            }
        ]

    equity = initial_balance
    peak = initial_balance
    curve = []

    for entry in closed:
        pnl = entry.get("pnl_usd") or 0.0
        equity += pnl
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak if peak > 0 else 0.0

        exit_dt = entry.get("exit_at", "")
        try:
            date_str = datetime.fromisoformat(
                str(exit_dt).replace("Z", "+00:00")
            ).date().isoformat()
        except Exception:
            date_str = datetime.now(timezone.utc).date().isoformat()

        curve.append({
            "date": date_str,
            "equity": round(equity, 2),
            "drawdown_pct": round(drawdown * 100, 2),
        })

    return curve


def _build_monthly_pnl(entries: list[dict]) -> dict[str, float]:
    """
    Aggregate P&L by calendar month (YYYY-MM).

    Returns a dict like {"2025-01": 450.5, "2025-02": -120.0, ...}
    for use in the monthly P&L heatmap in the journal analytics screen.
    """
    monthly: dict[str, float] = defaultdict(float)

    for entry in entries:
        if entry.get("status") in {"OPEN"}:
            continue
        exit_dt = entry.get("exit_at")
        pnl = entry.get("pnl_usd") or 0.0
        if not exit_dt:
            continue
        try:
            dt = datetime.fromisoformat(str(exit_dt).replace("Z", "+00:00"))
            month_key = dt.strftime("%Y-%m")
            monthly[month_key] += pnl
        except Exception:
            continue

    return {k: round(v, 2) for k, v in sorted(monthly.items())}


# Session windows in UTC hours (non-DST, see §6.6 of PRD)
_SESSION_WINDOWS = {
    "Asian": (0, 2),
    "London": (7, 10),
    "New York": (13, 16),
    "London Close": (15, 17),
}


def _classify_session(exit_dt_iso: Optional[str]) -> str:
    """Return the Kill Zone session name for a given UTC timestamp."""
    if not exit_dt_iso:
        return "Off-Session"
    try:
        dt = datetime.fromisoformat(str(exit_dt_iso).replace("Z", "+00:00"))
        hour = dt.hour
        for session, (start, end) in _SESSION_WINDOWS.items():
            if start <= hour < end:
                return session
        return "Off-Session"
    except Exception:
        return "Off-Session"


def _build_session_stats(entries: list[dict]) -> dict[str, dict]:
    """Build per-session performance breakdown."""
    session_data: dict[str, dict] = defaultdict(
        lambda: {"trades": 0, "wins": 0, "rr_sum": 0.0}
    )

    for entry in entries:
        if entry.get("status") in {"OPEN"}:
            continue
        session = _classify_session(entry.get("exit_at"))
        sd = session_data[session]
        sd["trades"] += 1
        r_mult = entry.get("r_multiple") or 0.0
        if r_mult > 0:
            sd["wins"] += 1
        sd["rr_sum"] += r_mult

    result = {}
    for session, sd in session_data.items():
        t = sd["trades"]
        result[session] = {
            "trades": t,
            "win_rate": round(sd["wins"] / t, 4) if t > 0 else 0.0,
            "avg_rr": round(sd["rr_sum"] / t, 3) if t > 0 else 0.0,
        }
    return result


async def _fetch_user_entries(
    user_id: str,
    db,
    pair: Optional[PairEnum] = None,
    style: Optional[TradingStyleEnum] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> list[dict]:
    """Fetch all journal entries for a user, with optional filters."""
    if db is None:
        entries = list(_mock_journal[user_id].values())
    else:
        try:
            query = (
                db.table("journal_entries")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
            )
            response = query.execute()
            entries = response.data or []
        except Exception:
            entries = list(_mock_journal[user_id].values())

    if pair:
        entries = [e for e in entries if e.get("pair") == pair.value]
    if style:
        entries = [e for e in entries if e.get("trading_style") == style.value]
    if from_date:
        entries = [e for e in entries if e.get("created_at", "") >= from_date.isoformat()]
    if to_date:
        entries = [e for e in entries if e.get("created_at", "") <= to_date.isoformat()]

    return entries


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/summary", response_model=AnalyticsSummary, summary="Performance summary")
async def analytics_summary(
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    pair: Optional[PairEnum] = Query(None),
    style: Optional[TradingStyleEnum] = Query(None),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    """
    Return a full analytics summary for the user's trade journal.

    Includes win rate, profit factor, average R:R, total P&L, max drawdown,
    and breakdowns by pair, style, and day of week.
    """
    user_id = user["sub"]
    entries = await _fetch_user_entries(user_id, db, pair, style, from_date, to_date)
    stats = _calculate_stats(entries)
    if from_date:
        stats["from_date"] = from_date
    if to_date:
        stats["to_date"] = to_date
    return stats


@router.get(
    "/equity-curve",
    response_model=list[dict],
    summary="Equity curve time series",
)
async def equity_curve(
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    initial_balance: float = Query(10_000.0, ge=100.0, le=10_000_000.0),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> list[dict]:
    """
    Return the equity curve as a time series.

    Each entry: {"date": "YYYY-MM-DD", "equity": float, "drawdown_pct": float}.
    Prominently displayed on the dashboard to help users see long-term performance
    during drawdown periods (retention mechanism per §19.3).
    """
    user_id = user["sub"]
    entries = await _fetch_user_entries(user_id, db, from_date=from_date, to_date=to_date)
    return _build_equity_curve(entries, initial_balance=initial_balance)


@router.get("/monthly-pnl", response_model=dict, summary="Monthly P&L heatmap data")
async def monthly_pnl(
    pair: Optional[PairEnum] = Query(None),
    style: Optional[TradingStyleEnum] = Query(None),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    """
    Return monthly P&L aggregated by calendar month.

    Response shape: {"2025-01": 450.5, "2025-02": -120.0, ...}
    Used to render the monthly P&L heatmap (months as columns, years as rows).
    """
    user_id = user["sub"]
    entries = await _fetch_user_entries(user_id, db, pair=pair, style=style)
    return _build_monthly_pnl(entries)


@router.get("/by-session", response_model=dict, summary="Performance by Kill Zone session")
async def by_session(
    pair: Optional[PairEnum] = Query(None),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    """
    Return win rate and average R:R broken down by trading session.

    Sessions: Asian, London, New York, London Close, Off-Session.
    Used to validate the Kill Zone weighting assumptions (§6.5 of PRD)
    and to show users which sessions they perform best in.
    """
    user_id = user["sub"]
    entries = await _fetch_user_entries(user_id, db, pair=pair)
    return _build_session_stats(entries)
