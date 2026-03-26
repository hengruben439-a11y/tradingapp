"""
Daily rundown scheduler for the made. Telegram bot.

Uses APScheduler (AsyncIOScheduler) to fire a daily economic calendar summary
at 22:00 UTC (06:00 SGT) every day. This module is intentionally thin — it
wires the scheduler to the bot without owning any formatting or fetch logic.

Dependencies:
    apscheduler>=3.10.0  (add to requirements if not already present)
"""

from __future__ import annotations

import logging
from typing import Callable, Awaitable, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Daily rundown fires at 22:00 UTC = 06:00 SGT (UTC+8)
RUNDOWN_HOUR_UTC = 22
RUNDOWN_MINUTE_UTC = 0

# APScheduler job ID — used for identity / replacement
_JOB_ID = "made_daily_rundown"


class DailyRundownScheduler:
    """Manages the APScheduler job that sends the daily economic rundown.

    Usage::

        scheduler = DailyRundownScheduler()

        # Set up recurring job (called once on bot startup)
        scheduler.schedule_daily_rundown(bot_instance, fetch_calendar_events)

        # Manually fire right now (e.g. from /rundown command)
        await scheduler.send_rundown_now(bot_instance, fetch_calendar_events)

        # Clean up on shutdown
        scheduler.shutdown()

    Args:
        calendar_fn: An async callable ``() -> list[dict]`` that returns today's
            economic events in the format expected by
            ``formatters.format_daily_rundown``.
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._running = False

    # ─── Public API ───────────────────────────────────────────────────────────

    def schedule_daily_rundown(
        self,
        bot_instance: Any,
        calendar_fn: Callable[[], Awaitable[list[dict]]],
    ) -> None:
        """Register (or replace) the daily rundown job at 22:00 UTC.

        Safe to call multiple times — existing job is replaced.

        Args:
            bot_instance: The ``TradingBot`` instance. Must have a
                ``send_daily_rundown(events)`` coroutine method.
            calendar_fn: Async callable returning today's event list.
        """
        if not self._running:
            self._scheduler.start()
            self._running = True
            logger.info("APScheduler started.")

        # Remove previous job if present (idempotent re-registration)
        if self._scheduler.get_job(_JOB_ID):
            self._scheduler.remove_job(_JOB_ID)

        trigger = CronTrigger(
            hour=RUNDOWN_HOUR_UTC,
            minute=RUNDOWN_MINUTE_UTC,
            timezone="UTC",
        )

        self._scheduler.add_job(
            func=_run_daily_rundown,
            trigger=trigger,
            args=[bot_instance, calendar_fn],
            id=_JOB_ID,
            name="made. Daily Rundown",
            replace_existing=True,
            misfire_grace_time=300,  # allow up to 5 min late if process was down
        )

        logger.info(
            "Daily rundown scheduled at %02d:%02d UTC (%02d:%02d SGT).",
            RUNDOWN_HOUR_UTC,
            RUNDOWN_MINUTE_UTC,
            (RUNDOWN_HOUR_UTC + 8) % 24,
            RUNDOWN_MINUTE_UTC,
        )

    async def send_rundown_now(
        self,
        bot_instance: Any,
        calendar_fn: Callable[[], Awaitable[list[dict]]],
    ) -> None:
        """Immediately fire the daily rundown (used by the /rundown command).

        Args:
            bot_instance: The ``TradingBot`` instance.
            calendar_fn: Async callable returning today's event list.
        """
        logger.info("Manual rundown triggered.")
        await _run_daily_rundown(bot_instance, calendar_fn)

    def shutdown(self) -> None:
        """Gracefully stop the scheduler."""
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("APScheduler stopped.")

    # ─── Properties ───────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """True if the scheduler is active."""
        return self._running

    def next_run_time(self) -> str:
        """Human-readable string showing next scheduled run time."""
        job = self._scheduler.get_job(_JOB_ID)
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %H:%M UTC")
        return "Not scheduled"


# ─── Internal job function ────────────────────────────────────────────────────

async def _run_daily_rundown(
    bot_instance: Any,
    calendar_fn: Callable[[], Awaitable[list[dict]]],
) -> None:
    """Fetch calendar events and dispatch to TradingBot.send_daily_rundown.

    Errors are caught and logged so a calendar API failure never silences the
    rundown entirely — the bot will send an empty rundown instead.
    """
    try:
        events: list[dict] = await calendar_fn()
    except Exception as exc:  # noqa: BLE001
        logger.error("Calendar fetch failed for daily rundown: %s", exc, exc_info=True)
        events = []

    try:
        await bot_instance.send_daily_rundown(events)
    except Exception as exc:  # noqa: BLE001
        logger.error("send_daily_rundown failed: %s", exc, exc_info=True)
