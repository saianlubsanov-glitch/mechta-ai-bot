from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ParsedCallback:
    namespace: str
    action: str
    entity_id: int | None
    raw: str


def parse_callback_data(raw: str) -> ParsedCallback | None:
    parts = raw.split(":")
    if len(parts) < 2:
        return None
    namespace, action = parts[0], parts[1]
    entity_id: int | None = None
    if len(parts) >= 3 and parts[-1].isdigit():
        entity_id = int(parts[-1])
    return ParsedCallback(namespace=namespace, action=action, entity_id=entity_id, raw=raw)


def cb(namespace: str, action: str, entity_id: int | None = None) -> str:
    if entity_id is None:
        return f"{namespace}:{action}"
    return f"{namespace}:{action}:{entity_id}"
