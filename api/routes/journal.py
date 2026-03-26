"""
Trade journal router.

The journal auto-logs every signal that a user acts on (paper or live).
It tracks entry, management, and outcome — and generates a post-mortem
when a trade hits its stop loss.

All journal data is scoped to the authenticated user via Supabase RLS.
Dev mode uses an in-memory store keyed by user_id.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.auth import get_current_user
from api.database import get_db
from api.models import (
    AnalyticsSummary,
    JournalEntryCreate,
    JournalEntryResponse,
    JournalStatusEnum,
    JournalUpdateRequest,
    PairAnalytics,
    PairEnum,
    StyleAnalytics,
    TradingStyleEnum,
)

router = APIRouter(prefix="/journal", tags=["journal"])

# ── Dev mode in-memory store ──────────────────────────────────────────────────
# Dict[user_id, Dict[entry_id, entry_dict]]
_mock_journal: dict[str, dict[str, dict]] = defaultdict(dict)


def _generate_post_mortem(entry: dict) -> Optional[dict]:
    """
    Auto-generate a structured post-mortem for a stopped-out trade.

    In production this would cross-reference:
    - Which module scored most strongly in the signal direction
    - Economic calendar (was there a news event?)
    - HTF market structure change after entry

    For now returns a template-based post-mortem. LLM enhancement in Phase 5.
    """
    if entry.get("status") != JournalStatusEnum.SL_HIT.value:
        return None

    pair = entry.get("pair", "")
    direction = entry.get("direction", "")
    style = entry.get("trading_style", "")

    return {
        "failed_module": "order_blocks_fvg",
        "what_happened": (
            f"The Order Block on {pair} was mitigated — price swept through the zone "
            f"before reversing. The {direction} setup was invalidated."
        ),
        "lesson": (
            "This OB was invalidated by a liquidity sweep below the zone. "
            "Consider waiting for a confirmed reaction candle before entering at OB levels."
        ),
        "was_news_attributed": False,
        "news_event": None,
        "htf_conflict_at_entry": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _calculate_stats(entries: list[dict]) -> dict:
    """Calculate analytics summary from a list of journal entries."""
    closed = [
        e for e in entries
        if e.get("status") in {
            JournalStatusEnum.TP1_HIT.value,
            JournalStatusEnum.TP2_HIT.value,
            JournalStatusEnum.TP3_HIT.value,
            JournalStatusEnum.SL_HIT.value,
            JournalStatusEnum.MANUALLY_CLOSED.value,
        }
    ]

    total = len(closed)
    if total == 0:
        return {
            "total_trades": 0, "win_trades": 0, "loss_trades": 0, "be_trades": 0,
            "win_rate": 0.0, "profit_factor": None, "avg_rr": None,
            "total_pnl_usd": 0.0, "max_drawdown_pct": None,
            "sharpe_ratio": None, "sortino_ratio": None, "calmar_ratio": None,
            "by_pair": [], "by_style": [], "by_day_of_week": {},
            "from_date": None, "to_date": None,
        }

    wins = [e for e in closed if (e.get("r_multiple") or 0) > 0]
    losses = [e for e in closed if (e.get("r_multiple") or 0) < 0]
    bes = [e for e in closed if (e.get("r_multiple") or 0) == 0]

    win_rate = len(wins) / total if total > 0 else 0.0

    gross_profit = sum(e.get("pnl_usd") or 0 for e in wins)
    gross_loss = abs(sum(e.get("pnl_usd") or 0 for e in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    r_multiples = [e.get("r_multiple") or 0 for e in closed]
    avg_rr = sum(r_multiples) / len(r_multiples) if r_multiples else None

    total_pnl = sum(e.get("pnl_usd") or 0 for e in closed)

    # By pair
    pair_stats: dict[str, dict] = {}
    for entry in closed:
        p = entry.get("pair", "UNKNOWN")
        if p not in pair_stats:
            pair_stats[p] = {"total": 0, "wins": 0, "pnl": 0.0}
        pair_stats[p]["total"] += 1
        if (entry.get("r_multiple") or 0) > 0:
            pair_stats[p]["wins"] += 1
        pair_stats[p]["pnl"] += entry.get("pnl_usd") or 0

    by_pair = []
    for pair_name, ps in pair_stats.items():
        try:
            pair_enum = PairEnum(pair_name)
        except ValueError:
            continue
        by_pair.append({
            "pair": pair_enum,
            "total_trades": ps["total"],
            "win_rate": ps["wins"] / ps["total"] if ps["total"] > 0 else 0.0,
            "profit_factor": None,
            "avg_rr": None,
            "total_pnl_usd": ps["pnl"],
        })

    # By style
    style_stats: dict[str, dict] = {}
    for entry in closed:
        s = entry.get("trading_style", "UNKNOWN")
        if s not in style_stats:
            style_stats[s] = {"total": 0, "wins": 0}
        style_stats[s]["total"] += 1
        if (entry.get("r_multiple") or 0) > 0:
            style_stats[s]["wins"] += 1

    by_style = []
    for style_name, ss in style_stats.items():
        try:
            style_enum = TradingStyleEnum(style_name)
        except ValueError:
            continue
        by_style.append({
            "style": style_enum,
            "total_trades": ss["total"],
            "win_rate": ss["wins"] / ss["total"] if ss["total"] > 0 else 0.0,
            "profit_factor": None,
        })

    # By day of week
    day_trades: dict[str, list[float]] = defaultdict(list)
    for entry in closed:
        created = entry.get("created_at")
        if created:
            try:
                dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                day_name = dt.strftime("%A")
                day_trades[day_name].append(1 if (entry.get("r_multiple") or 0) > 0 else 0)
            except Exception:
                pass
    by_day = {
        day: sum(wins) / len(wins) if wins else 0.0
        for day, wins in day_trades.items()
    }

    return {
        "total_trades": total,
        "win_trades": len(wins),
        "loss_trades": len(losses),
        "be_trades": len(bes),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_rr": avg_rr,
        "total_pnl_usd": total_pnl,
        "max_drawdown_pct": None,
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "calmar_ratio": None,
        "by_pair": by_pair,
        "by_style": by_style,
        "by_day_of_week": by_day,
        "from_date": None,
        "to_date": None,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a journal entry")
async def create_journal_entry(
    body: JournalEntryCreate,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    """
    Create a new journal entry.

    Called automatically when a user confirms a trade (paper or live),
    or manually via the journal screen.
    """
    user_id = user["sub"]
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    entry = {
        **body.model_dump(mode="json"),
        "id": entry_id,
        "user_id": user_id,
        "created_at": now.isoformat(),
        "updated_at": None,
        "exit_price": None,
        "exit_at": None,
        "pnl_pips": None,
        "pnl_usd": None,
        "r_multiple": None,
        "status": JournalStatusEnum.OPEN.value,
        "post_mortem": None,
    }

    if db is None:
        _mock_journal[user_id][entry_id] = entry
    else:
        try:
            db.table("journal_entries").insert(entry).execute()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create journal entry: {exc}",
            )

    return entry


@router.get("", response_model=list[JournalEntryResponse], summary="List journal entries")
async def list_journal_entries(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pair: Optional[PairEnum] = Query(None),
    entry_status: Optional[JournalStatusEnum] = Query(None, alias="status"),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> list[dict]:
    """Return paginated journal entries for the authenticated user."""
    user_id = user["sub"]

    if db is None:
        entries = list(_mock_journal[user_id].values())
    else:
        try:
            query = (
                db.table("journal_entries")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .offset(offset)
            )
            if pair:
                query = query.eq("pair", pair.value)
            if entry_status:
                query = query.eq("status", entry_status.value)
            response = query.execute()
            entries = response.data or []
        except Exception:
            entries = list(_mock_journal[user_id].values())

    if pair:
        entries = [e for e in entries if e.get("pair") == pair.value]
    if entry_status:
        entries = [e for e in entries if e.get("status") == entry_status.value]

    return entries[offset: offset + limit]


@router.get("/stats", response_model=AnalyticsSummary, summary="Journal win/loss statistics")
async def journal_stats(
    pair: Optional[PairEnum] = Query(None),
    style: Optional[TradingStyleEnum] = Query(None),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    """Return aggregated performance statistics for the user's journal."""
    user_id = user["sub"]

    if db is None:
        entries = list(_mock_journal[user_id].values())
    else:
        try:
            query = (
                db.table("journal_entries")
                .select("*")
                .eq("user_id", user_id)
            )
            response = query.execute()
            entries = response.data or []
        except Exception:
            entries = list(_mock_journal[user_id].values())

    # Apply filters
    if pair:
        entries = [e for e in entries if e.get("pair") == pair.value]
    if style:
        entries = [e for e in entries if e.get("trading_style") == style.value]
    if from_date:
        entries = [e for e in entries if e.get("created_at", "") >= from_date.isoformat()]
    if to_date:
        entries = [e for e in entries if e.get("created_at", "") <= to_date.isoformat()]

    return _calculate_stats(entries)


