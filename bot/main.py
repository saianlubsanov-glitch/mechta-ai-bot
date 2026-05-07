import asyncio
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from bot.handlers.dreams import router
from bot.services.db_service import init_db

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def main():
    init_db()

    dp.include_router(router)

    print("Mechta.ai started...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
