import asyncio
import contextlib
import logging
import os
import socket
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import BasicAuth, ClientError, web
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import load_dotenv

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
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN[:12]}"

_POLLING_TIMEOUT = 30
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


async def _run_webhook(bot: Bot, dp: Dispatcher, logger: logging.Logger) -> None:
    full_url = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
    logger.info("setting webhook url=%s", full_url)
    await bot.set_webhook(url=full_url, drop_pending_updates=True, allowed_updates=dp.resolve_used_update_types())
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=WEBHOOK_PORT).start()
    logger.info("webhook server started port=%s", WEBHOOK_PORT)
    stop = asyncio.Event()
    try:
        await stop.wait()
    finally:
        await runner.cleanup()
        with contextlib.suppress(Exception):
            await bot.delete_webhook()


async def _run_polling(bot: Bot, dp: Dispatcher, logger: logging.Logger) -> None:
    backoff, attempt = 3, 0
    while True:
        try:
            logger.info("polling started attempt=%s", attempt + 1)
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                timeout=_POLLING_TIMEOUT,
                drop_pending_updates=(attempt == 0),
            )
            break
        except asyncio.CancelledError:
            logger.info("polling cancelled")
            raise
        except Exception as exc:
            attempt += 1
            logger.exception("polling crashed: attempt=%s exception=%s delay=%ss", attempt, type(exc).__name__, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


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

    mode = "webhook" if WEBHOOK_URL else "polling"
    logger.info("bot starting mode=%s", mode)
    print(f"BOT STARTED mode={mode}")

    scheduler_task = None
    try:
        scheduler_task = asyncio.create_task(run_scheduler(bot))
        logger.info("scheduler task started")

        if WEBHOOK_URL:
            await _run_webhook(bot=bot, dp=dp, logger=logger)
        else:
            await _run_polling(bot=bot, dp=dp, logger=logger)
    finally:
        if scheduler_task and not scheduler_task.done():
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task
        await storage.close()
        await bot.session.close()
        logger.info("bot shut down cleanly")


if __name__ == "__main__":
    asyncio.run(main())
