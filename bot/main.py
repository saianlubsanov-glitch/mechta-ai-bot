import asyncio
import contextlib
import logging
import os
import secrets
import signal
import socket
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import BasicAuth, ClientError
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands
from dotenv import load_dotenv

from keep_alive import create_app, run_flask_blocking, shutdown_http_server

from bot.handlers.chat import router as chat_router
from bot.handlers.dreams import router as dreams_router
from bot.handlers.start import router as start_router
from bot.middleware.rate_limiter import RateLimiterMiddleware
from bot.services.db_service import init_db
from bot.services.scheduler_service import run_scheduler
from bot.storage.sqlite_storage import SQLiteFSMStorage

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PROXY_URL = os.getenv("PROXY_URL", "").strip()
PROXY_LOGIN = os.getenv("PROXY_LOGIN", "").strip()
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip()
_env_webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip()
WEBHOOK_SECRET = _env_webhook_secret if _env_webhook_secret else secrets.token_urlsafe(24)
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"

_AIOHTTP_TIMEOUT = 60  # seconds — AiohttpSession expects int, not ClientTimeout object


def _delete_webhook_on_shutdown() -> bool:
    """Render SIGTERM on every restart/sleep — deleting webhook makes the bot silent until set_webhook runs again."""
    v = os.getenv("DELETE_WEBHOOK_ON_SHUTDOWN", "").strip().lower()
    return v in ("1", "true", "yes", "on")


# Shared between the aiogram asyncio thread and the main-thread Flask server / signals.
LIFECYCLE: dict = {}


def configure_logging() -> None:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        logs_dir / "bot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8",
    )
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler], force=True)


async def configure_telegram_commands(bot: Bot) -> None:
    logger = logging.getLogger(__name__)
    commands = [
        BotCommand(command="menu", description="главный dashboard"),
        BotCommand(command="dreams", description="мои активные мечты"),
        BotCommand(command="new", description="создать мечту"),
        BotCommand(command="focus", description="текущий фокус"),
        BotCommand(command="progress", description="прогресс по мечте"),
        BotCommand(command="check", description="проверить истинность мечты"),
        BotCommand(command="pause", description="пауза и восстановление ресурса"),
        BotCommand(command="help", description="как работает mechta.ai"),
    ]
    delay = 3
    for attempt in range(1, 4):
        try:
            await bot.set_my_commands(commands=commands, scope=BotCommandScopeDefault())
            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            logger.info("startup commands configured")
            return
        except (TelegramNetworkError, TimeoutError, ClientError) as exc:
            logger.warning("startup commands attempt=%s failed: %s, retry in %ss", attempt, type(exc).__name__, delay)
            if attempt == 3:
                logger.warning("startup commands skipped after 3 attempts")
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
        except Exception:
            logger.exception("startup commands unexpected error, skipping")
            return


def _build_session(logger: logging.Logger) -> AiohttpSession:
    proxy_target = None
    if PROXY_URL:
        if PROXY_LOGIN:
            proxy_target = (PROXY_URL, BasicAuth(login=PROXY_LOGIN, password=PROXY_PASSWORD))
        else:
            proxy_target = PROXY_URL
        try:
            session = AiohttpSession(proxy=proxy_target, timeout=_AIOHTTP_TIMEOUT)
            logger.info("proxy enabled host=%s", urlparse(PROXY_URL).hostname or "unknown")
            return session
        except RuntimeError:
            logger.exception("proxy init failed, fallback to direct")

    session = AiohttpSession(timeout=_AIOHTTP_TIMEOUT)
    session._connector_init["family"] = socket.AF_INET
    logger.info("proxy disabled, direct connection")
    return session


def _resolve_public_base_url() -> str:
    return (WEBHOOK_URL or RENDER_EXTERNAL_URL).strip().rstrip("/")