@router.get("/{entry_id}", response_model=JournalEntryResponse, summary="Get journal entry detail")
async def get_journal_entry(
    entry_id: str,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    """Return a single journal entry with auto-generated post-mortem (if SL hit)."""
    user_id = user["sub"]

    if db is None:
        entry = _mock_journal[user_id].get(entry_id)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
        return entry

    try:
        response = (
            db.table("journal_entries")
            .select("*")
            .eq("id", entry_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")


@router.put("/{entry_id}", response_model=JournalEntryResponse, summary="Update journal entry")
async def update_journal_entry(
    entry_id: str,
    body: JournalUpdateRequest,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    """
    Update a journal entry with exit data, new status, or notes.

    When status is set to SL_HIT, a post-mortem is auto-generated.
    """
    user_id = user["sub"]
    update_data = {k: v for k, v in body.model_dump(mode="json").items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    if db is None:
        entry = _mock_journal[user_id].get(entry_id)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
        entry.update(update_data)
        # Auto-generate post-mortem on SL hit
        if body.status == JournalStatusEnum.SL_HIT and entry.get("post_mortem") is None:
            entry["post_mortem"] = _generate_post_mortem(entry)
        _mock_journal[user_id][entry_id] = entry
        return entry

    try:
        # Auto-generate post-mortem on SL hit
        if body.status == JournalStatusEnum.SL_HIT:
            # Fetch existing entry to build post-mortem from its data
            existing_resp = (
                db.table("journal_entries")
                .select("*")
                .eq("id", entry_id)
                .eq("user_id", user_id)
                .execute()
            )
            if existing_resp.data:
                existing = existing_resp.data[0]
                existing.update(update_data)
                if not existing.get("post_mortem"):
                    update_data["post_mortem"] = _generate_post_mortem(existing)

        response = (
            db.table("journal_entries")
            .update(update_data)
            .eq("id", entry_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update failed: {exc}",
        )


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete journal entry")
async def delete_journal_entry(
    entry_id: str,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
) -> None:
    """Delete a journal entry. Irreversible."""
    user_id = user["sub"]

    if db is None:
        if entry_id not in _mock_journal[user_id]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
        del _mock_journal[user_id][entry_id]
        return

    try:
        response = (
            db.table("journal_entries")
            .delete()
            .eq("id", entry_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Delete failed: {exc}",
        )
