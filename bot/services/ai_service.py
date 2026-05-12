from __future__ import annotations

import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from bot.services.db_service import get_dream_messages

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_PATH = BASE_DIR / "prompts" / "system_prompt.txt"

# Cache for generate_next_step: {dream_id: (result, timestamp)}
_NEXT_STEP_CACHE: dict[int, tuple[str, float]] = {}
_NEXT_STEP_CACHE_TTL = 600.0  # 10 minutes


def _get_cached_next_step(dream_id: int) -> str | None:
    entry = _NEXT_STEP_CACHE.get(dream_id)
    if entry and (time.monotonic() - entry[1]) < _NEXT_STEP_CACHE_TTL:
        return entry[0]
    return None


def _set_cached_next_step(dream_id: int, value: str) -> None:
    _NEXT_STEP_CACHE[dream_id] = (value, time.monotonic())


def invalidate_next_step_cache(dream_id: int) -> None:
    """Call this after task completion or new message to force cache refresh."""
    _NEXT_STEP_CACHE.pop(dream_id, None)


def _parse_identity_memory_sections(content: str) -> dict[str, str]:
    """
    Parse AI response into 7 named sections.
    Expects lines like:  values: ...\nfears: ...\n  etc.
    Falls back to distributing the raw text evenly if parsing fails.
    """
    sections = {
        "values": "",
        "fears": "",
        "motivational_triggers": "",
        "personality_evolution": "",
        "confidence_patterns": "",
        "focus_patterns": "",
        "emotional_trends": "",
    }
    # Try to find each section by key: value pattern (case-insensitive)
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
        # Good parse — fill found sections, leave rest as empty
        sections.update(found)
    else:
        # Fallback: split raw content into equal chunks per section
        chunk = max(1, len(content) // len(sections))
        keys = list(sections.keys())
        for i, key in enumerate(keys):
            sections[key] = content[i * chunk : (i + 1) * chunk].strip()[:300]

    return sections


class AIService:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )
        self._model = os.getenv("AI_MODEL", "deepseek-chat")
        self._system_prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()

    async def generate_response(
        self,
        dream_id: int,
        dream_title: str,
        user_message: str,
        personality_context: str | None = None,
        emotional_guidance: str | None = None,
        timeout: float = 60.0,
    ) -> str:
        dream_messages = get_dream_messages(dream_id=dream_id, limit=20)

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "system", "content": f"Текущая мечта пользователя: {dream_title}"},
            {
                "role": "system",
                "content": (
                    "Ответ должен быть emotionally paced: сначала снизь внутреннее сопротивление, "
                    "затем дай tiny actionable step, затем поддержи identity пользователя. "
                    "Избегай давления и рациональной перегрузки."
                ),
            },
            *(
                [{"role": "system", "content": personality_context}]
                if personality_context
                else []
            ),
            *(
                [{"role": "system", "content": f"Emotional cognition: {emotional_guidance}"}]
                if emotional_guidance
                else []
            ),
            *dream_messages,
            {"role": "user", "content": user_message},
        ]

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.7,
            timeout=timeout,
        )
        content = response.choices[0].message.content
        return content or "Сейчас не удалось сформировать ответ. Попробуй еще раз."

    async def compress_identity_memory(
        self,
        messages: list[dict[str, str]],
        existing_long_term: str | None = None,
        timeout: float = 60.0,
    ) -> dict[str, str]:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "system",
                    "content": (
                        "Сожми диалог в behavioral memory для долгосрочного хранения. "
                        "Верни СТРОГО 7 секций в формате 'ключ: значение', каждая с новой строки. "
                        "Секции: values, fears, motivational_triggers, personality_evolution, "
                        "confidence_patterns, focus_patterns, emotional_trends. "
                        "По 1-2 предложения на секцию, без дополнительного текста."
                    ),
                },
                *(
                    [{"role": "system", "content": f"Existing long-term memory: {existing_long_term}"}]
                    if existing_long_term
                    else []
                ),
                *messages[-24:],
            ],
            temperature=0.3,
            timeout=timeout,
        )
        content = (response.choices[0].message.content or "").strip()
        sections = _parse_identity_memory_sections(content)
        return {
            "raw": content,
            **sections,
        }

    async def generate_deep_reflection(
        self,
        dream_title: str,
        reflection_context: str,
        period: str,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "system",
                    "content": (
                        "Сформируй deeply personal reflection message. "
                        "Фокус на трансформации личности, эмоциональной устойчивости и поддержке identity. "
                        "Не превращай в productivity-отчет. 4-6 коротких строк."
                    ),
                },
                {"role": "system", "content": f"Period: {period}. Dream: {dream_title}"},
                {"role": "system", "content": reflection_context},
            ],
            temperature=0.6,
        )
        content = response.choices[0].message.content
        return (content or "").strip() or "Ты меняешься глубже, чем кажется. Отметь один внутренний сдвиг за этот период."

    async def generate_summary_memory(self, dream_id: int, dream_title: str, timeout: float = 60.0) -> str:
        dream_messages = get_dream_messages(dream_id=dream_id, limit=25)
        if not dream_messages:
            return "Мечта создана. Первый шаг пока не зафиксирован."

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "system",
                    "content": (
                        "Сделай краткую memory summary по мечте пользователя на русском языке. "
                        "Формат: 2-3 коротких предложения, максимум 280 символов. "
                        "Без markdown, без списков."
                    ),
                },
                {"role": "system", "content": f"Название мечты: {dream_title}"},
                *dream_messages,
            ],
            temperature=0.4,
            timeout=timeout,
        )
        content = response.choices[0].message.content
        return (content or "").strip() or "Контекст обновлен, краткая память пока формируется."

    async def generate_next_step(self, dream_id: int, dream_title: str) -> str:
        # Return cached result if still fresh
        cached = _get_cached_next_step(dream_id)
        if cached is not None:
            return cached

        dream_messages = get_dream_messages(dream_id=dream_id, limit=20)
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "system",
                    "content": (
                        "Определи следующий шаг без давления. "
                        "Формат: 1 tiny step до 140 символов, который снижает сопротивление."
                    ),
                },
                {"role": "system", "content": f"Название мечты: {dream_title}"},
                *dream_messages,
            ],
            temperature=0.5,
        )
        content = (response.choices[0].message.content or "").strip() or "Определи один следующий практический шаг на сегодня."
        _set_cached_next_step(dream_id, content)
        return content

    async def generate_focus_guidance(self, dream_id: int, dream_title: str, focus_base: str) -> str:
        dream_messages = get_dream_messages(dream_id=dream_id, limit=20)
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "system",
                    "content": (
                        "Сформулируй daily focus как мягкий, выполнимый шаг на сегодня. "
                        "Сначала уменьши тревогу/сопротивление, затем предложи одно действие. "
                        "До 160 символов."
                    ),
                },
                {"role": "system", "content": f"Мечта: {dream_title}. Базовая задача: {focus_base}"},
                *dream_messages,
            ],
            temperature=0.5,
        )
        content = response.choices[0].message.content
        return (content or "").strip() or focus_base

    async def generate_coaching_diagnostic(self, dream_id: int, dream_title: str, metrics_text: str) -> str:
        dream_messages = get_dream_messages(dream_id=dream_id, limit=16)
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "system",
                    "content": (
                        "Сделай краткий коучинговый анализ: consistency, momentum, unfinished tasks, focus drift. "
                        "Формат: 4 строки, каждая до 90 символов."
                    ),
                },
                {"role": "system", "content": f"Мечта: {dream_title}. Метрики: {metrics_text}"},
                *dream_messages,
            ],
            temperature=0.4,
        )
        content = response.choices[0].message.content
        return (content or "").strip() or "Consistency: формируется\nMomentum: умеренный\nUnfinished tasks: нужен приоритет\nFocus drift: держи 1 шаг в день"


ai_service = AIService()
