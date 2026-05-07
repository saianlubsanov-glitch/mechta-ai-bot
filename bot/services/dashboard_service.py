from __future__ import annotations

from bot.services.ai_service import ai_service
from bot.services.db_service import get_last_message
from bot.services.progress_service import get_progress_snapshot


def _compact(text: str | None, fallback: str) -> str:
    if not text:
        return fallback
    normalized = " ".join(text.split())
    return normalized[:160] + ("..." if len(normalized) > 160 else "")


def _status_badge(status: str) -> str:
    mapping = {
        "active": "🟢 Активна",
        "paused": "⏸ На паузе",
        "done": "✅ Завершена",
    }
    return mapping.get(status, f"⚪ {status}")


async def build_dream_dashboard_text(dream: dict[str, str | int | None]) -> str:
    dream_id = int(dream["id"])
    title = str(dream["title"])
    status = str(dream["status"])
    summary = _compact(dream.get("summary"), "Память еще не сформирована. Нажми «🧠 AI-анализ».")
    last_message = get_last_message(dream_id=dream_id)
    last_activity = (
        f"{last_message['created_at']} · {str(last_message['role']).upper()}"
        if last_message
        else "Нет активности"
    )
    next_step = await ai_service.generate_next_step(dream_id=dream_id, dream_title=title)
    snapshot = get_progress_snapshot(dream_id=dream_id, dream_title=title)
    metrics = snapshot["metrics"]
    progress = (
        f"Streak {metrics['streak_days']} дн. · "
        f"Momentum {metrics['momentum_score']}/100 · "
        f"Tasks {metrics['completed_tasks_count']}"
    )

    return (
        f"✨ {title}\n"
        f"━━━━━━━━━━━━━━\n"
        f"📌 Статус: {_status_badge(status)}\n"
        f"🕒 Последняя активность: {last_activity}\n\n"
        f"🧠 AI memory\n{summary}\n\n"
        f"📈 Последний прогресс\n{progress}\n\n"
        f"🎯 Следующий шаг\n{_compact(next_step, 'Определи шаг на сегодня')}"
    )
