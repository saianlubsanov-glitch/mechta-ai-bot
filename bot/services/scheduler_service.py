"""
scheduler_service.py
====================
Background asyncio task that periodically checks for due reminder_events
and delivers them to users via Telegram.

Architecture:
  - Runs as a long-lived asyncio Task started in main.py
  - Polls the DB every POLL_INTERVAL_SECONDS for due events
  - Respects per-user daily send limits and per-event max_attempts
  - Uses WAL-mode SQLite so polling doesn't block bot writes
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from bot.services import db_service
from bot.utils.telegram_safe import safe_send

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60          # How often to check for due events
MAX_EVENTS_PER_CYCLE = 10           # Process at most N events per poll cycle
MAX_DELIVERIES_PER_USER_PER_DAY = 3  # Avoid spamming users


async def run_scheduler(bot: Bot) -> None:
    """
    Long-running coroutine. Call via asyncio.create_task(run_scheduler(bot)).
    Gracefully exits on asyncio.CancelledError (e.g., bot shutdown).
    """
    logger.info("scheduler started poll_interval=%ss", POLL_INTERVAL_SECONDS)
    while True:
        try:
            await _process_due_events(bot)
        except asyncio.CancelledError:
            logger.info("scheduler cancelled, shutting down")
            return
        except Exception:  # noqa: BLE001
            logger.exception("scheduler cycle failed, will retry in %ss", POLL_INTERVAL_SECONDS)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _process_due_events(bot: Bot) -> None:
    events = db_service.get_due_pending_events(limit=MAX_EVENTS_PER_CYCLE)
    if not events:
        return

    logger.info("scheduler found %d due event(s)", len(events))

    for event in events:
        event_id = int(event["id"])
        dream_id = int(event["dream_id"])
        payload = str(event["payload"]) if event["payload"] else None

        if not payload:
            db_service.mark_event_delivered(event_id)
            continue

        # Resolve the dream and user
        dream_with_user = db_service.get_dream_by_id_with_user(dream_id)
        if dream_with_user is None:
            logger.warning("scheduler: dream not found dream_id=%s, marking delivered", dream_id)
            db_service.mark_event_delivered(event_id)
            continue

        telegram_id = int(dream_with_user["telegram_id"])
        user_id_db = int(dream_with_user["user_id"])

        # Respect per-user daily delivery cap
        delivered_today = db_service.count_user_delivered_events_today(user_id_db)
        if delivered_today >= MAX_DELIVERIES_PER_USER_PER_DAY:
            logger.debug(
                "scheduler: user_id=%s at daily delivery cap (%s), skipping event_id=%s",
                user_id_db,
                MAX_DELIVERIES_PER_USER_PER_DAY,
                event_id,
            )
            continue

        # Mark as processing to avoid double-delivery in concurrent scenarios
        db_service.mark_event_processing(event_id)

        sent = await safe_send(
            bot=bot,
            chat_id=telegram_id,
            text=payload,
            user_id=telegram_id,
        )

        if sent is not None:
            db_service.mark_event_delivered(event_id)
            logger.info(
                "scheduler: delivered event_id=%s type=%s user_id=%s",
                event_id,
                event["event_type"],
                user_id_db,
            )
        else:
            db_service.mark_event_failed(
                event_id,
                error_text="send_message returned None (network or bot error)",
                retry_in_minutes=30,
            )
            logger.warning(
                "scheduler: delivery failed event_id=%s user_id=%s, will retry in 30m",
                event_id,
                user_id_db,
            )
