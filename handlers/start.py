"""
/start - creates the user if new, then routes them to phone registration
(if needed) or straight to the main menu. Admins get the admin panel instead.
"""

import asyncpg
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
from database import queries
from keyboards.admin_keyboards import admin_menu_keyboard
from keyboards.user_keyboards import contact_request_keyboard, main_menu_keyboard
from states import RegistrationStates

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db_pool: asyncpg.Pool) -> None:
    user = await queries.create_user(
        db_pool,
        telegram_id=message.from_user.id,
        full_name=message.from_user.full_name,
    )

    if config.is_admin(message.from_user.id):
        await message.answer(
            "Welcome, admin. Use the panel below.",
            reply_markup=admin_menu_keyboard(),
        )
        return

    if not user["phone_number"]:
        await state.set_state(RegistrationStates.waiting_for_phone)
        await message.answer(
            "Welcome to the barber shop bot! 💈\n\n"
            "Before we continue, please share your phone number.",
            reply_markup=contact_request_keyboard(),
        )
        return

    await message.answer(
        "Welcome back! What would you like to do?",
        reply_markup=main_menu_keyboard(),
    )


def register(dp) -> None:
    dp.include_router(router)