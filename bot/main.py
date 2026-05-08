import asyncio
import logging
import os
import socket
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import BasicAuth, ClientError
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands
from dotenv import load_dotenv

from bot.handlers.chat import router as chat_router
from bot.handlers.dreams import router as dreams_router
from bot.handlers.start import router as start_router
from bot.services.db_service import init_db

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PROXY_URL = os.getenv("PROXY_URL", "").strip()
PROXY_LOGIN = os.getenv("PROXY_LOGIN", "").strip()
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "").strip()


def configure_logging() -> None:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        logs_dir / "bot.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
    )
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
    max_delay = 60
    for attempt in range(1, 4):
        try:
            await bot.set_my_commands(commands=commands, scope=BotCommandScopeDefault())
            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            logger.info("startup commands configured")
            return
        except (TelegramNetworkError, TimeoutError, ClientError) as exc:
            logger.exception(
                "telegram timeout during startup: restart attempt=%s exception_type=%s delay=%ss",
                attempt,
                type(exc).__name__,
                delay,
            )
            if attempt == 3:
                logger.warning("startup commands skipped")
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "startup command init failed with non-network error exception_type=%s",
                type(exc).__name__,
            )
            logger.warning("startup commands skipped")
            return


async def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in environment.")
    init_db()
    logger.info("database init/migrations completed")

    proxy_target: str | tuple[str, BasicAuth] | None = None
    if PROXY_URL:
        if PROXY_LOGIN:
            proxy_target = (
                PROXY_URL,
                BasicAuth(login=PROXY_LOGIN, password=PROXY_PASSWORD),
            )
        else:
            proxy_target = PROXY_URL

    if proxy_target:
        try:
            session = AiohttpSession(proxy=proxy_target)
        except RuntimeError as exc:
            logger.exception("proxy init failed, fallback to direct session: %s", exc)
            session = AiohttpSession()
            proxy_target = None
    else:
        session = AiohttpSession()
    session._connector_init["ssl"] = False
    session._connector_init["family"] = socket.AF_INET

    if proxy_target:
        parsed = urlparse(PROXY_URL)
        logger.info(
            "proxy enabled host=%s",
            parsed.hostname or "unknown",
        )
    else:
        logger.info("proxy disabled host=none")

    bot = Bot(
        token=BOT_TOKEN,
        session=session
    )
    dp = Dispatcher()
    try:
        await configure_telegram_commands(bot)
    except Exception:  # noqa: BLE001
        logger.exception("startup commands skipped due to unexpected wrapper failure")

    dp.include_router(start_router)
    dp.include_router(dreams_router)
    dp.include_router(chat_router)

    print("BOT STARTED")
    logger.info("polling started")
    backoff = 3
    max_backoff = 60
    attempt = 0
    while True:
        started_at = time.monotonic()
        try:
            await dp.start_polling(bot)
            break
        except asyncio.CancelledError:
            logger.info("polling cancelled, shutting down gracefully")
            raise
        except (TelegramNetworkError, TimeoutError, ClientError) as exc:
            attempt += 1
            uptime = time.monotonic() - started_at
            logger.exception(
                "polling crashed: restart attempt=%s exception_type=%s uptime_before_crash=%.2fs delay=%ss",
                attempt,
                type(exc).__name__,
                uptime,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
        except Exception as exc:  # noqa: BLE001
            attempt += 1
            uptime = time.monotonic() - started_at
            logger.exception(
                "polling crashed: restart attempt=%s exception_type=%s uptime_before_crash=%.2fs delay=%ss",
                attempt,
                type(exc).__name__,
                uptime,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)


if __name__ == "__main__":
    asyncio.run(main())
