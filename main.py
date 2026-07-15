"""
Entry point. Run with:  python main.py

This file only WIRES things together: builds the Bot/Dispatcher, opens the
DB pool, registers each handler module's router, and starts polling. All
the actual logic lives in handlers/, keyboards/, database/.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
from database.db import close_pool, create_pool
from handlers import admin, booking, phone, payment, start
from scheduler import generate_upcoming_slots, start_scheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def register_handlers(dp: Dispatcher) -> None:
    # Order matters for the FSM flow (start -> phone -> booking -> payment)
    # so it's registered before the standalone admin handlers.
    start.register(dp)
    phone.register(dp)
    booking.register(dp)
    payment.register(dp)
    admin.register(dp)


async def main() -> None:
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    pool = await create_pool()
    # Any key stored here is auto-injected into handlers that declare a
    # matching argument name - e.g. `async def handler(message, db_pool): ...`
    dp["db_pool"] = pool
    logger.info("Database pool created.")

    register_handlers(dp)

    # Make sure today's (and the next couple of days') slots exist right
    # away - important on first run or after any downtime - then keep
    # topping them up every night.
    await generate_upcoming_slots(pool)
    scheduler = start_scheduler(pool, bot)

    try:
        logger.info("Bot starting...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await close_pool(pool)
        logger.info("Database pool closed.")


if __name__ == "__main__":
    asyncio.run(main())