import asyncio
import contextlib
import logging
import os
import signal
import socket
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import BasicAuth, ClientError
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands
from dotenv import load_dotenv

from keep_alive import create_app, start_http_server_in_thread

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
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN[:12]}"

_AIOHTTP_TIMEOUT = 60  # seconds — AiohttpSession expects int, not ClientTimeout object


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
    base = (WEBHOOK_URL or RENDER_EXTERNAL_URL).strip().rstrip("/")
    return base


async def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in .env")

    init_db()
    logger.info("database initialized")

    # FIX: SQLiteFSMStorage — FSM состояния переживают рестарты бота
    # Больше нет "Экран устарел" после падения
    storage = SQLiteFSMStorage()

    session = _build_session(logger)
    bot = Bot(token=BOT_TOKEN, session=session)

    # FIX: Dispatcher получает persistent storage
    dp = Dispatcher(storage=storage)

    # FIX: Rate limiter middleware — защита от флуда
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

    logger.info("bot starting mode=webhook (Flask) public_base=%s", public_base)
    print("BOT STARTED mode=webhook (Flask)")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, ValueError):
            pass

    scheduler_task = None
    try:
        scheduler_task = asyncio.create_task(run_scheduler(bot))
        logger.info("scheduler task started")

        port = int(os.environ.get("PORT", "10000"))
        flask_app = create_app(bot, dp, loop, WEBHOOK_PATH)
        start_http_server_in_thread(flask_app, port)
        logger.info("flask listening host=0.0.0.0 port=%s path=%s", port, WEBHOOK_PATH)
        await asyncio.sleep(0.5)

        await bot.set_webhook(
            url=full_webhook_url,
            drop_pending_updates=True,
            allowed_updates=dp.resolve_used_update_types(),
        )
        logger.info("telegram webhook registered url=%s", full_webhook_url)

        await stop.wait()
    except asyncio.CancelledError:
        raise
    finally:
        with contextlib.suppress(Exception):
            await bot.delete_webhook(drop_pending_updates=False)
        logger.info("telegram webhook removed")
        if scheduler_task and not scheduler_task.done():
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task
        await storage.close()
        await bot.session.close()
        logger.info("bot shut down cleanly")


if __name__ == "__main__":
    asyncio.run(main())
