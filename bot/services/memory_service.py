from __future__ import annotations

from bot.services import db_service


def save_onboarding_memory(
    user_id: int,
    why_important: str,
    obstacles: str,
    emotional_state: str,
) -> None:
    motivation_style = "purpose-driven" if len(why_important) > 40 else "quick-win-driven"
    focus_behavior = "reactive" if "нет времени" in obstacles.lower() else "structured"
    communication_preference = "short-guided"
    fear_patterns = obstacles[:180]
    energy_patterns = emotional_state[:180]

    db_service.upsert_user_memory(
        user_id=user_id,
        motivation_style=motivation_style,
        emotional_patterns=emotional_state[:180],
        focus_behavior=focus_behavior,
        communication_preference=communication_preference,
        fear_patterns=fear_patterns,
        energy_patterns=energy_patterns,
    )
    db_service.upsert_user_rhythm_preferences(user_id=user_id)


def build_personality_context(user_id: int) -> str:
    memory = db_service.get_user_memory(user_id=user_id)
    identity_memory = db_service.get_identity_memory(user_id=user_id)
    if memory is None:
        return (
            "Personality memory: limited. Use short conversational coaching, "
            "ask one clarifying question максимум when needed."
        )
    return (
        "Personality memory profile:\n"
        f"- motivation_style: {memory['motivation_style'] or 'unknown'}\n"
        f"- emotional_patterns: {memory['emotional_patterns'] or 'unknown'}\n"
        f"- focus_behavior: {memory['focus_behavior'] or 'unknown'}\n"
        f"- communication_preference: {memory['communication_preference'] or 'short-guided'}\n"
        f"- fear_patterns: {memory['fear_patterns'] or 'unknown'}\n"
        f"- energy_patterns: {memory['energy_patterns'] or 'unknown'}\n"
        f"- long_term_identity: {(identity_memory['long_term_compressed_memory'] if identity_memory else 'not ready') or 'not ready'}"
    )


def update_behavioral_memory(user_id: int, user_message: str) -> None:
    normalized = user_message.lower()
    focus_behavior = None
    if "потом" in normalized or "не успеваю" in normalized:
        focus_behavior = "inconsistent"
    if "сделал" in normalized or "готово" in normalized:
        focus_behavior = "execution-oriented"

    emotional_patterns = None
    if any(token in normalized for token in ("тревог", "страх", "пережива")):
        emotional_patterns = "anxiety spikes around progress uncertainty"
    elif any(token in normalized for token in ("вдохнов", "заряж", "мотив")):
        emotional_patterns = "high motivation waves"

    if focus_behavior or emotional_patterns:
        db_service.upsert_user_memory(
            user_id=user_id,
            focus_behavior=focus_behavior,
            emotional_patterns=emotional_patterns,
        )
