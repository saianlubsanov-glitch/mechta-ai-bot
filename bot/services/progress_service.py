from __future__ import annotations

from datetime import date, datetime, timedelta

from bot.services import db_service


def ensure_primary_goal(dream_id: int, dream_title: str) -> int:
    goals = db_service.get_goals_by_dream(dream_id=dream_id)
    if goals:
        return int(goals[0]["id"])
    return db_service.create_goal(dream_id=dream_id, title=f"Core goal: {dream_title}", status="active", progress=0)


def create_action_task(dream_id: int, dream_title: str, task_title: str) -> int:
    goal_id = ensure_primary_goal(dream_id=dream_id, dream_title=dream_title)
    task_id = db_service.create_task(goal_id=goal_id, title=task_title.strip())
    db_service.create_progress_log(dream_id=dream_id, event_type="task_created", details=task_title.strip())
    refresh_metrics(dream_id=dream_id)
    return task_id


def complete_action_task(task_id: int) -> int | None:
    task = db_service.get_task(task_id=task_id)
    if task is None:
        return None
    db_service.complete_task(task_id=task_id)
    dream_id = int(task["dream_id"])
    db_service.create_progress_log(dream_id=dream_id, event_type="task_completed", details=str(task["title"]))
    refresh_metrics(dream_id=dream_id)
    return dream_id


def refresh_metrics(dream_id: int) -> dict[str, int | str | None]:
    goals = db_service.get_goals_by_dream(dream_id=dream_id)
    open_tasks = db_service.get_open_tasks_by_dream(dream_id=dream_id, limit=1000)
    completed_count = 0
    for goal in goals:
        goal_tasks = db_service.get_tasks_by_goal(goal_id=int(goal["id"]))
        completed_count += sum(1 for task in goal_tasks if int(task["is_completed"]) == 1)

    streak_days = _calculate_streak_days(dream_id=dream_id)
    momentum_score = max(0, min(100, completed_count * 6 + streak_days * 12 - len(open_tasks) * 2))
    last_activity_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    db_service.update_dream_metrics(
        dream_id=dream_id,
        streak_days=streak_days,
        completed_tasks_count=completed_count,
        momentum_score=momentum_score,
        last_activity_at=last_activity_at,
    )
    return {
        "streak_days": streak_days,
        "completed_tasks_count": completed_count,
        "momentum_score": momentum_score,
        "last_activity_at": last_activity_at,
    }


def get_progress_snapshot(dream_id: int, dream_title: str) -> dict[str, object]:
    goal_id = ensure_primary_goal(dream_id=dream_id, dream_title=dream_title)
    goal = db_service.get_goal(goal_id=goal_id)
    tasks = db_service.get_tasks_by_goal(goal_id=goal_id)
    open_tasks = [task for task in tasks if int(task["is_completed"]) == 0]
    done_tasks = [task for task in tasks if int(task["is_completed"]) == 1]
    metrics = refresh_metrics(dream_id=dream_id)
    total = len(tasks)
    progress_percent = int((len(done_tasks) / total) * 100) if total > 0 else 0
    if goal is not None:
        db_service.create_progress_log(dream_id=dream_id, event_type="progress_viewed", details=f"progress={progress_percent}")
    return {
        "goal_id": goal_id,
        "goal_title": goal["title"] if goal else f"Core goal: {dream_title}",
        "progress_percent": progress_percent,
        "open_tasks": open_tasks,
        "done_tasks": done_tasks,
        "metrics": metrics,
    }


def build_progress_text(dream_title: str, snapshot: dict[str, object]) -> str:
    metrics = snapshot["metrics"]
    open_tasks = snapshot["open_tasks"]
    done_tasks = snapshot["done_tasks"]
    next_open_lines: list[str] = []
    for index, task in enumerate(open_tasks[:3], start=1):
        next_open_lines.append(f"{index}. {task['title']}")
    if not next_open_lines:
        next_open_lines.append("Нет открытых задач. Добавь новую и продолжай темп.")

    return (
        f"📈 Прогресс по мечте: {dream_title}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎯 Goal: {snapshot['goal_title']}\n"
        f"✅ Выполнено: {len(done_tasks)} | 🟡 В работе: {len(open_tasks)}\n"
        f"📊 Прогресс: {snapshot['progress_percent']}%\n\n"
        f"🔥 Streak: {metrics['streak_days']} дн.\n"
        f"⚡ Momentum: {metrics['momentum_score']}/100\n"
        f"🧱 Completed tasks: {metrics['completed_tasks_count']}\n\n"
        f"Следующие задачи:\n" + "\n".join(next_open_lines)
    )


def _calculate_streak_days(dream_id: int) -> int:
    logs = db_service.get_progress_logs(dream_id=dream_id, limit=365)
    completion_days: set[date] = set()
    for log in logs:
        if str(log["event_type"]) != "task_completed":
            continue
        raw = str(log["created_at"]).split(" ")[0]
        try:
            completion_days.add(datetime.strptime(raw, "%Y-%m-%d").date())
        except ValueError:
            continue

    today = date.today()
    streak = 0
    cursor_day = today
    while cursor_day in completion_days:
        streak += 1
        cursor_day = cursor_day - timedelta(days=1)
    return streak
