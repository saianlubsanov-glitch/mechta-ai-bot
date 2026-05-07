from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from bot.services.db_service import get_dream_messages

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_PATH = BASE_DIR / "prompts" / "system_prompt.txt"


class AIService:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )
        self._model = "deepseek-chat"
        self._system_prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()

    async def generate_response(self, dream_id: int, dream_title: str, user_message: str) -> str:
        dream_messages = get_dream_messages(dream_id=dream_id, limit=20)

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "system", "content": f"Текущая мечта пользователя: {dream_title}"},
            *dream_messages,
            {"role": "user", "content": user_message},
        ]

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.7,
        )
        content = response.choices[0].message.content
        return content or "Сейчас не удалось сформировать ответ. Попробуй еще раз."


ai_service = AIService()
