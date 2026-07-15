"""
Phone number capture - accepts either the "Share my phone number" button
(preferred, Telegram-verified) or a manually typed number as a fallback.
"""

import re

import asyncpg
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from database import queries
from keyboards.user_keyboards import main_menu_keyboard
from states import RegistrationStates

router = Router(name="phone")

PHONE_REGEX = re.compile(r"^\+?\d{9,15}$")


@router.message(RegistrationStates.waiting_for_phone, F.contact)
async def phone_from_contact(message: Message, state: FSMContext, db_pool: asyncpg.Pool) -> None:
    # Make sure people can only share their OWN contact, not someone else's.
    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        await message.answer("Please share your own contact, not someone else's.")
        return

    await _save_and_continue(message, state, db_pool, message.contact.phone_number)


@router.message(RegistrationStates.waiting_for_phone, F.text)
async def phone_from_text(message: Message, state: FSMContext, db_pool: asyncpg.Pool) -> None:
    phone = message.text.strip()
    if not PHONE_REGEX.match(phone):
        await message.answer(
            "That doesn't look like a valid phone number.\n"
            "Use the button below, or type it like +998901234567."
        )
        return

    await _save_and_continue(message, state, db_pool, phone)


@router.message(RegistrationStates.waiting_for_phone)
async def phone_fallback(message: Message) -> None:
    """Catches anything that isn't text or a shared contact (stickers,
    photos, etc.) while we're waiting for the phone number."""
    await message.answer(
        "Please tap the button below to share your phone number, "
        "or type it manually (e.g. +998901234567)."
    )


async def _save_and_continue(
    message: Message, state: FSMContext, db_pool: asyncpg.Pool, phone: str
) -> None:
    await queries.save_phone(db_pool, message.from_user.id, phone)
    await state.clear()
    await message.answer("Thanks! Your number is saved. ✅", reply_markup=ReplyKeyboardRemove())
    await message.answer("What would you like to do?", reply_markup=main_menu_keyboard())


def register(dp) -> None:
    dp.include_router(router)