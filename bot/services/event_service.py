from __future__ import annotations

from datetime import datetime, timedelta

from bot.services import db_service


def evaluate_and_store_events(dream_id: int) -> list[str]:
    dream = db_service.get_dream(dream_id=dream_id)
    if dream is None:
        return []

    created: list[str] = []
    now = datetime.utcnow()
    last_activity_raw = dream["last_activity_at"]

    if last_activity_raw:
        try:
            last_activity = datetime.strptime(str(last_activity_raw), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            last_activity = now
    else:
        last_activity = now

    if now - last_activity > timedelta(days=2):
        db_service.create_reminder_event(
            dream_id=dream_id,
            event_type="inactivity_detection",
            payload="Похоже, ты выпал из ритма. Возвращаемся с одного простого шага?",
            priority=95,
            relevance_score=90,
            cooldown_key="inactivity",
        )
        created.append("inactivity_detection")

    if int(dream["streak_days"]) >= 3:
        db_service.create_reminder_event(
            dream_id=dream_id,
            event_type="streak_reminder",
            payload="Серия держится. Закрепи streak одним действием сегодня.",
            priority=60,
            relevance_score=65,
            cooldown_key="streak",
        )
        created.append("streak_reminder")

    if int(dream["momentum_score"]) < 30:
        db_service.create_reminder_event(
            dream_id=dream_id,
            event_type="momentum_alert",
            payload="Momentum просел. Сделай фокус-задачу, чтобы вернуть темп.",
            priority=80,
            relevance_score=80,
            cooldown_key="momentum",
        )
        created.append("momentum_alert")

    if not dream["daily_focus_text"]:
        db_service.create_reminder_event(
            dream_id=dream_id,
            event_type="focus_reminder",
            payload="Сформируй daily focus: один шаг, который реально сделать сегодня.",
            priority=85,
            relevance_score=85,
            cooldown_key="focus",
        )
        created.append("focus_reminder")

    _schedule_reflection_events(dream_id=dream_id, now=now)
    return created


def get_next_event_prompt(dream_id: int) -> str | None:
    events = db_service.get_pending_events(dream_id=dream_id, limit=1)
    if not events:
        return None
    return str(events[0]["payload"]) if events[0]["payload"] else None


def _schedule_reflection_events(dream_id: int, now: datetime) -> None:
    hour = now.hour
    weekday = now.weekday()
    if 19 <= hour <= 22:
        db_service.create_reminder_event(
            dream_id=dream_id,
            event_type="evening_reflection",
            payload="Вечерний рефлекс: какой 1 шаг сегодня приблизил тебя к мечте?",
            priority=55,
            relevance_score=60,
            cooldown_key="reflection_evening",
        )
    if weekday == 6 and 18 <= hour <= 22:
        db_service.create_reminder_event(
            dream_id=dream_id,
            event_type="weekly_reflection",
            payload="Недельный обзор: что сработало, что тормозит, какой фокус на новую неделю?",
            priority=70,
            relevance_score=75,
            cooldown_key="reflection_weekly",
        )
    if now.day in (1, 2) and 18 <= hour <= 22:
        db_service.create_reminder_event(
            dream_id=dream_id,
            event_type="monthly_reflection",
            payload="Месячная рефлексия: кем ты становишься через эту мечту?",
            priority=75,
            relevance_score=80,
            cooldown_key="reflection_monthly",
        )
    if weekday in (2, 5) and 18 <= hour <= 22:
        db_service.create_reminder_event(
            dream_id=dream_id,
            event_type="momentum_review",
            payload="Momentum review: удерживаешь темп или распыляешься? Выбери 1 ключевой шаг.",
            priority=65,
            relevance_score=70,
            cooldown_key="momentum_review",
        )
