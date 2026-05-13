from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from copy import deepcopy
from dataclasses import dataclass

from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.keyboards.main_menu import get_dream_secondary_menu_keyboard, get_open_dream_keyboard
from bot.services.ai_service import ai_service
from bot.services.db_service import get_last_message
from bot.services.progress_service import get_progress_snapshot
from bot.utils.telegram_safe import safe_answer, safe_edit, safe_edit_by_id

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DashboardState:
    dashboard_message_id: int | None = None
    dashboard_chat_id: int | None = None
    dashboard_screen: str = "main"
    dashboard_version: int = 0
    dashboard_updated_at: float = 0.0
    active_dream_id: int | None = None
    last_render_hash: str = ""


_dashboard_states: dict[int, DashboardState] = {}
_callback_locks: dict[int, float] = {}
_mutexes: dict[int, asyncio.Lock] = {}
_DEBOUNCE_TTL_SECONDS = 1.2
_MAX_TRACKED_USERS = 5000  # Limit memory growth
_LOCK_CLEANUP_TTL = 3600.0  # Remove locks older than 1 hour
# FIX: cooldown for force_new_message to break the retry loop
# when safe_answer fails and state never updates
_force_new_cooldowns: dict[int, float] = {}
_FORCE_NEW_COOLDOWN_SECONDS = 15.0


def get_dashboard_state(user_id: int) -> DashboardState:
    if user_id not in _dashboard_states:
        _dashboard_states[user_id] = DashboardState()
    return _dashboard_states[user_id]


def _cleanup_stale_locks() -> None:
    """Remove stale callback locks older than TTL to prevent memory leaks."""
    if len(_callback_locks) < _MAX_TRACKED_USERS:
        return
    now = time.monotonic()
    stale_keys = [uid for uid, ts in _callback_locks.items() if now - ts > _LOCK_CLEANUP_TTL]
    for key in stale_keys:
        _callback_locks.pop(key, None)
        _mutexes.pop(key, None)
    logger.debug("cleaned up %d stale callback locks", len(stale_keys))


def _extract_callback_version(callback_data: str | None) -> int | None:
    if not callback_data or "|v=" not in callback_data:
        return None
    tail = callback_data.rsplit("|v=", maxsplit=1)[-1]
    return int(tail) if tail.isdigit() else None


def _inject_callback_version(markup: InlineKeyboardMarkup | None, version: int) -> InlineKeyboardMarkup | None:
    if markup is None:
        return None
    cloned = deepcopy(markup)
    for row in cloned.inline_keyboard:
        for button in row:
            if button.callback_data:
                base = button.callback_data.split("|v=", maxsplit=1)[0]
                button.callback_data = f"{base}|v={version}"
    return cloned


def should_ignore_double_click(user_id: int) -> bool:
    now = time.monotonic()
    last = _callback_locks.get(user_id)
    if last and now - last < _DEBOUNCE_TTL_SECONDS:
        return True
    _callback_locks[user_id] = now
    _cleanup_stale_locks()
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
    dream_id = int(dream.get("id", 0))
    if screen == "secondary":
        return "Дополнительные действия", get_dream_secondary_menu_keyboard(dream_id)
    if screen == "focus":
        return "⚡ Фокус дня\nДержи один шаг. Нажми и выполни.", get_open_dream_keyboard(dream_id, primary_action="⚡ Фокус дня")

    title = str(dream.get("title", "Мечта"))
    status = str(dream.get("status", "active"))
    summary = _compact(dream.get("summary"), "Память еще формируется.")
    last_message = get_last_message(dream_id=dream_id)

    # FIX: show "where you left off" — last coach message as context
    last_coach_line = ""
    if last_message and last_message.get("role") == "assistant":
        last_coach_line = "💬 " + _compact(last_message.get("content"), "")
    elif last_message:
        # fetch actual last assistant reply from history
        from bot.services.db_service import get_dream_messages as _get_msgs
        for m in reversed(_get_msgs(dream_id=dream_id, limit=10)):
            if m.get("role") == "assistant":
                last_coach_line = "💬 " + _compact(m.get("content"), "")
                break

    last_activity = f"{last_message['created_at']}" if last_message else "Нет активности"
    next_step = await ai_service.generate_next_step(dream_id=dream_id, dream_title=title)
    snapshot = get_progress_snapshot(dream_id=dream_id, dream_title=title)
    metrics = snapshot["metrics"]

    parts = [
        f"✨ {title}",
        f"━━━━━━━━━━━━━━",
        f"📌 {_status_badge(status)}  ·  🕒 {last_activity}",
        "",
    ]
    if last_coach_line:
        parts += [last_coach_line, ""]
    else:
        parts += [f"🧠 {summary}", ""]
    parts += [
        f"📈 Streak {metrics['streak_days']} · Momentum {metrics['momentum_score']}",
        f"🎯 {_compact(next_step, 'Один маленький шаг на сегодня')}",
    ]
    text = "\n".join(parts)
    return text, get_open_dream_keyboard(dream_id, primary_action=primary_action)


