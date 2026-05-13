"""
rate_limiter.py
===============
Per-user rate limiting middleware for aiogram.

Prevents a single user from flooding the bot and burning DeepSeek API budget.
Uses a sliding-window token bucket per user, stored in memory (fast, no DB needed).

Limits (configurable via .env):
  RATE_LIMIT_MESSAGES=20       — max messages per window
  RATE_LIMIT_WINDOW_SECONDS=60 — rolling window duration

When limit is exceeded: user gets a soft warning, request is silently dropped.
Bot responds at most once per 30s to avoid spamming the warning itself.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)

_RATE_LIMIT = int(os.getenv("RATE_LIMIT_MESSAGES", "20"))
_WINDOW = float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
_WARN_COOLDOWN = 30.0  # seconds between "slow down" warnings per user


class RateLimiterMiddleware(BaseMiddleware):
    """
    Sliding-window rate limiter.
    Tracks message timestamps per user; drops messages over the limit.
    """

    def __init__(self) -> None:
        # {user_id: deque of timestamps}
        self._windows: dict[int, deque[float]] = defaultdict(deque)
        # {user_id: last_warning_timestamp}
        self._last_warned: dict[int, float] = {}

    def _is_allowed(self, user_id: int) -> bool:
        now = time.monotonic()
        window = self._windows[user_id]
        # Remove timestamps outside the rolling window
        while window and now - window[0] > _WINDOW:
            window.popleft()
        if len(window) >= _RATE_LIMIT:
            return False
        window.append(now)
        return True

    def _should_warn(self, user_id: int) -> bool:
        now = time.monotonic()
        last = self._last_warned.get(user_id, 0.0)
        if now - last < _WARN_COOLDOWN:
            return False
        self._last_warned[user_id] = now
        return True

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user = event.from_user
        if user is None:
            return await handler(event, data)

        if self._is_allowed(user.id):
            return await handler(event, data)

        logger.warning("rate limit exceeded user_id=%s", user.id)
        if self._should_warn(user.id):
            try:
                await event.answer(
                    f"⏳ Слишком много сообщений. Подожди немного — я успеваю обрабатывать до {_RATE_LIMIT} сообщений в минуту."
                )
            except Exception:  # noqa: BLE001
                pass
        return None
