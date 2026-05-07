from __future__ import annotations

from aiogram import Bot

from bot.services.ai_service import ai_service
from bot.services import db_service
from bot.services.emotion_service import build_emotional_guidance
from bot.services.memory_service import build_personality_context
from bot.services.reflection_service import build_reflection_context
from bot.utils.telegram_safe import safe_send


async def dispatch_event(bot: Bot, item: dict[str, object]) -> None:
    event = item["event"]
    dream = item["dream"]
    metrics = item["metrics"]

    event_id = int(event["id"])
    dream_id = int(dream.get("id", 0))
    telegram_id = int(dream.get("telegram_id", 0))
    user_id = int(dream.get("user_id", 0))

    db_service.mark_event_processing(event_id=event_id)

    try:
        event_type = str(event["event_type"])
        if event_type in {"evening_reflection", "weekly_reflection", "monthly_reflection", "momentum_review"}:
            reflection_context = build_reflection_context(user_id=user_id)
            reflection_period = event_type.replace("_", " ")
            text = await ai_service.generate_deep_reflection(
                dream_title=str(dream.get("title", "")),
                reflection_context=reflection_context,
                period=reflection_period,
            )
        else:
            text = _build_humanized_message(
                event_type=event_type,
                payload=str(event["payload"] or ""),
                dream_title=str(dream.get("title", "")),
                behavior_metrics=metrics,
                personality_context=build_personality_context(user_id=user_id),
            )
        sent = await safe_send(bot=bot, chat_id=telegram_id, text=text, user_id=telegram_id)
        if sent is None:
            raise RuntimeError("safe_send failed after retries")
        db_service.mark_event_delivered(event_id=event_id)
        db_service.create_progress_log(
            dream_id=dream_id,
            event_type="runtime_event_delivered",
            details=str(event["event_type"]),
        )
    except Exception as exc:  # noqa: BLE001
        db_service.mark_event_failed(event_id=event_id, error_text=str(exc), retry_in_minutes=30)


def _build_humanized_message(
    event_type: str,
    payload: str,
    dream_title: str,
    behavior_metrics: dict[str, int],
    personality_context: str,
) -> str:
    tone = "мягко"
    if behavior_metrics["churn_risk"] > 70:
        tone = "поддерживающе"
    elif behavior_metrics["motivation_level"] > 70:
        tone = "энергично"

    header_map = {
        "inactivity_detection": "Ты важнее идеального плана.",
        "streak_reminder": "Ты держишь ритм, это сильно.",
        "focus_reminder": "Вернем фокус на сегодня.",
        "momentum_alert": "Темп просел, но это поправимо.",
        "evening_reflection": "Короткая вечерняя рефлексия.",
        "weekly_reflection": "Время недельного обзора.",
        "momentum_review": "Проверка momentum.",
    }
    header = header_map.get(event_type, "Небольшой коучинговый пинг.")
    short_personality_hint = personality_context.splitlines()[0]
    emotional_hint = build_emotional_guidance(payload or dream_title)
    return (
        f"✨ {dream_title}\n"
        f"{header}\n\n"
        f"{payload}\n\n"
        f"Тон: {tone}. Один шаг сейчас > идеальный план позже.\n"
        f"Контекст: {short_personality_hint}\n"
        f"Эмоциональный слой: {emotional_hint}"
    )
