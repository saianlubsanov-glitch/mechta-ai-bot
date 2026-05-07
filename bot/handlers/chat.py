from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.services.ai_service import ai_service
from bot.services.db_service import (
    create_progress_log,
    get_dream_messages,
    get_identity_memory,
    save_message,
    update_dream_summary,
)
from bot.services.dream_service import get_user_dream_by_id
from bot.services.event_service import evaluate_and_store_events
from bot.services.memory_service import build_personality_context, update_behavioral_memory
from bot.services.emotion_service import build_emotional_guidance
from bot.services.progress_service import refresh_metrics
from bot.services.reflection_service import detect_identity_shift, update_identity_memory_layers
from bot.utils.telegram_safe import safe_answer

router = Router()


@router.message()
async def dream_chat_handler(message: Message, state: FSMContext) -> None:
    if message.from_user is None or message.text is None:
        return

    state_data = await state.get_data()
    active_dream_id = state_data.get("active_dream_id")
    if not isinstance(active_dream_id, int):
        await safe_answer(
            message,
            "Сначала выбери мечту через «📂 Мои мечты» или создай новую.",
            reply_markup=get_main_menu_keyboard(),
            user_id=message.from_user.id,
        )
        return

    dream = get_user_dream_by_id(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        dream_id=active_dream_id,
    )
    if dream is None:
        await state.clear()
        await safe_answer(
            message,
            "Активный контекст мечты не найден. Выбери мечту заново.",
            reply_markup=get_main_menu_keyboard(),
            user_id=message.from_user.id,
        )
        return

    user_text = message.text.strip()
    if not user_text:
        await safe_answer(message, "Сообщение пустое. Напиши текст для продолжения.", user_id=message.from_user.id)
        return

    personality_context = build_personality_context(user_id=int(dream["user_id"]))
    emotional_guidance = build_emotional_guidance(user_text)
    update_behavioral_memory(user_id=int(dream["user_id"]), user_message=user_text)

    save_message(dream_id=active_dream_id, role="user", content=user_text)
    ai_reply = await ai_service.generate_response(
        dream_id=active_dream_id,
        dream_title=str(dream["title"]),
        user_message=user_text,
        personality_context=personality_context,
        emotional_guidance=emotional_guidance,
    )
    save_message(dream_id=active_dream_id, role="assistant", content=ai_reply)
    create_progress_log(
        dream_id=active_dream_id,
        event_type="chat_interaction",
        details=user_text[:120],
    )
    refresh_metrics(dream_id=active_dream_id)
    evaluate_and_store_events(dream_id=active_dream_id)
    summary = await ai_service.generate_summary_memory(
        dream_id=active_dream_id,
        dream_title=str(dream["title"]),
    )
    update_dream_summary(dream_id=active_dream_id, summary=summary)

    detect_identity_shift(user_id=int(dream["user_id"]), dream_id=active_dream_id, text=user_text)
    recent_messages = get_dream_messages(dream_id=active_dream_id, limit=40)
    identity_memory = get_identity_memory(user_id=int(dream["user_id"]))
    compressed = await ai_service.compress_identity_memory(
        messages=recent_messages,
        existing_long_term=(
            str(identity_memory["long_term_compressed_memory"])
            if identity_memory and identity_memory["long_term_compressed_memory"]
            else None
        ),
    )
    update_identity_memory_layers(
        user_id=int(dream["user_id"]),
        short_term=summary,
        mid_term=summary,
        long_term=compressed["raw"],
        values=compressed["values"],
        fears=compressed["fears"],
        triggers=compressed["motivational_triggers"],
        evolution=compressed["personality_evolution"],
        confidence=compressed["confidence_patterns"],
        focus=compressed["focus_patterns"],
        emotional=compressed["emotional_trends"],
    )
    await safe_answer(message, ai_reply, user_id=message.from_user.id)
