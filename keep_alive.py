"""Flask HTTP for Render: healthcheck + Telegram webhook (main process binds PORT)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from typing import Any

from aiogram import Bot, Dispatcher
from flask import Flask, request

logger = logging.getLogger(__name__)


def create_app(bot: Bot, dp: Dispatcher, main_loop: asyncio.AbstractEventLoop, webhook_path: str) -> Flask:
    app = Flask("mechta_bot")

    @app.route("/")
    def health() -> str:
        return "Bot is alive"

    @app.route(webhook_path, methods=["POST"])
    def telegram_webhook() -> tuple[str, int]:
        logger.info(
            "webhook hit path=%s remote=%s content_type=%r content_length=%s",
            request.path,
            request.remote_addr,
            request.content_type,
            request.content_length,
        )

        raw = request.get_data(cache=False, as_text=False)
        preview = raw[:800] if raw else b""
        logger.debug("webhook raw body (prefix bytes len=%s): %r", len(raw or b""), preview)

        data: dict[str, Any] | None = None
        if raw:
            try:
                parsed = json.loads(raw.decode("utf-8"))
                if isinstance(parsed, dict):
                    data = parsed
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                logger.warning("webhook JSON decode failed: %s", exc)

        if data is None:
            data = request.get_json(force=True, silent=True)
            if not isinstance(data, dict):
                data = None

        if data is None:
            logger.warning("webhook rejected: no JSON object")
            return "", 400

        uid = data.get("update_id")
        keys = list(data.keys())
        logger.info("webhook parsed update_id=%s top_level_keys=%s", uid, keys)
        msg = data.get("message") if isinstance(data.get("message"), dict) else None
        if msg is None:
            msg = data.get("edited_message") if isinstance(data.get("edited_message"), dict) else None
        if msg is not None:
            chat = msg.get("chat") if isinstance(msg.get("chat"), dict) else {}
            logger.info(
                "webhook message preview chat_id=%s text=%r",
                chat.get("id"),
                (msg.get("text") or "")[:200],
            )

        async def _process() -> Any:
            logger.info("feed_raw_update begin update_id=%s bot_id=%s", uid, bot.id)
            try:
                result = await dp.feed_raw_update(bot, data)
                logger.info(
                    "feed_raw_update done update_id=%s result_type=%s",
                    uid,
                    type(result).__name__,
                )
                return result
            except Exception:
                logger.exception("feed_raw_update failed update_id=%s", uid)
                raise

        fut = asyncio.run_coroutine_threadsafe(_process(), main_loop)
        try:
            fut.result(timeout=55)
        except Exception:
            logger.exception("webhook worker future failed update_id=%s", uid)
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
