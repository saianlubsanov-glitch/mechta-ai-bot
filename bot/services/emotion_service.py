from __future__ import annotations

# Negation prefixes in Russian that invert the emotional meaning of a token
_NEGATION_PREFIXES = ("не ", "ничего не ", "совсем не ", "никакого ")


def _has_token_without_negation(normalized: str, tokens: tuple[str, ...]) -> bool:
    """Return True only if a token appears WITHOUT a preceding negation word."""
    for token in tokens:
        idx = normalized.find(token)
        while idx != -1:
            # Check the 15-character window before the token for negation
            prefix_window = normalized[max(0, idx - 15) : idx]
            if not any(neg in prefix_window for neg in _NEGATION_PREFIXES):
                return True
            idx = normalized.find(token, idx + 1)
    return False


def detect_emotional_state(text: str) -> str:
    normalized = text.lower()
    if _has_token_without_negation(normalized, ("трев", "боюсь", "страшно", "паник")):
        return "anxiety"
    if _has_token_without_negation(normalized, ("стыд", "виноват", "провал")):
        return "shame"
    if _has_token_without_negation(normalized, ("не могу", "замер", "ступор", "пусто")):
        return "freeze"
    if _has_token_without_negation(normalized, ("устал", "нет сил", "выгор")):
        return "overwhelm"
    if _has_token_without_negation(normalized, ("получилось", "смог", "рад", "вдохнов")):
        return "momentum"
    return "neutral"


def detect_resistance(text: str) -> bool:
    normalized = text.lower()
    return _has_token_without_negation(
        normalized, ("потом", "не сейчас", "не готов", "слишком сложно")
    )


def detect_shame_pressure(text: str) -> bool:
    normalized = text.lower()
    return _has_token_without_negation(
        normalized, ("я опять", "вечно", "со мной что-то не так", "стыдно")
    )


def detect_motivation_fragility(text: str) -> bool:
    normalized = text.lower()
    return _has_token_without_negation(
        normalized,
        ("быстро сдуваюсь", "не хватает мотивации", "нет энергии", "срываюсь"),
    )


def build_emotional_guidance(text: str) -> str:
    emotional_state = detect_emotional_state(text)
    resistance = detect_resistance(text)
    shame = detect_shame_pressure(text)
    fragile = detect_motivation_fragility(text)
    return (
        f"emotional_state={emotional_state}; "
        f"resistance={'yes' if resistance else 'no'}; "
        f"shame_pressure={'yes' if shame else 'no'}; "
        f"motivation_fragility={'yes' if fragile else 'no'}"
    )
