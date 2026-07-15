"""
Typed callback_data payloads. aiogram packs/unpacks these automatically,
so handlers never manually split a string like "slot:42" themselves.
"""

from aiogram.filters.callback_data import CallbackData


class SlotCallback(CallbackData, prefix="slot"):
    slot_id: int


class DateCallback(CallbackData, prefix="booking_date"):
    date: str  # ISO format, e.g. "2026-07-14"


class BookingActionCallback(CallbackData, prefix="booking"):
    action: str  # "confirm" or "reject"
    booking_id: int


class BookingsPageCallback(CallbackData, prefix="bookings_page"):
    offset: int