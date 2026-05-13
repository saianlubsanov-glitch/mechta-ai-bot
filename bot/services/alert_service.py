"""
alert_service.py
================
Sends critical error notifications to the admin's Telegram chat.

Setup: add ADMIN_CHAT_ID=<your_telegram_id> to .env
To find your chat ID: message @userinfobot in Telegram.

Features:
- Rate-limited: max 1 alert per error type per 5 minutes (no spam)
- Non-blocking: fire-and-forget, never raises exceptions
- Structured: includes error type, user context, and truncated traceback
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback

logger = logging.getLogger(__name__)

# {error_key: last_sent_timestamp}
_alert_cooldowns: dict[str, float] = {}
_ALERT_COOLDOWN_SECONDS = 300.0  # 5 minutes per error type
_MAX_TRACEBACK_CHARS = 800


def _should_send(error_key: str) -> bool:
    now = time.monotonic()
    last = _alert_cooldowns.get(error_key, 0.0)
    if now - last < _ALERT_COOLDOWN_SECONDS:
        return False
    _alert_cooldowns[error_key] = now
    return True


def _format_alert(
    title: str,
    error: BaseException | None,
    context: dict[str, str | int | None] | None,
) -> str:
    lines = [f"🚨 *{title}*"]
    if context:
        for k, v in context.items():
            lines.append(f"• {k}: `{v}`")
    if error:
        tb = traceback.format_exc()
        if tb and tb.strip() != "NoneType: None":
            trimmed = tb[-_MAX_TRACEBACK_CHARS:]
            lines.append(f"\n```\n{trimmed}\n```")
        else:
            lines.append(f"\n`{type(error).__name__}: {str(error)[:200]}`")
    return "\n".join(lines)


async def send_alert(
    bot,
    title: str,
    error: BaseException | None = None,
    context: dict[str, str | int | None] | None = None,
    error_key: str | None = None,
) -> None:
    """
    Send a critical alert to ADMIN_CHAT_ID.
    Safe to call from anywhere — never raises, never blocks.

    Args:
        bot: aiogram Bot instance
        title: short description like "DeepSeek timeout"
        error: the exception (optional)
        context: dict of extra info like {"user_id": 123, "action": "chat"}
        error_key: dedup key for rate limiting (defaults to title)
    """
    admin_chat_id = os.getenv("ADMIN_CHAT_ID", "").strip()
    if not admin_chat_id:
        return

    key = error_key or title
    if not _should_send(key):
        return

    text = _format_alert(title, error, context)
    try:
        await asyncio.wait_for(
            bot.send_message(
                chat_id=int(admin_chat_id),
                text=text,
                parse_mode="Markdown",
            ),
            timeout=10.0,
        )
    except Exception:  # noqa: BLE001
        # Alert sending must NEVER crash the bot
        logger.debug("alert send failed (suppressed)")


def fire_alert(
    bot,
    title: str,
    error: BaseException | None = None,
    context: dict[str, str | int | None] | None = None,
    error_key: str | None = None,
) -> None:
    """
    Non-async fire-and-forget wrapper. Use inside sync or exception handlers
    where you can't await.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(send_alert(bot, title, error, context, error_key))
    except Exception:  # noqa: BLE001
        pass
