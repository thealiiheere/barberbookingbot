"""
Keeps the time_slots table topped up so it never runs dry.

Runs once immediately at startup (covers today + a couple days ahead, in
case the bot was down or this is the very first run) and then again every
night just after midnight (to add the next new day).
"""

import logging
from datetime import date, timedelta

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from database import queries

logger = logging.getLogger(__name__)

# How many days of slots to keep generated ahead of today. Must cover the
# 7-day date picker in the booking flow (today + the next 6 days).
DAYS_AHEAD = 7


async def generate_upcoming_slots(pool: asyncpg.Pool) -> None:
    """Creates slots for today through DAYS_AHEAD days from now.
    Safe to call repeatedly - queries.generate_slots_for_date() uses
    ON CONFLICT DO NOTHING, so already-existing slots are left untouched."""
    today = date.today()
    for offset in range(DAYS_AHEAD + 1):
        target_date = today + timedelta(days=offset)
        await queries.generate_slots_for_date(
            pool,
            slot_date=target_date,
            start_time=config.SLOT_START_TIME,
            end_time=config.SLOT_END_TIME,
            duration_minutes=config.SLOT_DURATION_MINUTES,
        )
    logger.info(
        "Slots generated/verified for %s through %s.",
        today, today + timedelta(days=DAYS_AHEAD),
    )


def start_scheduler(pool: asyncpg.Pool) -> AsyncIOScheduler:
    """Call once from main.py, after the DB pool exists. Schedules the
    nightly top-up job. The scheduler runs inside the same asyncio event
    loop as the bot - no separate process or cron needed."""
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)

    scheduler.add_job(
        generate_upcoming_slots,
        trigger="cron",
        hour=0,
        minute=5,
        args=[pool],
        id="generate_daily_slots",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started - daily slot generation runs at 00:05.")
    return scheduler