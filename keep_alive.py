"""Flask HTTP for Render: healthcheck + Telegram webhook (main process binds PORT)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

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


def run_flask_blocking(app: Flask, holder: dict | None = None) -> None:
    """Listen on Render PORT in the current thread (main thread on Render)."""
    port = int(os.environ.get("PORT", "10000"))
    from werkzeug.serving import make_server

    server = make_server("0.0.0.0", port, app, threaded=True)
    if holder is not None:
        holder["_werkzeug_server"] = server
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with contextlib.suppress(Exception):
            server.server_close()


def shutdown_http_server(holder: dict) -> None:
    srv = holder.pop("_werkzeug_server", None)
    if srv is not None:
        with contextlib.suppress(Exception):
            srv.shutdown()
