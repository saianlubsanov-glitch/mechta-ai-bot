from __future__ import annotations

from bot.services import db_service


def save_onboarding_memory(
    user_id: int,
    why_important: str,
    obstacles: str,
    emotional_state: str,
) -> None:
    """
    Save initial user profile derived from onboarding answers.
    Instead of brittle length/keyword heuristics, we store the raw answers
    and let the AI determine real patterns via build_personality_context().
    The fields below represent structured starting defaults that will be
    refined by the identity-memory pipeline after the first AI interactions.
    """
    # Derive a rough motivation_style: purpose-driven if the user describes
    # a meaningful "why" (≥ 3 words), otherwise assume quick-win orientation.
    words_in_why = len(why_important.split())
    motivation_style = "purpose-driven" if words_in_why >= 5 else "quick-win-driven"

    # Detect common resistance patterns more carefully
    obstacles_lower = obstacles.lower()
    if any(phrase in obstacles_lower for phrase in ("нет времени", "не хватает времени", "занят")):
        focus_behavior = "time-constrained"
    elif any(phrase in obstacles_lower for phrase in ("не знаю с чего", "не понимаю", "непонятно")):
        focus_behavior = "clarity-seeking"
    elif any(phrase in obstacles_lower for phrase in ("лень", "откладываю", "прокрастин")):
        focus_behavior = "procrastination-prone"
    else:
        focus_behavior = "structured"

    # Store raw answers as fear/energy patterns for AI to interpret later
    fear_patterns = obstacles[:280]
    energy_patterns = emotional_state[:280]

    # communication_preference starts neutral; refined through interactions
    communication_preference = "short-guided"

    db_service.upsert_user_memory(
        user_id=user_id,
        motivation_style=motivation_style,
        emotional_patterns=emotional_state[:280],
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

    # Procrastination / delay signals
    if any(t in normalized for t in ("потом сделаю", "не успеваю", "откладываю", "руки не доходят")):
        focus_behavior = "inconsistent"
    # Execution / completion signals (require positive context, not negated)
    elif any(t in normalized for t in ("сделал", "готово", "выполнил", "закончил", "завершил")):
        # Make sure it's not "не сделал" etc.
        if not any(neg + t in normalized for neg in ("не ", "ещё не ", "так и не ") for t in ("сделал", "сделала")):
            focus_behavior = "execution-oriented"

    emotional_patterns = None
    if any(token in normalized for token in ("тревог", "страх", "пережива", "боюсь")):
        if not any(f"не {t}" in normalized for t in ("боюсь", "страшно")):
            emotional_patterns = "anxiety spikes around progress uncertainty"
    elif any(token in normalized for token in ("вдохнов", "заряж", "мотив", "энергия")):
        emotional_patterns = "high motivation waves"

    if focus_behavior or emotional_patterns:
        db_service.upsert_user_memory(
            user_id=user_id,
            focus_behavior=focus_behavior,
            emotional_patterns=emotional_patterns,
        )
