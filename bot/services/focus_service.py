from __future__ import annotations

from bot.services import db_service
from bot.services.ai_service import ai_service


async def generate_daily_focus(dream_id: int, dream_title: str) -> dict[str, int | str | None]:
    open_tasks = db_service.get_open_tasks_by_dream(dream_id=dream_id, limit=8)
    if open_tasks:
        focus_task = open_tasks[0]
        focus_task_id = int(focus_task["id"])
        focus_base = str(focus_task["title"])
    else:
        focus_task_id = None
        focus_base = "Сформулируй и зафиксируй одну конкретную задачу на сегодня."

    focus_text = await ai_service.generate_focus_guidance(
        dream_id=dream_id,
        dream_title=dream_title,
        focus_base=focus_base,
    )
    db_service.update_daily_focus(dream_id=dream_id, focus_text=focus_text, focus_task_id=focus_task_id)
    db_service.create_progress_log(dream_id=dream_id, event_type="focus_updated", details=focus_text)
    return {
        "focus_text": focus_text,
        "focus_task_id": focus_task_id,
    }


def get_current_focus(dream_id: int) -> dict[str, int | str | None]:
    dream = db_service.get_dream(dream_id=dream_id)
    if not dream:
        return {"focus_text": None, "focus_task_id": None, "focus_updated_at": None}
    return {
        "focus_text": dream.get("daily_focus_text"),
        "focus_task_id": dream.get("daily_focus_task_id"),
        "focus_updated_at": dream.get("daily_focus_updated_at"),
    }