async def _safe_callback_answer(callback: CallbackQuery, text: str, show_alert: bool = True) -> None:
    """
    FIX: Wrap callback.answer() in try/except to prevent TelegramNetworkError
    from propagating when the network is unstable. Callback will expire
    naturally regardless — this is best-effort only.
    """
    try:
        await callback.answer(text, show_alert=show_alert)
    except (TelegramNetworkError, TelegramBadRequest, TimeoutError) as exc:
        logger.debug(
            "callback.answer failed (ignored) user_id=%s exception=%s",
            callback.from_user.id if callback.from_user else "?",
            type(exc).__name__,
        )


async def validate_dashboard_callback(callback: CallbackQuery) -> bool:
    """
    FIX: Instead of hard-rejecting on version mismatch (which causes Экран устарел
    spam after every bot restart), we now silently adopt the incoming message as the
    new dashboard anchor when state is fresh (version==0 after restart).
    """
    if callback.from_user is None or callback.message is None:
        await _safe_callback_answer(callback, "Открой меню заново — /menu")
        logger.warning("callback rejected: missing user/message")
        return False

    state = get_dashboard_state(callback.from_user.id)
    user_id = callback.from_user.id
    msg_id = callback.message.message_id
    chat_id = callback.message.chat.id

    # FIX: state is fresh after restart - adopt incoming message silently
    if state.dashboard_version == 0 or state.dashboard_message_id is None:
        state.dashboard_message_id = msg_id
        state.dashboard_chat_id = chat_id
        state.dashboard_version = 1
        logger.info("dashboard state adopted after restart user_id=%s message_id=%s", user_id, msg_id)
        return True

    # Old message (user scrolled up and clicked) - dismiss spinner silently
    if msg_id != state.dashboard_message_id or chat_id != state.dashboard_chat_id:
        await _safe_callback_answer(callback, "", show_alert=False)
        logger.info("callback on stale message ignored user_id=%s", user_id)
        return False

    callback_version = _extract_callback_version(callback.data)

    # FIX: version mismatch after restart - adopt and continue, handler re-renders
    if callback_version is None or callback_version != state.dashboard_version:
        logger.info("callback version mismatch user_id=%s expected=%s got=%s adopting", user_id, state.dashboard_version, callback_version)
        state.dashboard_version = max(state.dashboard_version, callback_version or 1)
        return True

    return True



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
        dream_id=int(dream.get("id", 0)),
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
    if (
        state.last_render_hash == state_hash
        and state.dashboard_message_id == message.message_id
        and state.dashboard_chat_id == message.chat.id
    ):
        return message

    state.dashboard_version += 1
    stamped_markup = _inject_callback_version(reply_markup, state.dashboard_version)
    updated = await safe_edit_message(message=message, text=text, reply_markup=stamped_markup)
    state.dashboard_message_id = updated.message_id
    state.dashboard_chat_id = updated.chat.id
    state.active_dream_id = dream_id
    state.dashboard_screen = screen
    state.dashboard_updated_at = time.time()
    state.last_render_hash = state_hash
    logger.info(
        "dashboard update user_id=%s chat_id=%s message_id=%s screen=%s version=%s",
        user_id,
        updated.chat.id,
        updated.message_id,
        screen,
        state.dashboard_version,
    )
    return updated


