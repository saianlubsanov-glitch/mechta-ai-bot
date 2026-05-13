from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from bot.services.db_service import get_dream_messages

load_dotenv()

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"

_MAX_CONCURRENT_AI = 3
_ai_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _ai_semaphore  # noqa: PLW0603
    if _ai_semaphore is None:
        _ai_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_AI)
    return _ai_semaphore


_NEXT_STEP_CACHE: dict[int, tuple[str, float]] = {}
_NEXT_STEP_CACHE_TTL = 600.0


def _get_cached_next_step(dream_id: int) -> str | None:
    entry = _NEXT_STEP_CACHE.get(dream_id)
    if entry and (time.monotonic() - entry[1]) < _NEXT_STEP_CACHE_TTL:
        return entry[0]
    return None


def _set_cached_next_step(dream_id: int, value: str) -> None:
    _NEXT_STEP_CACHE[dream_id] = (value, time.monotonic())


def invalidate_next_step_cache(dream_id: int) -> None:
    _NEXT_STEP_CACHE.pop(dream_id, None)


def _load_prompt(filename: str, fallback: str) -> str:
    path = PROMPTS_DIR / filename
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning("prompt file not found: %s, using fallback", filename)
        return fallback


def _parse_identity_memory_sections(content: str) -> dict[str, str]:
    sections = {
        "values": "", "fears": "", "motivational_triggers": "",
        "personality_evolution": "", "confidence_patterns": "",
        "focus_patterns": "", "emotional_trends": "",
    }
    pattern = re.compile(
        r"(?:^|\n)\s*(?P<key>values|fears|motivational_triggers|personality_evolution"
        r"|confidence_patterns|focus_patterns|emotional_trends)\s*[:\-]\s*(?P<value>[^\n]+)",
        re.IGNORECASE,
    )
    found: dict[str, str] = {}
    for match in pattern.finditer(content):
        key = match.group("key").lower()
        value = match.group("value").strip()
        if key in sections and key not in found:
            found[key] = value[:300]

    if len(found) >= 4:
        sections.update(found)
    else:
        chunk = max(1, len(content) // len(sections))
        keys = list(sections.keys())
        for i, key in enumerate(keys):
            sections[key] = content[i * chunk: (i + 1) * chunk].strip()[:300]
    return sections


class AIService:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )
        self._model = os.getenv("AI_MODEL", "deepseek-chat")

        # FIX: каждая функция получает свой специализированный промпт
        self._system_prompt = _load_prompt("system_prompt.txt", "Ты — AI-коуч Mechta.ai.")
        self._next_step_prompt = _load_prompt("next_step_prompt.txt", "Определи один следующий шаг до 140 символов.")
        self._summary_prompt = _load_prompt("summary_prompt.txt", "Сделай краткую memory summary. 2-3 предложения, 280 символов. Без markdown.")
        self._reflection_prompt = _load_prompt("reflection_prompt.txt", "Сформируй personal reflection. Фокус на трансформации. 4-6 строк.")
        self._memory_compress_prompt = _load_prompt("memory_compress_prompt.txt", "Сожми диалог в 7 секций: values, fears, motivational_triggers, personality_evolution, confidence_patterns, focus_patterns, emotional_trends.")
        self._focus_prompt = _load_prompt("focus_prompt.txt", "Сформулируй daily focus как мягкий выполнимый шаг. До 160 символов.")
        self._diagnostic_prompt = _load_prompt("diagnostic_prompt.txt", "Коучинговый анализ: 4 строки — Consistency, Momentum, Unfinished, Focus.")

    async def generate_response(
        self,
        dream_id: int,
        dream_title: str,
        user_message: str,
        personality_context: str | None = None,
        emotional_guidance: str | None = None,
        timeout: float = 30.0,
    ) -> str:
        dream_messages = get_dream_messages(dream_id=dream_id, limit=20)
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "system", "content": f"Текущая мечта пользователя: {dream_title}"},
            {"role": "system", "content": "Ответ emotionally paced: снизь сопротивление → tiny step → поддержи identity. Без давления."},
            *([{"role": "system", "content": personality_context}] if personality_context else []),
            *([{"role": "system", "content": f"Emotional cognition: {emotional_guidance}"}] if emotional_guidance else []),
            *dream_messages,
            {"role": "user", "content": user_message},
        ]
        async with _get_semaphore():
            response = await self._client.chat.completions.create(
                model=self._model, messages=messages, temperature=0.7, timeout=timeout,
            )
        return response.choices[0].message.content or "Сейчас не удалось сформировать ответ. Попробуй еще раз."

    async def compress_identity_memory(
        self,
        messages: list[dict[str, str]],
        existing_long_term: str | None = None,
        timeout: float = 25.0,
    ) -> dict[str, str]:
        async with _get_semaphore():
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._memory_compress_prompt},
                    *([{"role": "system", "content": f"Existing long-term memory: {existing_long_term}"}] if existing_long_term else []),
                    *messages[-24:],
                ],
                temperature=0.3, timeout=timeout,
            )
        content = (response.choices[0].message.content or "").strip()
        sections = _parse_identity_memory_sections(content)
        non_empty = sum(1 for v in sections.values() if v.strip())
        if non_empty < 3:
            logger.warning("memory compress low quality: %d/7 sections filled", non_empty)
        return {"raw": content, **sections}

    async def generate_deep_reflection(
        self, dream_title: str, reflection_context: str, period: str, timeout: float = 25.0,
    ) -> str:
        async with _get_semaphore():
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._reflection_prompt},
                    {"role": "system", "content": f"Period: {period}. Dream: {dream_title}"},
                    {"role": "system", "content": reflection_context},
                ],
                temperature=0.6, timeout=timeout,
            )
        content = response.choices[0].message.content
        return (content or "").strip() or "Ты меняешься глубже, чем кажется. Отметь один внутренний сдвиг за этот период."

    async def generate_summary_memory(self, dream_id: int, dream_title: str, timeout: float = 25.0) -> str:
        dream_messages = get_dream_messages(dream_id=dream_id, limit=25)
        if not dream_messages:
            return "Мечта создана. Первый шаг пока не зафиксирован."
        async with _get_semaphore():
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._summary_prompt},
                    {"role": "system", "content": f"Название мечты: {dream_title}"},
                    *dream_messages,
                ],
                temperature=0.4, timeout=timeout,
            )
        content = response.choices[0].message.content
        return (content or "").strip() or "Контекст обновлен, краткая память пока формируется."

    async def generate_next_step(self, dream_id: int, dream_title: str, timeout: float = 20.0) -> str:
        cached = _get_cached_next_step(dream_id)
        if cached is not None:
            return cached
        dream_messages = get_dream_messages(dream_id=dream_id, limit=20)
        async with _get_semaphore():
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._next_step_prompt},
                    {"role": "system", "content": f"Название мечты: {dream_title}"},
                    *dream_messages,
                ],
                temperature=0.5, timeout=timeout,
            )
        content = (response.choices[0].message.content or "").strip() or "Определи один следующий практический шаг на сегодня."
        _set_cached_next_step(dream_id, content)
        return content

    async def generate_focus_guidance(self, dream_id: int, dream_title: str, focus_base: str, timeout: float = 20.0) -> str:
        dream_messages = get_dream_messages(dream_id=dream_id, limit=20)
        async with _get_semaphore():
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._focus_prompt},
                    {"role": "system", "content": f"Мечта: {dream_title}. Базовая задача: {focus_base}"},
                    *dream_messages,
                ],
                temperature=0.5, timeout=timeout,
            )
        content = response.choices[0].message.content
        return (content or "").strip() or focus_base

    async def generate_coaching_diagnostic(self, dream_id: int, dream_title: str, metrics_text: str, timeout: float = 20.0) -> str:
        dream_messages = get_dream_messages(dream_id=dream_id, limit=16)
        async with _get_semaphore():
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._diagnostic_prompt},
                    {"role": "system", "content": f"Мечта: {dream_title}. Метрики: {metrics_text}"},
                    *dream_messages,
                ],
                temperature=0.4, timeout=timeout,
            )
        content = response.choices[0].message.content
        return (content or "").strip() or "Consistency: формируется\nMomentum: умеренный\nUnfinished tasks: нужен приоритет\nFocus drift: держи 1 шаг в день"


ai_service = AIService()