async def _async_bot_runner(ready: threading.Event) -> None:
    """Aiogram lifecycle on a dedicated asyncio loop (background thread)."""
    logger = logging.getLogger(__name__)
    LIFECYCLE["loop"] = asyncio.get_running_loop()

    storage = SQLiteFSMStorage()
    session = _build_session(logger)
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher(storage=storage)

    dp.message.middleware(RateLimiterMiddleware())

    dp.include_router(start_router)
    dp.include_router(dreams_router)
    dp.include_router(chat_router)

    try:
        await configure_telegram_commands(bot)
    except Exception:
        logger.exception("startup commands wrapper failed")

    public_base = _resolve_public_base_url()
    if not public_base:
        raise RuntimeError(
            "Webhook base URL is missing: set WEBHOOK_URL (e.g. https://your-service.onrender.com) "
            "or deploy on Render so RENDER_EXTERNAL_URL is set."
        )
    full_webhook_url = f"{public_base}{WEBHOOK_PATH}"
    LIFECYCLE["render_public_url"] = public_base

    shutdown = asyncio.Event()
    LIFECYCLE["shutdown"] = shutdown

    scheduler_task = asyncio.create_task(run_scheduler(bot))
    LIFECYCLE["scheduler_task"] = scheduler_task
    LIFECYCLE["bot"] = bot
    LIFECYCLE["dp"] = dp
    LIFECYCLE["storage"] = storage

    logger.info(
        "webhook configured path=%s secret_enabled=%s",
        WEBHOOK_PATH,
        True,
    )
    await bot.set_webhook(
        url=full_webhook_url,
        drop_pending_updates=True,
        allowed_updates=dp.resolve_used_update_types(),
        secret_token=WEBHOOK_SECRET,
    )
    logger.info("telegram webhook registered url=%s", full_webhook_url)

    wh = await bot.get_webhook_info()
    logger.info(
        "getWebhookInfo url=%s pending_update_count=%s last_error_message=%s last_error_date=%s",
        wh.url,
        wh.pending_update_count,
        wh.last_error_message,
        wh.last_error_date,
    )

    logger.info("bot asyncio worker ready (webhook + scheduler)")
    print("BOT STARTED mode=webhook (Flask main thread)")
    ready.set()

    try:
        await shutdown.wait()
    finally:
        if _delete_webhook_on_shutdown():
            with contextlib.suppress(Exception):
                await bot.delete_webhook(drop_pending_updates=False)
            logger.info("telegram webhook removed (DELETE_WEBHOOK_ON_SHUTDOWN=true)")
        else:
            logger.info(
                "shutdown: keeping Telegram webhook (avoid silence on Render SIGTERM); "
                "set DELETE_WEBHOOK_ON_SHUTDOWN=true to remove webhook on stop"
            )
        if not scheduler_task.done():
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task
        await storage.close()
        await bot.session.close()
        logger.info("bot shut down cleanly")


def _async_thread_main(ready: threading.Event) -> None:
    try:
        asyncio.run(_async_bot_runner(ready))
    except Exception:
        logging.getLogger(__name__).exception("async bot thread crashed")
        if not ready.is_set():
            ready.set()


def run_webhook_server() -> None:
    """
    Render Web Service entry: bind PORT from the main thread (Werkzeug/Flask),
    run aiogram on a second thread with its own asyncio event loop.
    """
    configure_logging()
    logger = logging.getLogger(__name__)

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set")
        sys.exit(1)

    init_db()
    logger.info("database initialized")

    ready = threading.Event()
    worker = threading.Thread(target=_async_thread_main, args=(ready,), name="aiogram-async", daemon=False)
    LIFECYCLE["_async_thread"] = worker
    worker.start()

    if not ready.wait(timeout=120):
        logger.error("bot did not become ready within 120s")
        sys.exit(1)

    bot = LIFECYCLE.get("bot")
    dp = LIFECYCLE.get("dp")
    loop = LIFECYCLE.get("loop")
    if bot is None or dp is None or loop is None:
        logger.error("incomplete bot startup (missing bot/dp/loop)")
        sys.exit(1)

    app = create_app(
        bot,
        dp,
        loop,
        WEBHOOK_PATH,
        LIFECYCLE.get("render_public_url") or "",
        WEBHOOK_SECRET,
    )

    def _finish_shutdown_from_signal() -> None:
        """Runs off the main Flask thread so Werkzeug can exit serve_forever without deadlock."""
        worker.join(timeout=120)
        shutdown_http_server(LIFECYCLE)

    def _on_signal(signum: int, _frame: object | None) -> None:
        logger.info("signal %s received, graceful shutdown", signum)
        sd = LIFECYCLE.get("shutdown")
        ev_loop = LIFECYCLE.get("loop")
        if ev_loop is not None and sd is not None and ev_loop.is_running():
            ev_loop.call_soon_threadsafe(sd.set)
        threading.Thread(target=_finish_shutdown_from_signal, name="shutdown-helper", daemon=True).start()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            pass

    port = int(os.environ.get("PORT", "10000"))
    logger.info("flask main thread host=0.0.0.0 port=%s path=%s", port, WEBHOOK_PATH)
    run_flask_blocking(app, LIFECYCLE)
    worker.join(timeout=30)


if __name__ == "__main__":
    run_webhook_server()
