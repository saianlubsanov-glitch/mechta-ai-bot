from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup, Message

from bot.keyboards.main_menu import get_dream_secondary_menu_keyboard, get_open_dream_keyboard
from bot.services.ai_service import ai_service
from bot.services.db_service import get_last_message
from bot.services.progress_service import get_progress_snapshot
from bot.utils.telegram_safe import safe_answer, safe_edit, safe_edit_by_id

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DashboardState:
    active_message_id: int | None = None
    active_dream_id: int | None = None
    active_screen: str = "main"
    last_render_hash: str = ""


_dashboard_states: dict[int, DashboardState] = {}
_callback_locks: dict[int, float] = {}
_mutexes: dict[int, asyncio.Lock] = {}
_DEBOUNCE_TTL_SECONDS = 1.2


def get_dashboard_state(user_id: int) -> DashboardState:
    if user_id not in _dashboard_states:
        _dashboard_states[user_id] = DashboardState()
    return _dashboard_states[user_id]


def should_ignore_double_click(user_id: int) -> bool:
    now = time.monotonic()
    last = _callback_locks.get(user_id)
    if last and now - last < _DEBOUNCE_TTL_SECONDS:
        return True
    _callback_locks[user_id] = now
    return False


def get_user_mutex(user_id: int) -> asyncio.Lock:
    if user_id not in _mutexes:
        _mutexes[user_id] = asyncio.Lock()
    return _mutexes[user_id]


def _compact(text: str | None, fallback: str) -> str:
    if not text:
        return fallback
    normalized = " ".join(text.split())
    return normalized[:160] + ("..." if len(normalized) > 160 else "")


def _status_badge(status: str) -> str:
    mapping = {"active": "🟢 Активна", "paused": "⏸ На паузе", "done": "✅ Завершена"}
    return mapping.get(status, f"⚪ {status}")


def _render_hash(text: str, markup: InlineKeyboardMarkup | None) -> str:
    serialized_markup = str(markup.model_dump()) if markup else ""
    return hashlib.sha256(f"{text}|{serialized_markup}".encode("utf-8")).hexdigest()


async def render_screen(
    screen: str,
    dream: dict[str, str | int | None],
    primary_action: str = "🎯 Следующий шаг",
) -> tuple[str, InlineKeyboardMarkup]:
    dream_id = int(dream["id"])
    if screen == "secondary":
        return "Дополнительные действия", get_dream_secondary_menu_keyboard(dream_id)
    if screen == "focus":
        return "⚡ Фокус дня\nДержи один шаг. Нажми и выполни.", get_open_dream_keyboard(dream_id, primary_action="⚡ Фокус дня")

    title = str(dream["title"])
    status = str(dream["status"])
    summary = _compact(dream.get("summary"), "Память еще формируется.")
    last_message = get_last_message(dream_id=dream_id)
    last_activity = f"{last_message['created_at']} · {str(last_message['role']).upper()}" if last_message else "Нет активности"
    next_step = await ai_service.generate_next_step(dream_id=dream_id, dream_title=title)
    snapshot = get_progress_snapshot(dream_id=dream_id, dream_title=title)
    metrics = snapshot["metrics"]
    text = (
        f"✨ {title}\n"
        f"━━━━━━━━━━━━━━\n"
        f"📌 {_status_badge(status)}\n"
        f"🕒 {last_activity}\n\n"
        f"🧠 {summary}\n\n"
        f"📈 Streak {metrics['streak_days']} · Momentum {metrics['momentum_score']}\n"
        f"🎯 {_compact(next_step, 'Один маленький шаг на сегодня')}"
    )
    return text, get_open_dream_keyboard(dream_id, primary_action=primary_action)


async def safe_edit_message(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> Message:
    edited = await safe_edit(message, text=text, reply_markup=reply_markup)
    if edited is not None:
        logger.debug("dashboard redraw: edited message_id=%s", edited.message_id)
        return edited
    sent = await safe_answer(message, text=text, reply_markup=reply_markup)
    if sent is not None:
        await safe_edit(message, edit_markup_only=True, reply_markup=None)
        return sent
    return message


async def render_dashboard(
    user_id: int,
    message: Message,
    dream: dict[str, str | int | None],
    screen: str = "dashboard",
    primary_action: str = "🎯 Следующий шаг",
) -> Message:
    text, markup = await render_screen(screen=screen, dream=dream, primary_action=primary_action)
    return await update_dashboard(
        user_id=user_id,
        message=message,
        dream_id=int(dream["id"]),
        screen=screen,
        text=text,
        reply_markup=markup,
    )


async def update_dashboard(
    user_id: int,
    message: Message,
    dream_id: int,
    screen: str,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> Message:
    state = get_dashboard_state(user_id)
    state_hash = _render_hash(text=text, markup=reply_markup)
    if state.last_render_hash == state_hash and state.active_message_id == message.message_id:
        return message

    updated = await safe_edit_message(message=message, text=text, reply_markup=reply_markup)
    state.active_message_id = updated.message_id
    state.active_dream_id = dream_id
    state.active_screen = screen
    state.last_render_hash = state_hash
    return updated


async def update_dashboard_by_id(
    *,
    bot,
    user_id: int,
    chat_id: int,
    message_id: int,
    dream_id: int,
    screen: str,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> bool:
    state = get_dashboard_state(user_id)
    state_hash = _render_hash(text=text, markup=reply_markup)
    if state.last_render_hash == state_hash and state.active_message_id == message_id:
        return True
    ok = await safe_edit_by_id(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=reply_markup,
        user_id=user_id,
    )
    if ok:
        state.active_message_id = message_id
        state.active_dream_id = dream_id
        state.active_screen = screen
        state.last_render_hash = state_hash
    return ok
