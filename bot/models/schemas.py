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
    summary: str | None
    status: str
    streak_days: int
    completed_tasks_count: int
    momentum_score: int
    last_activity_at: datetime | None
    daily_focus_text: str | None
    daily_focus_task_id: int | None
    daily_focus_updated_at: datetime | None
    created_at: datetime


@dataclass(slots=True)
class MessageSchema:
    id: int
    dream_id: int
    role: str
    content: str
    created_at: datetime


@dataclass(slots=True)
class GoalSchema:
    id: int
    dream_id: int
    title: str
    status: str
    progress: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class TaskSchema:
    id: int
    goal_id: int
    title: str
    is_completed: bool
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class ProgressLogSchema:
    id: int
    dream_id: int
    event_type: str
    details: str | None
    created_at: datetime


@dataclass(slots=True)
class UserBehaviorMetricsSchema:
    id: int
    user_id: int
    engagement_score: int
    churn_risk: int
    motivation_level: int
    consistency_score: int
    updated_at: datetime
    created_at: datetime


@dataclass(slots=True)
class IdentityMemorySchema:
    id: int
    user_id: int
    short_term_memory: str | None
    mid_term_memory: str | None
    long_term_compressed_memory: str | None
    values_profile: str | None
    fears_profile: str | None
    motivational_triggers: str | None
    personality_evolution: str | None
    confidence_patterns: str | None
    focus_patterns: str | None
    emotional_trends: str | None
    updated_at: datetime
    created_at: datetime


@dataclass(slots=True)
class IdentityChangeEventSchema:
    id: int
    user_id: int
    dream_id: int | None
    change_type: str
    delta_score: int
    notes: str | None
    created_at: datetime
