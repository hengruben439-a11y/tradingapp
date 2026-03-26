"""
Economic calendar router.

Provides upcoming high-impact economic events affecting XAUUSD and GBPJPY.

Primary source: TradingEconomics API (TRADING_ECONOMICS_KEY env var).
Fallback: static mock data if API key is not set (dev mode).

All times are stored and returned as UTC. The iOS app displays in SGT (UTC+8)
by default, with user-configurable timezone in Settings.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.database import get_db
from api.models import CalendarEvent, ImpactEnum, PairEnum, TodayCalendarResponse

router = APIRouter(prefix="/calendar", tags=["calendar"])

_TE_BASE_URL = "https://api.tradingeconomics.com"

# Currencies that affect our pairs
_PAIR_CURRENCIES: dict[str, list[str]] = {
    "XAUUSD": ["USD", "XAU"],
    "GBPJPY": ["GBP", "JPY"],
}

_ALL_CURRENCIES = {"USD", "XAU", "GBP", "JPY"}


def _currency_to_pairs(currency: str) -> list[PairEnum]:
    """Map a currency code to the pairs it affects."""
    affected = []
    for pair, currencies in _PAIR_CURRENCIES.items():
        if currency in currencies:
            affected.append(PairEnum(pair))
    return affected


def _make_mock_events(base_dt: Optional[datetime] = None) -> list[dict]:
    """Generate mock calendar events for dev mode."""
    if base_dt is None:
        base_dt = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    events = [
        {
            "id": str(uuid.uuid4()),
            "title": "Non-Farm Payrolls",
            "impact": "HIGH",
            "scheduled_at": (base_dt + timedelta(hours=13, minutes=30)).isoformat(),
            "actual": None,
            "forecast": "185K",
            "previous": "177K",
            "currency": "USD",
            "pairs_affected": ["XAUUSD", "GBPJPY"],
            "description": "Monthly change in non-farm employment. Extreme impact on XAUUSD.",
        },
        {
            "id": str(uuid.uuid4()),
            "title": "BOE Interest Rate Decision",
            "impact": "HIGH",
            "scheduled_at": (base_dt + timedelta(hours=12, minutes=0)).isoformat(),
            "actual": None,
            "forecast": "4.50%",
            "previous": "4.75%",
            "currency": "GBP",
            "pairs_affected": ["GBPJPY"],
            "description": "Bank of England rate decision. Extreme impact on GBPJPY.",
        },
        {
            "id": str(uuid.uuid4()),
            "title": "US CPI (MoM)",
            "impact": "HIGH",
            "scheduled_at": (base_dt + timedelta(days=1, hours=13, minutes=30)).isoformat(),
            "actual": None,
            "forecast": "0.3%",
            "previous": "0.4%",
            "currency": "USD",
            "pairs_affected": ["XAUUSD", "GBPJPY"],
            "description": "Consumer Price Index month-over-month. Very high impact on gold.",
        },
        {
            "id": str(uuid.uuid4()),
            "title": "UK PMI (Manufacturing)",
            "impact": "MEDIUM",
            "scheduled_at": (base_dt + timedelta(hours=9, minutes=30)).isoformat(),
            "actual": None,
            "forecast": "49.8",
            "previous": "49.5",
            "currency": "GBP",
            "pairs_affected": ["GBPJPY"],
            "description": "Purchasing Managers Index for UK manufacturing sector.",
        },
        {
            "id": str(uuid.uuid4()),
            "title": "BOJ Monetary Policy Statement",
            "impact": "HIGH",
            "scheduled_at": (base_dt + timedelta(hours=3, minutes=0)).isoformat(),
            "actual": None,
            "forecast": None,
            "previous": None,
            "currency": "JPY",
            "pairs_affected": ["GBPJPY"],
            "description": "Bank of Japan policy statement. Extreme impact on JPY pairs.",
        },
    ]
    return events


async def _fetch_trading_economics(
    from_dt: datetime,
    to_dt: datetime,
    currencies: Optional[list[str]] = None,
) -> list[dict]:
    """
    Fetch events from TradingEconomics API.

    Returns empty list on any error (falls back to mock data upstream).
    """
    api_key = os.getenv("TRADING_ECONOMICS_KEY", "")
    if not api_key:
        return []

    currency_str = ",".join(currencies or list(_ALL_CURRENCIES))
    url = f"{_TE_BASE_URL}/calendar/country/{currency_str}"
    params = {
        "c": api_key,
        "d1": from_dt.strftime("%Y-%m-%d"),
        "d2": to_dt.strftime("%Y-%m-%d"),
        "importance": "1,2,3",  # 3=high, 2=medium, 1=low
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            raw_events = resp.json()
    except Exception:
        return []

    # Normalise TradingEconomics format to our CalendarEvent shape
    impact_map = {"3": "HIGH", "2": "MEDIUM", "1": "LOW"}
    normalised = []
    for ev in raw_events:
        currency = ev.get("Currency", "USD")
        importance = str(ev.get("Importance", "1"))
        normalised.append({
            "id": ev.get("CalendarId", str(uuid.uuid4())),
            "title": ev.get("Event", "Unknown Event"),
            "impact": impact_map.get(importance, "LOW"),
            "scheduled_at": ev.get("Date", from_dt.isoformat()),
            "actual": ev.get("Actual"),
            "forecast": ev.get("Forecast"),
            "previous": ev.get("Previous"),
            "currency": currency,
            "pairs_affected": [p.value for p in _currency_to_pairs(currency)],
            "description": None,
        })
    return normalised


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[CalendarEvent], summary="Get upcoming calendar events")
async def list_calendar_events(
    from_date: Optional[datetime] = Query(None, description="Start date (UTC)"),
    to_date: Optional[datetime] = Query(None, description="End date (UTC)"),
    impact: Optional[ImpactEnum] = Query(None, description="Filter by impact level"),
    pairs: Optional[str] = Query(
        None,
        description="Comma-separated pairs to filter by (e.g. 'XAUUSD,GBPJPY')",
    ),
    db=Depends(get_db),
) -> list[dict]:
    """
    Return upcoming economic calendar events.

    Fetches from TradingEconomics API when configured, otherwise returns
    mock data for development. All times are UTC.
    """
    now = datetime.now(timezone.utc)
    if from_date is None:
        from_date = now
    if to_date is None:
        to_date = now + timedelta(days=7)

    # Parse pair filter
    pair_filter: Optional[list[str]] = None
    if pairs:
        pair_filter = [p.strip().upper() for p in pairs.split(",")]

    # Try live API first
    events = await _fetch_trading_economics(from_date, to_date)

    # Fall back to mock data
    if not events:
        events = _make_mock_events(
            base_dt=from_date.replace(hour=0, minute=0, second=0, microsecond=0)
        )

    # Filter by impact
    if impact:
        events = [e for e in events if e.get("impact") == impact.value]

    # Filter by pair
    if pair_filter:
        events = [
            e for e in events
            if any(p in pair_filter for p in e.get("pairs_affected", []))
        ]

    # Filter to date range
    events = [
        e for e in events
        if from_date.isoformat() <= e.get("scheduled_at", "") <= to_date.isoformat()
    ]

    # Sort by scheduled time
    events.sort(key=lambda e: e.get("scheduled_at", ""))

    return events


@router.get("/today", response_model=TodayCalendarResponse, summary="Today's events in SGT")
async def today_calendar(db=Depends(get_db)) -> dict:
    """
    Return today's economic events grouped for the daily rundown.

    The daily rundown is pushed at 6:00 AM SGT and shows high-impact events
    for the trading day ahead. All times remain UTC in the response;
    the iOS app renders in the user's configured timezone (default SGT).
    """
    now_utc = datetime.now(timezone.utc)
    # SGT = UTC+8; compute today's date in SGT
    sgt_offset = timedelta(hours=8)
    now_sgt = now_utc + sgt_offset
    today_sgt = now_sgt.date()

    # Fetch today's events (full UTC day that covers today in SGT)
    day_start_utc = datetime(today_sgt.year, today_sgt.month, today_sgt.day,
                             tzinfo=timezone.utc) - sgt_offset
    day_end_utc = day_start_utc + timedelta(days=1)

    events = await _fetch_trading_economics(day_start_utc, day_end_utc)
    if not events:
        events = _make_mock_events(base_dt=day_start_utc)
        # Filter to today only
        events = [
            e for e in events
            if day_start_utc.isoformat() <= e.get("scheduled_at", "") < day_end_utc.isoformat()
        ]

    events.sort(key=lambda e: e.get("scheduled_at", ""))
    high_impact = [e for e in events if e.get("impact") == "HIGH"]

    # Find next upcoming high-impact event
    now_iso = now_utc.isoformat()
    upcoming_high = next(
        (e for e in high_impact if e.get("scheduled_at", "") >= now_iso), None
    )

    return {
        "date": today_sgt.isoformat(),
        "timezone": "SGT (UTC+8)",
        "events": events,
        "high_impact_count": len(high_impact),
        "next_high_impact": upcoming_high,
    }


@router.get("/next", response_model=Optional[CalendarEvent], summary="Next high-impact event")
async def next_high_impact_event(db=Depends(get_db)) -> Optional[dict]:
    """
    Return the next upcoming high-impact economic event.

    Used by the signal engine to determine news_risk flag and
    by the iOS app countdown timer (cascading alerts at 1h, 30m, 15m, 5m, 1m).
    Returns null if no high-impact events are scheduled in the next 24 hours.
    """
    now_utc = datetime.now(timezone.utc)
    look_ahead = now_utc + timedelta(hours=24)

    events = await _fetch_trading_economics(now_utc, look_ahead)
    if not events:
        events = _make_mock_events(base_dt=now_utc.replace(hour=0, minute=0, second=0, microsecond=0))

    high_impact = [
        e for e in events
        if e.get("impact") == "HIGH" and e.get("scheduled_at", "") >= now_utc.isoformat()
    ]
    high_impact.sort(key=lambda e: e.get("scheduled_at", ""))

    return high_impact[0] if high_impact else None
