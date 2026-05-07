from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.services.ai_service import ai_service
from bot.services.db_service import save_message
from bot.services.dream_service import get_user_dream_by_id

router = Router()


@router.message()
async def dream_chat_handler(message: Message, state: FSMContext) -> None:
    if message.from_user is None or message.text is None:
        return

    state_data = await state.get_data()
    active_dream_id = state_data.get("active_dream_id")
    if not isinstance(active_dream_id, int):
        await message.answer(
            "Сначала выбери мечту через «📂 Мои мечты» или создай новую.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    dream = get_user_dream_by_id(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        dream_id=active_dream_id,
    )
    if dream is None:
        await state.clear()
        await message.answer(
            "Активный контекст мечты не найден. Выбери мечту заново.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    user_text = message.text.strip()
    if not user_text:
        await message.answer("Сообщение пустое. Напиши текст для продолжения.")
        return

    save_message(dream_id=active_dream_id, role="user", content=user_text)
    ai_reply = await ai_service.generate_response(
        dream_id=active_dream_id,
        dream_title=str(dream["title"]),
        user_message=user_text,
    )
    save_message(dream_id=active_dream_id, role="assistant", content=ai_reply)
    await message.answer(ai_reply)
