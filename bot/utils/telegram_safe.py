from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import Message

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
# FIX: increased base delay — 0.6s was too short under network pressure; use 1.5s
_BASE_DELAY_SECONDS = 1.5


async def safe_answer(
    message: Message,
    text: str,
    *,
    user_id: int | None = None,
    **kwargs: Any,
) -> Message | None:
    uid = user_id or (message.from_user.id if message.from_user else None)
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return await message.answer(text, **kwargs)
        except TelegramNetworkError as exc:
            logger.warning(
                "tg_safe retry user_id=%s action=answer retry_count=%s exception=%s",
                uid,
                attempt,
                type(exc).__name__,
            )
            if attempt == _MAX_RETRIES:
                logger.error("tg_safe failed user_id=%s action=answer", uid)
                return None
            await asyncio.sleep(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        except TimeoutError:
            logger.warning(
                "tg_safe retry user_id=%s action=answer retry_count=%s exception=TimeoutError",
                uid,
                attempt,
            )
            if attempt == _MAX_RETRIES:
                logger.error("tg_safe failed user_id=%s action=answer", uid)
                return None
            await asyncio.sleep(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "tg_safe nonretry user_id=%s action=answer exception=%s",
                uid,
                type(exc).__name__,
            )
            return None
    return None


async def safe_send(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    user_id: int | None = None,
    **kwargs: Any,
) -> Message | None:
    uid = user_id or chat_id
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except TelegramNetworkError:
            logger.warning(
                "tg_safe retry user_id=%s action=send retry_count=%s exception=TelegramNetworkError",
                uid,
                attempt,
            )
            if attempt == _MAX_RETRIES:
                logger.error("tg_safe failed user_id=%s action=send", uid)
                return None
            await asyncio.sleep(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        except TimeoutError:
            logger.warning(
                "tg_safe retry user_id=%s action=send retry_count=%s exception=TimeoutError",
                uid,
                attempt,
            )
            if attempt == _MAX_RETRIES:
                logger.error("tg_safe failed user_id=%s action=send", uid)
                return None
            await asyncio.sleep(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "tg_safe nonretry user_id=%s action=send exception=%s",
                uid,
                type(exc).__name__,
            )
            return None
    return None


async def safe_edit(
    message: Message,
    *,
    text: str | None = None,
    reply_markup: Any = None,
    edit_markup_only: bool = False,
    user_id: int | None = None,
) -> Message | None:
    uid = user_id or (message.from_user.id if message.from_user else None)
    action = "edit_reply_markup" if edit_markup_only else "edit_text"
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            if edit_markup_only:
                await message.edit_reply_markup(reply_markup=reply_markup)
                return message
            if text is None:
                return message
            await message.edit_text(text=text, reply_markup=reply_markup)
            return message
        except TelegramBadRequest as exc:
            err = str(exc).lower()
            logger.warning(
                "tg_safe badrequest user_id=%s action=%s retry_count=%s exception=%s",
                uid,
                action,
                attempt,
                type(exc).__name__,
            )
            if "message is not modified" in err:
                return message
            if "message can't be edited" in err or "message to edit not found" in err:
                if not edit_markup_only and text is not None:
                    return await safe_answer(message, text, user_id=uid, reply_markup=reply_markup)
                return None
            if attempt == _MAX_RETRIES:
                logger.error("tg_safe failed user_id=%s action=%s", uid, action)
                return None
            await asyncio.sleep(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        except TelegramNetworkError:
            logger.warning(
                "tg_safe retry user_id=%s action=%s retry_count=%s exception=TelegramNetworkError",
                uid,
                action,
                attempt,
            )
            if attempt == _MAX_RETRIES:
                logger.error("tg_safe failed user_id=%s action=%s", uid, action)
                return None
            await asyncio.sleep(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        except TimeoutError:
            logger.warning(
                "tg_safe retry user_id=%s action=%s retry_count=%s exception=TimeoutError",
                uid,
                action,
                attempt,
            )
            if attempt == _MAX_RETRIES:
                logger.error("tg_safe failed user_id=%s action=%s", uid, action)
                return None
            await asyncio.sleep(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "tg_safe nonretry user_id=%s action=%s exception=%s",
                uid,
                action,
                type(exc).__name__,
            )
            return None
    return None


async def safe_edit_by_id(
    bot: Bot,
    chat_id: int,
    message_id: int,
    *,
    text: str,
    reply_markup: Any = None,
    user_id: int | None = None,
) -> bool:
    uid = user_id or chat_id
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
            return True
        except TelegramBadRequest as exc:
            err = str(exc).lower()
            logger.warning(
                "tg_safe badrequest user_id=%s action=edit_by_id retry_count=%s exception=%s",
                uid,
                attempt,
                type(exc).__name__,
            )
            if "message is not modified" in err:
                return True
            if "message can't be edited" in err or "message to edit not found" in err:
                return False
            if attempt == _MAX_RETRIES:
                logger.error("tg_safe failed user_id=%s action=edit_by_id", uid)
                return False
            await asyncio.sleep(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        except (TelegramNetworkError, TimeoutError):
            logger.warning(
                "tg_safe retry user_id=%s action=edit_by_id retry_count=%s",
                uid,
                attempt,
            )
            if attempt == _MAX_RETRIES:
                logger.error("tg_safe failed user_id=%s action=edit_by_id", uid)
                return False
            await asyncio.sleep(_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "tg_safe nonretry user_id=%s action=edit_by_id exception=%s",
                uid,
                type(exc).__name__,
            )
            return False
    return False
