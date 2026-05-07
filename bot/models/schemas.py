from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class UserSchema:
    id: int
    telegram_id: int
    username: str | None
    created_at: datetime


@dataclass(slots=True)
class DreamSchema:
    id: int
    user_id: int
    title: str
    description: str | None
    status: str
    created_at: datetime


@dataclass(slots=True)
class MessageSchema:
    id: int
    dream_id: int
    role: str
    content: str
    created_at: datetime
