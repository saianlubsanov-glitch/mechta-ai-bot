from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bot.services import db_service
from bot.services.behavior_service import refresh_user_behavior_metrics

DAILY_SEND_LIMIT = 4
GLOBAL_COOLDOWN_MINUTES = 90
MIN_RELEVANCE_SCORE = 45


def pick_due_events(batch_size: int = 20) -> list[dict[str, object]]:
    candidates = db_service.get_due_pending_events(limit=batch_size * 3)
    selected: list[dict[str, object]] = []

    for event in candidates:
        dream = db_service.get_dream_by_id_with_user(dream_id=int(event["dream_id"]))
        if dream is None:
            continue

        user_id = int(dream["user_id"])
        metrics = refresh_user_behavior_metrics(user_id=user_id)
        relevance = int(event["relevance_score"])

        if relevance < MIN_RELEVANCE_SCORE and metrics["engagement_score"] > 50:
            continue

        sent_today = db_service.count_user_delivered_events_today(user_id=user_id)
        if sent_today >= DAILY_SEND_LIMIT:
            continue

        if not _is_user_in_delivery_window(user_id=user_id):
            continue

        cooldown_key = str(event["cooldown_key"] or "default")
        if db_service.was_cooldown_sent_recently(
            user_id=user_id,
            cooldown_key=cooldown_key,
            within_minutes=GLOBAL_COOLDOWN_MINUTES,
        ):
            continue

        selected.append(
            {
                "event": event,
                "dream": dream,
                "metrics": metrics,
            }
        )
        if len(selected) >= batch_size:
            break

    return selected


def _is_user_in_delivery_window(user_id: int) -> bool:
    prefs = db_service.get_user_rhythm_preferences(user_id=user_id)
    if prefs is None:
        return True
    tz_name = str(prefs["timezone"] or "UTC")
    try:
        now_local = datetime.now(ZoneInfo(tz_name))
    except Exception:  # noqa: BLE001
        now_local = datetime.utcnow()
    hour = now_local.hour
    sleep_start = int(prefs["sleep_start_hour"])
    sleep_end = int(prefs["sleep_end_hour"])
    active_start = int(prefs["active_start_hour"])
    active_end = int(prefs["active_end_hour"])

    in_sleep = hour >= sleep_start or hour < sleep_end
    if in_sleep:
        return False
    return active_start <= hour < active_end
