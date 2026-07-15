"""
Receives the payment receipt photo, marks the booking as awaiting admin
confirmation, and forwards the receipt + booking details to every admin
with Confirm/Reject buttons.
"""

import asyncpg
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
from database import queries
from keyboards.admin_keyboards import confirm_reject_keyboard
from states import BookingStates

router = Router(name="payment")


@router.message(BookingStates.waiting_for_receipt, F.photo)
async def receipt_received(message: Message, state: FSMContext, db_pool: asyncpg.Pool) -> None:
    data = await state.get_data()
    booking_id = data.get("booking_id")
    if not booking_id:
        await message.answer("Something went wrong - please start again with /start.")
        await state.clear()
        return

    file_id = message.photo[-1].file_id  # largest resolution
    saved = await queries.save_receipt(db_pool, booking_id, file_id)
    await state.clear()

    if not saved:
        # The reservation already expired (see scheduler.expire_stale_bookings_job)
        # before the receipt arrived - the slot's already been released.
        await message.answer(
            "Uzr, bu bron chek qabul qilinmagani uchun bekor qilindi "
            f"Berilgan vaqt {config.RECEIPT_TIMEOUT_MINUTES} daqiqa, va bron "
            "bekor qilindi. Iltimos boshqa vaqt tanlang /start."
        )
        return

    await message.answer(
        "Raxmat! Sizning chekingiz adminga jonatildi va tasdiqlanishi kutilyapti. "
        "Tasdiqlangandan song shu yerdan habar olasiz. 🙏"
    )

    booking = await queries.get_booking(db_pool, booking_id)
    caption = (
        "🧾 New payment receipt\n\n"
        f"Client: {booking['full_name']}\n"
        f"Phone: {booking['phone_number']}\n"
        f"Date: {booking['slot_date'].strftime('%A, %b %d')}\n"
        f"Time: {booking['slot_time'].strftime('%H:%M')}\n"
        f"Booking ID: {booking_id}"
    )
    for admin_id in config.ADMIN_IDS:
        await message.bot.send_photo(
            chat_id=admin_id,
            photo=file_id,
            caption=caption,
            reply_markup=confirm_reject_keyboard(booking_id),
        )


@router.message(BookingStates.waiting_for_receipt)
async def receipt_wrong_type(message: Message) -> None:
    """Catches anything that isn't a photo while we're waiting for one."""
    await message.answer("Please send the payment receipt as a photo.")


def register(dp) -> None:
    dp.include_router(router)