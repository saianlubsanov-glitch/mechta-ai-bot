from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot

from bot.runtime.dispatcher import dispatch_event
from bot.runtime.scheduler import pick_due_events


async def run_event_loop(bot: Bot, poll_interval_seconds: int = 25) -> None:
    while True:
        try:
            due_items = pick_due_events(batch_size=10)
            for item in due_items:
                await dispatch_event(bot=bot, item=item)
        except Exception:  # noqa: BLE001
            await asyncio.sleep(5)
        await asyncio.sleep(poll_interval_seconds)


async def shutdown_event_loop(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
