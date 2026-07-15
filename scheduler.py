"""
Keeps the time_slots table topped up so it never runs dry.

Runs once immediately at startup (covers today + a couple days ahead, in
case the bot was down or this is the very first run) and then again every
night just after midnight (to add the next new day).
"""

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import asyncpg
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from database import queries

logger = logging.getLogger(__name__)

# How many days of slots to keep generated ahead of today.
DAYS_AHEAD = 7


def _today() -> date:
    """Tashkent's calendar date - NOT the server's system date, which could
    be a different day if the server itself runs in UTC or another zone."""
    return datetime.now(ZoneInfo(config.TIMEZONE)).date()


async def generate_upcoming_slots(pool: asyncpg.Pool) -> None:
    """Creates slots for today through DAYS_AHEAD days from now.
    Safe to call repeatedly - queries.generate_slots_for_date() uses
    ON CONFLICT DO NOTHING, so already-existing slots are left untouched."""
    today = _today()
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


async def expire_stale_bookings_job(pool: asyncpg.Pool, bot: Bot) -> None:
    """Releases any slot that's been sitting in pending_payment for longer
    than RECEIPT_TIMEOUT_MINUTES (i.e. the user picked a time but never
    sent a receipt), and lets the affected user know. Runs every couple of
    minutes - see start_scheduler() below."""
    expired = await queries.expire_stale_bookings(pool, minutes=config.RECEIPT_TIMEOUT_MINUTES)

    for row in expired:
        try:
            await bot.send_message(
                chat_id=row["telegram_id"],
                text=(
                    "Your reserved slot on "
                    f"{row['slot_date'].strftime('%A, %b %d')} at {row['slot_time'].strftime('%H:%M')} "
                    "was released because no payment receipt arrived in time.\n"
                    "Feel free to book again with /start."
                ),
            )
        except Exception:
            # Notification failing (e.g. user blocked the bot) shouldn't
            # stop the slot itself from being released - that already
            # happened inside queries.expire_stale_bookings().
            logger.exception("Failed to notify user %s about an expired booking", row["telegram_id"])

    if expired:
        logger.info("Expired %d stale booking(s).", len(expired))


def start_scheduler(pool: asyncpg.Pool, bot: Bot) -> AsyncIOScheduler:
    """Call once from main.py, after the DB pool exists. Schedules the
    nightly top-up job and the stale-booking cleanup job. The scheduler
    runs inside the same asyncio event loop as the bot - no separate
    process or cron needed."""
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

    scheduler.add_job(
        expire_stale_bookings_job,
        trigger="interval",
        minutes=2,
        args=[pool, bot],
        id="expire_stale_bookings",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started - daily slot generation at 00:05, "
        "stale-booking cleanup every 2 minutes."
    )
    return scheduler