import asyncio
import logging
import os
import socket
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import BasicAuth
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

from bot.handlers.chat import router as chat_router
from bot.handlers.dreams import router as dreams_router
from bot.handlers.start import router as start_router

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


async def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in environment.")

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

    dp.include_router(start_router)
    dp.include_router(dreams_router)
    dp.include_router(chat_router)

    print("BOT STARTED")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
