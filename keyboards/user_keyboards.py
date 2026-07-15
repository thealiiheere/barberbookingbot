"""
Keyboards shown to regular (non-admin) users.
"""

from datetime import date, timedelta

import asyncpg
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards.callback_data import DateCallback, SlotCallback


def contact_request_keyboard() -> ReplyKeyboardMarkup:
    """A single button that shares the user's Telegram-verified phone number -
    more reliable than asking them to type it, and no typos."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Share my phone number", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Book an Appointment", callback_data="book_appointment")
    return builder.as_markup()


def dates_keyboard(start_date: date, days: int = 7) -> InlineKeyboardMarkup:
    """Shows `days` upcoming calendar days starting from start_date, one
    button each, two per row. Used as the first step of booking, before
    the user picks a specific time."""
    builder = InlineKeyboardBuilder()
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        label = "Today" if offset == 0 else day.strftime("%a, %b %d")
        builder.button(text=label, callback_data=DateCallback(date=day.isoformat()))
    builder.adjust(2)
    return builder.as_markup()


def slots_keyboard(
    slots: list[asyncpg.Record], back_callback_data: str = "book_appointment"
) -> InlineKeyboardMarkup:
    """slots: rows returned by queries.get_available_slots(), each with
    .id and .slot_time. Always ends with a row to go back and pick a
    different date."""
    builder = InlineKeyboardBuilder()
    for slot in slots:
        label = slot["slot_time"].strftime("%H:%M")
        builder.button(text=label, callback_data=SlotCallback(slot_id=slot["id"]))
    builder.adjust(3)  # 3 time-buttons per row
    builder.row(InlineKeyboardButton(text="🗓 Choose another date", callback_data=back_callback_data))
    return builder.as_markup()