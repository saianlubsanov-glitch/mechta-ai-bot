"""HTTP server for Render Web Service: healthcheck + Telegram webhook (Flask)."""

from __future__ import annotations

import asyncio
import logging
from threading import Thread

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from flask import Flask, request

logger = logging.getLogger(__name__)


def create_app(bot: Bot, dp: Dispatcher, main_loop: asyncio.AbstractEventLoop, webhook_path: str) -> Flask:
    app = Flask("mechta_bot")

    @app.route("/")
    def health() -> str:
        return "Bot is alive"

    @app.route(webhook_path, methods=["POST"])
    def telegram_webhook() -> tuple[str, int]:
        if not request.is_json:
            return "", 400
        data = request.get_json(silent=True)
        if data is None:
            return "", 400
        try:
            update = Update.model_validate(data)
        except Exception:
            logger.exception("invalid Telegram update JSON")
            return "", 400

        async def _process() -> None:
            await dp.feed_update(bot, update)

        fut = asyncio.run_coroutine_threadsafe(_process(), main_loop)
        try:
            fut.result(timeout=55)
        except Exception:
            logger.exception("webhook feed_update failed")
            return "", 500
        return "", 200

    return app


def _run_flask(app: Flask, port: int) -> None:
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)


def start_http_server_in_thread(app: Flask, port: int) -> Thread:
    thread = Thread(target=_run_flask, args=(app, port), daemon=True)
    thread.start()
    return thread
