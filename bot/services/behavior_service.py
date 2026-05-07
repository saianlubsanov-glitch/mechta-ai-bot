from __future__ import annotations

from bot.services import db_service


def refresh_user_behavior_metrics(user_id: int) -> dict[str, int]:
    dreams = db_service.get_user_dreams(user_id=user_id)
    if not dreams:
        metrics = {
            "engagement_score": 20,
            "churn_risk": 80,
            "motivation_level": 40,
            "consistency_score": 20,
        }
        db_service.upsert_user_behavior_metrics(user_id=user_id, **metrics)
        return metrics

    momentum_avg = int(sum(int(d["momentum_score"]) for d in dreams) / len(dreams))
    streak_avg = int(sum(int(d["streak_days"]) for d in dreams) / len(dreams))
    completed_avg = int(sum(int(d["completed_tasks_count"]) for d in dreams) / len(dreams))

    engagement_score = max(0, min(100, momentum_avg // 2 + completed_avg * 3))
    consistency_score = max(0, min(100, streak_avg * 10))
    motivation_level = max(0, min(100, (engagement_score + consistency_score) // 2))
    churn_risk = max(0, min(100, 100 - ((engagement_score + consistency_score) // 2)))

    metrics = {
        "engagement_score": engagement_score,
        "churn_risk": churn_risk,
        "motivation_level": motivation_level,
        "consistency_score": consistency_score,
    }
    db_service.upsert_user_behavior_metrics(user_id=user_id, **metrics)
    return metrics


def get_behavior_prompt(user_id: int) -> str:
    metrics = db_service.get_user_behavior_metrics(user_id=user_id)
    if metrics is None:
        return "Behavior profile unavailable; use supportive concise coaching tone."
    return (
        "Behavior metrics:\n"
        f"- engagement_score: {metrics['engagement_score']}\n"
        f"- churn_risk: {metrics['churn_risk']}\n"
        f"- motivation_level: {metrics['motivation_level']}\n"
        f"- consistency_score: {metrics['consistency_score']}"
    )