async def open_dashboard_screen(
    *,
    user_id: int,
    message: Message,
    dream_id: int,
    screen: str,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
    force_new_message: bool = False,
) -> Message | None:
    state = get_dashboard_state(user_id)

    # FIX: if we already have a tracked message, try to EDIT it first even when
    # force_new_message=True. Only actually create a new message if editing fails.
    # This breaks the loop where safe_answer fails, state never updates, and
    # the bot keeps spamming "force new message" on every /menu command.
    if state.dashboard_message_id and state.dashboard_chat_id:
        edited = await update_dashboard_by_id(
            bot=message.bot,
            user_id=user_id,
            chat_id=state.dashboard_chat_id,
            message_id=state.dashboard_message_id,
            dream_id=dream_id,
            screen=screen,
            text=text,
            reply_markup=reply_markup,
        )
        if edited:
            return message

        # Edit failed (message deleted / too old). Apply cooldown before sending new.
        now = time.monotonic()
        last_force = _force_new_cooldowns.get(user_id, 0.0)
        if now - last_force < _FORCE_NEW_COOLDOWN_SECONDS:
            logger.debug(
                "dashboard force_new suppressed by cooldown user_id=%s last=%.1fs ago",
                user_id, now - last_force,
            )
            return None
        _force_new_cooldowns[user_id] = now
        logger.info(
            "dashboard force new message user_id=%s previous_message_id=%s",
            user_id,
            state.dashboard_message_id,
        )

    # FIX: reset version to 1 when creating a new message
    # Prevents version number from growing unboundedly (26→27→28→29...)
    state.dashboard_version = 1
    stamped_markup = _inject_callback_version(reply_markup, state.dashboard_version)
    sent = await safe_answer(message, text=text, reply_markup=stamped_markup, user_id=user_id)
    if sent is None:
        # FIX: even on failure, record the attempt so we don't spin endlessly
        _force_new_cooldowns[user_id] = time.monotonic()
        logger.warning("dashboard render failed user_id=%s", user_id)
        return None
    state.dashboard_message_id = sent.message_id
    state.dashboard_chat_id = sent.chat.id
    state.active_dream_id = dream_id
    state.dashboard_screen = screen
    state.dashboard_updated_at = time.time()
    state.last_render_hash = _render_hash(text=text, markup=reply_markup)
    logger.info(
        "dashboard render user_id=%s chat_id=%s message_id=%s screen=%s version=%s",
        user_id,
        sent.chat.id,
        sent.message_id,
        screen,
        state.dashboard_version,
    )
    return sent


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
    if state.last_render_hash == state_hash and state.dashboard_message_id == message_id:
        return True
    state.dashboard_version += 1
    stamped_markup = _inject_callback_version(reply_markup, state.dashboard_version)
    ok = await safe_edit_by_id(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=stamped_markup,
        user_id=user_id,
    )
    if ok:
        state.dashboard_message_id = message_id
        state.dashboard_chat_id = chat_id
        state.active_dream_id = dream_id
        state.dashboard_screen = screen
        state.dashboard_updated_at = time.time()
        state.last_render_hash = state_hash
        logger.info(
            "dashboard update user_id=%s chat_id=%s message_id=%s screen=%s version=%s",
            user_id,
            chat_id,
            message_id,
            screen,
            state.dashboard_version,
        )
    else:
        logger.warning(
            "dashboard edit failed user_id=%s chat_id=%s message_id=%s screen=%s",
            user_id,
            chat_id,
            message_id,
            screen,
        )
    return ok
