"""
Central place for all configuration.
Every other module imports settings from here instead of reading
os.environ directly, so there is exactly one source of truth.
"""

import os
from datetime import time

from dotenv import load_dotenv

load_dotenv()  # reads the .env file sitting next to this script


def _require(name: str) -> str:
    """Fetch an env var or crash immediately with a clear message.

    Better to fail at startup than halfway through a booking."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _parse_time(value: str) -> time:
    hour, minute = map(int, value.split(":"))
    return time(hour=hour, minute=minute)


# --- Telegram ---
BOT_TOKEN: str = _require("BOT_TOKEN")

ADMIN_IDS: set[int] = {
    int(chunk.strip())
    for chunk in _require("ADMIN_IDS").split(",")
    if chunk.strip()
}

# --- PostgreSQL ---
DB_HOST: str = _require("DB_HOST")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_NAME: str = _require("DB_NAME")
DB_USER: str = _require("DB_USER")
DB_PASSWORD: str = _require("DB_PASSWORD")

# --- Business settings ---
BARBER_CARD_NUMBER: str = _require("BARBER_CARD_NUMBER")
APPOINTMENT_PRICE: int = int(os.getenv("APPOINTMENT_PRICE", "5000"))
TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Tashkent")

# --- Slot generation ---
SLOT_START_TIME: time = _parse_time(os.getenv("SLOT_START_TIME", "10:00"))
SLOT_END_TIME: time = _parse_time(os.getenv("SLOT_END_TIME", "00:00"))
SLOT_DURATION_MINUTES: int = int(os.getenv("SLOT_DURATION_MINUTES", "30"))

# --- Reliability settings ---
# How long a user has to send a payment receipt before their reserved slot
# is automatically released back to everyone else.
RECEIPT_TIMEOUT_MINUTES: int = int(os.getenv("RECEIPT_TIMEOUT_MINUTES", "15"))

# Port for the /health endpoint an external uptime monitor can ping.
HEALTHCHECK_PORT: int = int(os.getenv("HEALTHCHECK_PORT", "8080"))


def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS