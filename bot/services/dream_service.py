from __future__ import annotations

from bot.services import db_service


def ensure_user(telegram_id: int, username: str | None) -> int:
    user = db_service.get_user(telegram_id)
    if user:
        return int(user["id"])
    return db_service.create_user(telegram_id=telegram_id, username=username)


def create_user_dream(telegram_id: int, username: str | None, title: str) -> int:
    user_id = ensure_user(telegram_id=telegram_id, username=username)
    return db_service.create_dream(user_id=user_id, title=title.strip())


def list_user_dreams(telegram_id: int, username: str | None) -> list[dict[str, str | int | None]]:
    user_id = ensure_user(telegram_id=telegram_id, username=username)
    dreams = db_service.get_user_dreams(user_id=user_id)
    return [
        {
            "id": int(dream["id"]),
            "user_id": int(dream["user_id"]),
            "title": str(dream["title"]),
            "description": dream["description"],
            "summary": dream["summary"],
            "status": str(dream["status"]),
            "streak_days": int(dream["streak_days"]),
            "completed_tasks_count": int(dream["completed_tasks_count"]),
            "momentum_score": int(dream["momentum_score"]),
            "last_activity_at": dream["last_activity_at"],
            "daily_focus_text": dream["daily_focus_text"],
            "daily_focus_task_id": dream["daily_focus_task_id"],
            "release_reflection_text": dream["release_reflection_text"],
            "released_at": dream["released_at"],
            "archived_at": dream["archived_at"],
            "deleted_at": dream["deleted_at"],
        }
        for dream in dreams
    ]


def get_user_dream_by_id(
    telegram_id: int,
    username: str | None,
    dream_id: int,
) -> dict[str, str | int | None] | None:
    user_id = ensure_user(telegram_id=telegram_id, username=username)
    dream = db_service.get_dream(dream_id=dream_id)
    if not dream or int(dream["user_id"]) != user_id:
        return None
    return {
        "id": int(dream["id"]),
        "user_id": int(dream["user_id"]),
        "title": str(dream["title"]),
        "description": dream["description"],
        "summary": dream["summary"],
        "status": str(dream["status"]),
        "streak_days": int(dream["streak_days"]),
        "completed_tasks_count": int(dream["completed_tasks_count"]),
        "momentum_score": int(dream["momentum_score"]),
        "last_activity_at": dream["last_activity_at"],
        "daily_focus_text": dream["daily_focus_text"],
        "daily_focus_task_id": dream["daily_focus_task_id"],
        "release_reflection_text": dream["release_reflection_text"],
        "released_at": dream["released_at"],
        "archived_at": dream["archived_at"],
        "deleted_at": dream["deleted_at"],
    }
