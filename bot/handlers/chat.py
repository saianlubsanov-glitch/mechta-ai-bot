import asyncio
import contextlib
import logging

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
from bot.services.dashboard_service import get_dashboard_state, open_dashboard_screen, update_dashboard_by_id
from bot.services.progress_service import refresh_metrics
from bot.services.reflection_service import detect_identity_shift, update_identity_memory_layers
from bot.keyboards.main_menu import get_quick_access_keyboard
from bot.states.dream_states import DreamStates
from bot.utils.telegram_safe import safe_answer

router = Router()
logger = logging.getLogger(__name__)
_DEEPSEEK_TIMEOUT_SECONDS = 60.0


async def _typing_status_loop(message: Message) -> None:
    while True:
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:  # noqa: BLE001
            logger.debug("typing status send failed chat_id=%s", message.chat.id)
        await asyncio.sleep(5)


async def _run_background_memory_pipeline(
    *,
    user_id: int,
    dream_id: int,
    dream_title: str,
    user_text: str,
) -> None:
    try:
        summary = await ai_service.generate_summary_memory(
            dream_id=dream_id,
            dream_title=dream_title,
            timeout=_DEEPSEEK_TIMEOUT_SECONDS,
        )
        update_dream_summary(dream_id=dream_id, summary=summary)
        detect_identity_shift(user_id=user_id, dream_id=dream_id, text=user_text)
        recent_messages = get_dream_messages(dream_id=dream_id, limit=40)
        identity_memory = get_identity_memory(user_id=user_id)
        compressed = await ai_service.compress_identity_memory(
            messages=recent_messages,
            existing_long_term=(
                str(identity_memory["long_term_compressed_memory"])
                if identity_memory and identity_memory["long_term_compressed_memory"]
                else None
            ),
            timeout=_DEEPSEEK_TIMEOUT_SECONDS,
        )
        update_identity_memory_layers(
            user_id=user_id,
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
    except Exception:  # noqa: BLE001
        logger.exception("background memory pipeline failed user_id=%s dream_id=%s", user_id, dream_id)


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

    user_id = int(dream.get("user_id", 0))
    personality_context = build_personality_context(user_id=user_id)
    emotional_guidance = build_emotional_guidance(user_text)
    update_behavioral_memory(user_id=user_id, user_message=user_text)

    save_message(dream_id=active_dream_id, role="user", content=user_text)
    dream_title = str(dream.get("title", ""))
    pending = await safe_answer(
        message,
        "Сонастраиваюсь с полем твоих смыслов... 🧘‍♂️",
        user_id=message.from_user.id,
    )
    typing_task = asyncio.create_task(_typing_status_loop(message))
    try:
        ai_reply = await ai_service.generate_response(
            dream_id=active_dream_id,
            dream_title=dream_title,
            user_message=user_text,
            personality_context=personality_context,
            emotional_guidance=emotional_guidance,
            timeout=_DEEPSEEK_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001
        ai_reply = "Связь с полем сейчас нестабильна, но твой импульс зафиксирован. Попробуй чуть позже."
        logger.exception("generate_response failed user_id=%s dream_id=%s", message.from_user.id, active_dream_id)
    finally:
        typing_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await typing_task

    delivered = False
    if pending is not None:
        try:
            await message.bot.edit_message_text(
                chat_id=pending.chat.id,
                message_id=pending.message_id,
                text=ai_reply,
            )
            delivered = True
        except Exception:  # noqa: BLE001
            logger.exception("pending message edit failed user_id=%s", message.from_user.id)
    if not delivered:
        await safe_answer(message, ai_reply, user_id=message.from_user.id)

    save_message(dream_id=active_dream_id, role="assistant", content=ai_reply)
    create_progress_log(
        dream_id=active_dream_id,
        event_type="chat_interaction",
        details=user_text[:120],
    )
    refresh_metrics(dream_id=active_dream_id)
    evaluate_and_store_events(dream_id=active_dream_id)
    asyncio.create_task(
        _run_background_memory_pipeline(
            user_id=user_id,
            dream_id=active_dream_id,
            dream_title=dream_title,
            user_text=user_text,
        )
    )
    await state.set_state(DreamStates.waiting_action)
    dash_state = get_dashboard_state(user_id=message.from_user.id)
    if dash_state.dashboard_message_id and dash_state.dashboard_chat_id:
        ok = await update_dashboard_by_id(
            bot=message.bot,
            user_id=message.from_user.id,
            chat_id=dash_state.dashboard_chat_id,
            message_id=dash_state.dashboard_message_id,
            dream_id=active_dream_id,
            screen="waiting_action",
            text=(
                "Сейчас важно не спешить.\n"
                "Выбери один мягкий следующий шаг."
            ),
            reply_markup=get_quick_access_keyboard(active_dream_id),
        )
        if not ok:
            await open_dashboard_screen(
                user_id=message.from_user.id,
                message=message,
                dream_id=active_dream_id,
                screen="waiting_action",
                text="Сейчас важно не спешить.\nВыбери один мягкий следующий шаг.",
                reply_markup=get_quick_access_keyboard(active_dream_id),
            )
