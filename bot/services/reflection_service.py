from __future__ import annotations

from bot.services import db_service


def update_identity_memory_layers(
    user_id: int,
    short_term: str | None = None,
    mid_term: str | None = None,
    long_term: str | None = None,
    values: str | None = None,
    fears: str | None = None,
    triggers: str | None = None,
    evolution: str | None = None,
    confidence: str | None = None,
    focus: str | None = None,
    emotional: str | None = None,
) -> None:
    db_service.upsert_identity_memory(
        user_id=user_id,
        short_term_memory=short_term,
        mid_term_memory=mid_term,
        long_term_compressed_memory=long_term,
        values_profile=values,
        fears_profile=fears,
        motivational_triggers=triggers,
        personality_evolution=evolution,
        confidence_patterns=confidence,
        focus_patterns=focus,
        emotional_trends=emotional,
    )


def detect_identity_shift(user_id: int, dream_id: int, text: str) -> None:
    normalized = text.lower()
    if any(token in normalized for token in ("уверен", "получилось", "смог")):
        db_service.create_identity_change_event(
            user_id=user_id,
            dream_id=dream_id,
            change_type="increased_confidence",
            delta_score=8,
            notes=text[:180],
        )
    if any(token in normalized for token in ("регулярно", "каждый день", "держу ритм")):
        db_service.create_identity_change_event(
            user_id=user_id,
            dream_id=dream_id,
            change_type="consistency_growth",
            delta_score=7,
            notes=text[:180],
        )
    if any(token in normalized for token in ("страшно", "боюсь", "тревожно")):
        db_service.create_identity_change_event(
            user_id=user_id,
            dream_id=dream_id,
            change_type="fear_spike",
            delta_score=-6,
            notes=text[:180],
        )


def build_reflection_context(user_id: int) -> str:
    memory = db_service.get_identity_memory(user_id=user_id)
    events = db_service.get_identity_change_events(user_id=user_id, limit=12)
    if memory is None:
        return "Identity memory limited; reflection should stay exploratory and gentle."
    trajectory = analyze_growth_regression(user_id=user_id)
    event_lines = []
    for event in events[:5]:
        event_lines.append(f"{event['change_type']} ({event['delta_score']})")
    return (
        "Identity reflection context:\n"
        f"- values: {memory['values_profile'] or 'emerging'}\n"
        f"- fears: {memory['fears_profile'] or 'not stable'}\n"
        f"- motivational_triggers: {memory['motivational_triggers'] or 'unknown'}\n"
        f"- personality_evolution: {memory['personality_evolution'] or 'in progress'}\n"
        f"- confidence_patterns: {memory['confidence_patterns'] or 'variable'}\n"
        f"- focus_patterns: {memory['focus_patterns'] or 'forming'}\n"
        f"- emotional_trends: {memory['emotional_trends'] or 'variable'}\n"
        f"- change_events: {', '.join(event_lines) if event_lines else 'none'}\n"
        f"- trajectory: {trajectory}"
    )


def analyze_growth_regression(user_id: int) -> str:
    events = db_service.get_identity_change_events(user_id=user_id, limit=40)
    if not events:
        return "insufficient data"
    delta = sum(int(event["delta_score"]) for event in events)
    if delta >= 20:
        return "strong growth in confidence and resilience"
    if delta >= 5:
        return "gradual positive growth with stable recovery"
    if delta > -5:
        return "mixed period, progress and regressions balanced"
    return "regression signal detected, needs gentle re-alignment"
