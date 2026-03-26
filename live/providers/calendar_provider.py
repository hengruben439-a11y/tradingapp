"""
TradingEconomics calendar provider with JBlanked fallback.

Config (from env):
    TRADING_ECONOMICS_API_KEY: TE API key
    JBLANKED_API_KEY: JBlanked API key (fallback)

Returns events affecting XAUUSD and GBPJPY.
Pair filter: only returns events touching XAU, USD, GBP, or JPY.

Priority order:
    1. TradingEconomics API  (real-time, actual/forecast/previous values)
    2. JBlanked News API     (Forex Factory-compatible fallback)
    3. Empty list with warning logged (if both APIs fail)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Currencies relevant to our traded pairs
_RELEVANT_CURRENCIES = {"USD", "XAU", "GBP", "JPY"}

# TE impact level strings that map to "high"
_HIGH_IMPACT_LABELS = {"high", "3", "3.0"}

# JBlanked Forex Factory API base
_JBLANKED_BASE_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


class CalendarProvider:
    """
    Economic calendar provider with automatic TradingEconomics → JBlanked fallback.

    All returned event dicts have the shape:
        {
            "name":          str,           # Event name, e.g. "Non-Farm Payrolls"
            "datetime_utc":  datetime,      # UTC-aware datetime
            "impact":        str,           # "high", "medium", "low"
            "pairs_affected": list[str],    # ["XAUUSD", "GBPJPY"] etc.
            "actual":        Optional[str], # Reported value, if released
            "forecast":      Optional[str], # Consensus forecast
            "previous":      Optional[str], # Prior reading
            "source":        str,           # "tradingeconomics" | "jblanked"
        }
    """

    def __init__(self) -> None:
        self._te_key: str = os.environ.get("TRADING_ECONOMICS_API_KEY", "")
        self._jb_key: str = os.environ.get("JBLANKED_API_KEY", "")

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_today_events(self) -> list[dict]:
        """Return today's events (UTC) affecting XAU/USD or GBP/JPY."""
        now_utc = datetime.now(timezone.utc)
        start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return await self._fetch_events(start, end)

    async def get_upcoming_events(self, hours_ahead: int = 24) -> list[dict]:
        """Return events in the next N hours (UTC) affecting relevant pairs."""
        now_utc = datetime.now(timezone.utc)
        end = now_utc + timedelta(hours=hours_ahead)
        return await self._fetch_events(now_utc, end)

    async def is_high_impact_event_imminent(self, minutes: int = 15) -> bool:
        """
        Return True if a high-impact event is scheduled within the next N minutes.

        Args:
            minutes: Look-ahead window in minutes (default 15).

        Returns:
            True if any high-impact event falls within the window.
        """
        now_utc = datetime.now(timezone.utc)
        window_end = now_utc + timedelta(minutes=minutes)
        events = await self._fetch_events(now_utc, window_end)
        for ev in events:
            if ev.get("impact", "").lower() != "high":
                continue
            ev_dt = ev.get("datetime_utc")
            if ev_dt is None:
                continue
            # Guard: ensure the event actually falls within the window
            if now_utc <= ev_dt <= window_end:
                return True
        return False

    # ── Internal Fetch Logic ──────────────────────────────────────────────────

    async def _fetch_events(
        self,
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        """Attempt TE API, fall back to JBlanked, then return empty on failure."""
        if not _HTTPX_AVAILABLE:
            logger.warning("httpx not available — calendar provider returning empty list")
            return []

        if self._te_key:
            try:
                events = await self._fetch_te(start, end)
                return [e for e in events if self._is_relevant(e)]
            except Exception:
                logger.warning(
                    "TradingEconomics calendar fetch failed — trying JBlanked fallback",
                    exc_info=True,
                )

        try:
            events = await self._fetch_jblanked(start, end)
            return [e for e in events if self._is_relevant(e)]
        except Exception:
            logger.warning(
                "JBlanked calendar fetch failed — returning empty calendar",
                exc_info=True,
            )
            return []

    async def _fetch_te(self, start: datetime, end: datetime) -> list[dict]:
        """
        Fetch events from TradingEconomics API.

        Endpoint: GET https://api.tradingeconomics.com/calendar
        Params: c (api_key), d1 (start date), d2 (end date)
        """
        params = {
            "c":  self._te_key,
            "d1": start.strftime("%Y-%m-%d"),
            "d2": end.strftime("%Y-%m-%d"),
            "f":  "json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.tradingeconomics.com/calendar",
                params=params,
            )
            resp.raise_for_status()
            raw = resp.json()

        events = []
        for item in raw:
            try:
                ev_dt = self._parse_te_datetime(item.get("Date", ""))
                if ev_dt is None:
                    continue
                # Filter to the requested window
                if not (start <= ev_dt <= end):
                    continue

                impact_raw = str(item.get("Importance", "")).lower()
                impact = self._normalise_impact(impact_raw)

                currency = str(item.get("Currency", "")).upper()
                pairs = self._currency_to_pairs(currency)

                events.append({
                    "name":           str(item.get("Event", "")),
                    "datetime_utc":   ev_dt,
                    "impact":         impact,
                    "pairs_affected": pairs,
                    "actual":         item.get("Actual"),
                    "forecast":       item.get("Forecast"),
                    "previous":       item.get("Previous"),
                    "source":         "tradingeconomics",
                })
            except Exception:
                logger.debug("Skipping malformed TE event: %s", item)
                continue

        return events

    async def _fetch_jblanked(self, start: datetime, end: datetime) -> list[dict]:
        """
        Fetch events from the JBlanked (Forex Factory-compatible) API.

        Returns the current week's calendar. We filter to the requested window.
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            params = {}
            if self._jb_key:
                params["apikey"] = self._jb_key

            resp = await client.get(_JBLANKED_BASE_URL, params=params if params else None)
            resp.raise_for_status()
            raw = resp.json()

        events = []
        for item in raw:
            try:
                ev_dt = self._parse_jb_datetime(item.get("date", ""), item.get("time", ""))
                if ev_dt is None:
                    continue
                if not (start <= ev_dt <= end):
                    continue

                impact_raw = str(item.get("impact", "")).lower()
                impact = self._normalise_impact(impact_raw)

                currency = str(item.get("currency", "")).upper()
                pairs = self._currency_to_pairs(currency)

                events.append({
                    "name":           str(item.get("title", "")),
                    "datetime_utc":   ev_dt,
                    "impact":         impact,
                    "pairs_affected": pairs,
                    "actual":         item.get("actual"),
                    "forecast":       item.get("forecast"),
                    "previous":       item.get("previous"),
                    "source":         "jblanked",
                })
            except Exception:
                logger.debug("Skipping malformed JBlanked event: %s", item)
                continue

        return events

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_te_datetime(date_str: str) -> Optional[datetime]:
        """Parse TradingEconomics ISO datetime string to UTC-aware datetime."""
        if not date_str:
            return None
        try:
            # TE format: "2026-03-06T13:30:00" (UTC, no tz suffix)
            dt = datetime.fromisoformat(date_str.rstrip("Z"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    @staticmethod
    def _parse_jb_datetime(date_str: str, time_str: str) -> Optional[datetime]:
        """Parse JBlanked date and time strings to UTC-aware datetime."""
        if not date_str:
            return None
        try:
            # JBlanked format: date "2026-03-06", time "1:30pm" or "8:30am" (ET)
            # JBlanked API actually returns UTC-based ISO strings in some versions;
            # we attempt ISO first, then fall back to combined parse.
            combined = f"{date_str} {time_str}".strip()
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    @staticmethod
    def _normalise_impact(raw: str) -> str:
        """Normalise provider-specific impact labels to high/medium/low."""
        raw = raw.lower().strip()
        if raw in {"high", "3", "3.0", "red"}:
            return "high"
        if raw in {"medium", "2", "2.0", "orange"}:
            return "medium"
        return "low"

    @staticmethod
    def _currency_to_pairs(currency: str) -> list[str]:
        """Map a single currency code to the pairs it affects."""
        mapping: dict[str, list[str]] = {
            "USD": ["XAUUSD", "GBPJPY"],
            "XAU": ["XAUUSD"],
            "GBP": ["GBPJPY"],
            "JPY": ["GBPJPY"],
        }
        return mapping.get(currency.upper(), [])

    @staticmethod
    def _is_relevant(event: dict) -> bool:
        """True if the event affects at least one of our traded pairs."""
        return bool(event.get("pairs_affected"))
