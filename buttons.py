"""
"Book an Appointment" flow:
  1. show a 7-day date picker
  2. user taps a date -> show that day's open slots
  3. user taps a slot -> atomically claim it, create the booking, ask for payment
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import asyncpg
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import config
from database import queries
from keyboards.callback_data import DateCallback, SlotCallback
from keyboards.user_keyboards import dates_keyboard, slots_keyboard
from states import BookingStates

router = Router(name="booking")


def _today() -> date:
    return datetime.now(ZoneInfo(config.TIMEZONE)).date()


async def _send_dates(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Choose a date:", reply_markup=dates_keyboard(_today())
    )


async def _send_slots(callback: CallbackQuery, db_pool: asyncpg.Pool, target_date: date) -> None:
    slots = await queries.get_available_slots(db_pool, target_date)

    # Hide times that have already passed, if we're looking at today.
    now = datetime.now(ZoneInfo(config.TIMEZONE))
    if target_date == now.date():
        slots = [s for s in slots if s["slot_time"] > now.time()]

    if not slots:
        await callback.message.edit_text(
            f"Tanlangan vaqtda bosh oyin yoq {target_date.strftime('%A, %b %d')}.\n"
            "iltimos boshqa sana tanlang.",
            reply_markup=dates_keyboard(_today()),
        )
        return

    await callback.message.edit_text(
        f"Tanalagan sanada mavjud orinlar {target_date.strftime('%A, %b %d')}:",
        reply_markup=slots_keyboard(slots),
    )


@router.callback_query(F.data == "book_appointment")
async def show_date_picker(callback: CallbackQuery) -> None:
    await _send_dates(callback)
    await callback.answer()


@router.callback_query(DateCallback.filter())
async def date_chosen(
    callback: CallbackQuery, callback_data: DateCallback, db_pool: asyncpg.Pool
) -> None:
    target_date = date.fromisoformat(callback_data.date)
    await _send_slots(callback, db_pool, target_date)
    await callback.answer()


@router.callback_query(SlotCallback.filter())
async def slot_chosen(
    callback: CallbackQuery,
    callback_data: SlotCallback,
    state: FSMContext,
    db_pool: asyncpg.Pool,
) -> None:
    slot_id = callback_data.slot_id

    slot = await queries.get_slot(db_pool, slot_id)
    if not slot:
        await callback.answer("This slot no longer exists.", show_alert=True)
        await _send_dates(callback)
        return

    user = await queries.get_user_by_telegram_id(db_pool, callback.from_user.id)
    if not user or not user["phone_number"]:
        await callback.answer("Please register your phone number first with /start.", show_alert=True)
        return

    claimed = await queries.book_slot(db_pool, slot_id, user["id"])
    if not claimed:
        # Someone else grabbed it a split second earlier - re-show the
        # remaining slots for the same date.
        await callback.answer("Sorry, that slot was just taken. Pick another.", show_alert=True)
        await _send_slots(callback, db_pool, slot["slot_date"])
        return

    booking_id = await queries.create_booking(
        db_pool, user_id=user["id"], slot_id=slot_id, phone_number=user["phone_number"]
    )

    await state.set_state(BookingStates.waiting_for_receipt)
    await state.update_data(booking_id=booking_id)

    await callback.message.edit_text(
        f"Siz tanlagan vaqt {slot['slot_time'].strftime('%H:%M')} on "
        f"{slot['slot_date'].strftime('%A, %b %d')}. ✅\n\n"
        f"Tasdiqlash uchun, iltimos shu karta raqamiga {config.APPOINTMENT_PRICE} so'm tolov qiling:\n"
        f"💳 {config.BARBER_CARD_NUMBER}\n\n"
        "Keyin shu yerga chek rasmi yoki skrinshotini yuboring."
    )
    await callback.answer()


def register(dp) -> None:
    dp.include_router(router)