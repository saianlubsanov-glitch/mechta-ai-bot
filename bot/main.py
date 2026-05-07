import asyncio
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from bot.handlers.chat import router as chat_router
from bot.handlers.dreams import router as dreams_router
from bot.handlers.start import router as start_router
from bot.services.db_service import init_db

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in environment.")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    init_db()

    dp.include_router(start_router)
    dp.include_router(dreams_router)
    dp.include_router(chat_router)

    print("Mechta.ai started...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
