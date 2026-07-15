"""
Admin panel: /admin command, "Show Bookings" (paginated, joined view of
users + slots + bookings), and Confirm/Reject buttons on incoming receipts.
"""

import asyncpg
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import config
from database import queries
from keyboards.admin_keyboards import admin_menu_keyboard, pagination_keyboard
from keyboards.callback_data import BookingActionCallback, BookingsPageCallback

router = Router(name="admin")

PAGE_SIZE = 10


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not config.is_admin(message.from_user.id):
        return  # silently ignore - don't reveal the admin panel to regular users
    await message.answer("Admin panel:", reply_markup=admin_menu_keyboard())


@router.callback_query(F.data == "admin_show_bookings")
async def show_bookings(callback: CallbackQuery, db_pool: asyncpg.Pool) -> None:
    if not config.is_admin(callback.from_user.id):
        await callback.answer()
        return
    # Sent as a NEW message (not an edit) so the original admin panel
    # message - and its "Show Bookings" button - stays visible and can be
    # pressed again any time, instead of being overwritten.
    await _render_bookings_page(callback.message, db_pool, offset=0, as_new_message=True)
    await callback.answer()


@router.callback_query(BookingsPageCallback.filter())
async def paginate_bookings(
    callback: CallbackQuery, callback_data: BookingsPageCallback, db_pool: asyncpg.Pool
) -> None:
    if not config.is_admin(callback.from_user.id):
        await callback.answer()
        return
    # Prev/Next edit the bookings message itself, which is separate from
    # the original admin panel message.
    await _render_bookings_page(callback.message, db_pool, offset=callback_data.offset, as_new_message=False)
    await callback.answer()


async def _render_bookings_page(
    message: Message, db_pool: asyncpg.Pool, offset: int, as_new_message: bool
) -> None:
    # Fetch one extra row just to know whether a "Next" page exists.
    rows = await queries.get_all_bookings(db_pool, limit=PAGE_SIZE + 1, offset=offset)
    has_more = len(rows) > PAGE_SIZE
    rows = rows[:PAGE_SIZE]

    if not rows:
        text = "No bookings found."
        markup = None
    else:
        lines = [
            f"#{row['id']} · {row['full_name']} · {row['phone_number']}\n"
            f"   {row['slot_date'].strftime('%b %d')} at {row['slot_time'].strftime('%H:%M')} · {row['status']}"
            for row in rows
        ]
        text = "\n\n".join(lines)
        markup = pagination_keyboard(offset, PAGE_SIZE, has_more)

    if as_new_message:
        await message.answer(text, reply_markup=markup)
    else:
        await message.edit_text(text, reply_markup=markup)


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