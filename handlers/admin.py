"""
Admin panel: /admin command, "Show Bookings" (today's bookings, joined view
of users + slots + bookings), and Confirm/Reject buttons on incoming receipts.
"""

from datetime import date

import asyncpg
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import config
from database import queries
from keyboards.admin_keyboards import admin_menu_keyboard
from keyboards.callback_data import BookingActionCallback

router = Router(name="admin")


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not config.is_admin(message.from_user.id):
        return  # silently ignore - don't reveal the admin panel to regular users
    await message.answer("Admin panel:", reply_markup=admin_menu_keyboard())


@router.callback_query(F.data == "admin_show_bookings", F.from_user.id.in_(config.ADMIN_IDS))
async def show_todays_bookings(callback: CallbackQuery, db_pool: asyncpg.Pool) -> None:
    """Fetches and displays every booking for today. The admin-only check
    happens declaratively in the decorator above via
    F.from_user.id.in_(config.ADMIN_IDS) - a non-admin's tap simply never
    reaches this function at all."""
    bookings = await queries.get_todays_bookings(db_pool)

    if not bookings:
        text = f"📅 No bookings for today ({date.today().strftime('%A, %b %d')})."
    else:
        lines = [
            f"#{b['id']} · {b['full_name']} · {b['phone_number']}\n"
            f"   {b['slot_time'].strftime('%H:%M')} · {b['status']}"
            for b in bookings
        ]
        text = (
            f"📅 Today's bookings ({date.today().strftime('%A, %b %d')}):\n\n"
            + "\n\n".join(lines)
        )

    # Sent as a NEW message (not an edit) so the admin panel's own
    # "Show Bookings" button stays visible and can be tapped again any
    # time, instead of being overwritten.
    await callback.message.answer(text)

    # Stops the Telegram loading spinner on the tapped button.
    await callback.answer()


@router.callback_query(BookingActionCallback.filter())
async def handle_booking_action(
    callback: CallbackQuery, callback_data: BookingActionCallback, db_pool: asyncpg.Pool
) -> None:
    if not config.is_admin(callback.from_user.id):
        await callback.answer()
        return

    booking_id = callback_data.booking_id
    booking = await queries.get_booking(db_pool, booking_id)
    if not booking:
        await callback.answer("Booking not found.", show_alert=True)
        return

    if callback_data.action == "confirm":
        await queries.confirm_booking(db_pool, booking_id, callback.from_user.id)
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n✅ CONFIRMED"
        )
        await callback.bot.send_message(
            chat_id=booking["telegram_id"],
            text=(
                f"Your appointment on {booking['slot_date'].strftime('%A, %b %d')} "
                f"at {booking['slot_time'].strftime('%H:%M')} is confirmed! ✅ See you soon."
            ),
        )
    else:
        await queries.reject_booking(db_pool, booking_id)
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n❌ REJECTED"
        )
        await callback.bot.send_message(
            chat_id=booking["telegram_id"],
            text=(
                "We couldn't confirm your payment for the appointment on "
                f"{booking['slot_date'].strftime('%A, %b %d')} at {booking['slot_time'].strftime('%H:%M')}.\n"
                "The slot has been released - please send a valid receipt or book a new time."
            ),
        )

    await callback.answer()


def register(dp) -> None:
    dp.include_router(router)