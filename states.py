"""
FSM states. aiogram tracks conversation progress per-user via these states
instead of python-telegram-bot's ConversationHandler.
"""

from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_for_phone = State()


class BookingStates(StatesGroup):
    waiting_for_receipt = State()