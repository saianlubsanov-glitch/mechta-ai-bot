from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart

from bot.keyboards.main_menu import main_menu
from bot.services.dream_service import (
    create_dream,
    get_user_dreams
)

router = Router()

waiting_for_dream = {}


@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "🌌 Добро пожаловать в Mechta.ai\n\n"
        "Здесь каждая мечта становится отдельным путем.",
        reply_markup=main_menu
    )


@router.message(lambda message: message.text == "✨ Новая мечта")
async def new_dream(message: Message):
    waiting_for_dream[message.from_user.id] = True

    await message.answer(
        "Напиши свою новую мечту одним сообщением."
    )


@router.message(lambda message: message.from_user.id in waiting_for_dream)
async def save_dream(message: Message):
    create_dream(
        telegram_id=message.from_user.id,
        title=message.text
    )

    del waiting_for_dream[message.from_user.id]

    await message.answer(
        f"✨ Мечта сохранена:\n\n{message.text}"
    )


@router.message(lambda message: message.text == "📂 Мои мечты")
async def my_dreams(message: Message):
    dreams = get_user_dreams(message.from_user.id)

    if not dreams:
        await message.answer(
            "У тебя пока нет мечт."
        )
        return

    text = "🌌 Твои мечты:\n\n"

    for dream in dreams:
        dream_id, title, progress = dream

        text += (
            f"#{dream_id} — {title}\n"
            f"Прогресс: {progress}%\n\n"
        )

    await message.answer(text)
