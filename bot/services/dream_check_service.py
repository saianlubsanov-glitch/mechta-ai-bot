from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DreamCheckResult:
    outcome: str
    summary: str
    fear_patterns: str
    shame_triggers: str
    external_validation_dependency: str
    intrinsic_motivation: str
    energy_resonance: str
    avoidance_signals: str


def get_dream_check_questions() -> list[str]:
    return [
        "Почему именно эта мечта?",
        "Что изменится внутри тебя, если она исполнится?",
        "Это желание больше похоже на интерес, давление, сравнение, боль, вдохновение или попытку доказать что-то?",
        "Если никто никогда не узнает, что ты достиг этого — ты все еще этого хочешь?",
        "Что в этой мечте кажется тебе живым, а что — «надо»?",
    ]


def evaluate_dream_check(answers: list[str]) -> DreamCheckResult:
    joined = " ".join(a.lower() for a in answers)

    external = "средняя"
    if any(token in joined for token in ("доказать", "сравнение", "чтобы заметили", "одобрение", "статус")):
        external = "высокая"

    intrinsic = "средняя"
    if any(token in joined for token in ("живое", "интерес", "люблю", "внутренне", "спокойствие", "свобода")):
        intrinsic = "высокая"

    fear = "умеренные"
    if any(token in joined for token in ("боюсь", "страшно", "стыдно", "провал", "тревожно")):
        fear = "выраженные"

    shame = "низкие"
    if any(token in joined for token in ("стыд", "виноват", "со мной не так")):
        shame = "повышенные"

    avoidance = "низкие"
    if any(token in joined for token in ("потом", "не готов", "не сейчас", "избегаю")):
        avoidance = "повышенные"

    resonance = "нейтральная"
    if any(token in joined for token in ("живым", "вдохновение", "энергия", "да, хочу")):
        resonance = "высокая"

    if intrinsic == "высокая" and external != "высокая":
        outcome = "validated"
        summary = "Мечта ощущается как твоя собственная и живая."
    elif external == "высокая" and intrinsic != "высокая":
        outcome = "dissolved"
        summary = "Похоже, мечта больше связана с внешним давлением, чем с внутренним направлением."
    else:
        outcome = "evolving"
        summary = "Мечта трансформируется: в ней есть более глубокое внутреннее ядро."

    return DreamCheckResult(
        outcome=outcome,
        summary=summary,
        fear_patterns=fear,
        shame_triggers=shame,
        external_validation_dependency=external,
        intrinsic_motivation=intrinsic,
        energy_resonance=resonance,
        avoidance_signals=avoidance,
    )
