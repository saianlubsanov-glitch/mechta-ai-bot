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
            "id": int(dream.get("id", 0)),
            "user_id": int(dream.get("user_id", 0)),
            "title": str(dream.get("title", "")),
            "description": dream.get("description"),
            "summary": dream.get("summary"),
            "status": str(dream.get("status", "active")),
            "streak_days": int(dream.get("streak_days", 0)),
            "completed_tasks_count": int(dream.get("completed_tasks_count", 0)),
            "momentum_score": int(dream.get("momentum_score", 0)),
            "last_activity_at": dream.get("last_activity_at"),
            "daily_focus_text": dream.get("daily_focus_text"),
            "daily_focus_task_id": dream.get("daily_focus_task_id"),
            "release_reflection_text": dream.get("release_reflection_text"),
            "released_at": dream.get("released_at"),
            "archived_at": dream.get("archived_at"),
            "deleted_at": dream.get("deleted_at"),
            "paused_at": dream.get("paused_at"),
            "lineage_parent_id": dream.get("lineage_parent_id"),
            "lineage_child_id": dream.get("lineage_child_id"),
            "evolution_reason": dream.get("evolution_reason"),
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
    if not dream or int(dream.get("user_id", 0)) != user_id:
        return None
    return {
        "id": int(dream.get("id", 0)),
        "user_id": int(dream.get("user_id", 0)),
        "title": str(dream.get("title", "")),
        "description": dream.get("description"),
        "summary": dream.get("summary"),
        "status": str(dream.get("status", "active")),
        "streak_days": int(dream.get("streak_days", 0)),
        "completed_tasks_count": int(dream.get("completed_tasks_count", 0)),
        "momentum_score": int(dream.get("momentum_score", 0)),
        "last_activity_at": dream.get("last_activity_at"),
        "daily_focus_text": dream.get("daily_focus_text"),
        "daily_focus_task_id": dream.get("daily_focus_task_id"),
        "release_reflection_text": dream.get("release_reflection_text"),
        "released_at": dream.get("released_at"),
        "archived_at": dream.get("archived_at"),
        "deleted_at": dream.get("deleted_at"),
        "paused_at": dream.get("paused_at"),
        "lineage_parent_id": dream.get("lineage_parent_id"),
        "lineage_child_id": dream.get("lineage_child_id"),
        "evolution_reason": dream.get("evolution_reason"),
    }
