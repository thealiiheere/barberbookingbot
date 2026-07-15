"""
Keyboards shown to admins only.
"""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards.callback_data import BookingActionCallback, BookingsPageCallback


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Show Bookings", callback_data="admin_show_bookings")
    return builder.as_markup()


def confirm_reject_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Confirm",
        callback_data=BookingActionCallback(action="confirm", booking_id=booking_id),
    )
    builder.button(
        text="❌ Reject",
        callback_data=BookingActionCallback(action="reject", booking_id=booking_id),
    )
    builder.adjust(2)
    return builder.as_markup()


def pagination_keyboard(offset: int, page_size: int, has_more: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if offset > 0:
        builder.button(
            text="⬅️ Prev",
            callback_data=BookingsPageCallback(offset=max(0, offset - page_size)),
        )
    if has_more:
        builder.button(
            text="➡️ Next",
            callback_data=BookingsPageCallback(offset=offset + page_size),
        )
    builder.adjust(2)
    return builder.as_markup()