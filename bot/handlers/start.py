from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.services.dream_service import ensure_user
from bot.utils.telegram_safe import safe_answer

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    ensure_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )
    await state.clear()
    await safe_answer(
        message,
        "Привет! Я твой AI-коуч Mechta.\n"
        "Каждая мечта живет в отдельном контексте, и я помогаю двигаться по каждой из них отдельно.",
        reply_markup=get_main_menu_keyboard(),
        user_id=message.from_user.id,
    )
