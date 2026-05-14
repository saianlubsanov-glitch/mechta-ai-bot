from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent


def _mechta_db_dir() -> Path:
    """Render: mount a persistent disk and set MECHTA_DB_DIR to that path so data survives restarts."""
    override = os.getenv("MECHTA_DB_DIR", "").strip()
    if override:
        return Path(override)
    return BASE_DIR / "database"


DB_DIR = _mechta_db_dir()
DB_PATH = DB_DIR / "mechta.db"
logger = logging.getLogger(__name__)

DEFAULT_DREAM_FIELDS: dict[str, Any] = {
    "id": 0,
    "user_id": 0,
    "title": "",
    "description": None,
    "summary": None,
    "status": "active",
    "streak_days": 0,
    "completed_tasks_count": 0,
    "momentum_score": 0,
    "last_activity_at": None,
    "daily_focus_text": None,
    "daily_focus_task_id": None,
    "daily_focus_updated_at": None,
    "release_reflection_text": None,
    "released_at": None,
    "archived_at": None,
    "deleted_at": None,
    "paused_at": None,
    "lineage_parent_id": None,
    "lineage_child_id": None,
    "evolution_reason": None,
    "created_at": None,
}


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")  # FIX: wait up to 5s instead of failing immediately
    connection.execute("PRAGMA synchronous=NORMAL")  # FIX: faster writes with WAL, still safe
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("migration started db_path=%s", DB_PATH)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                motivation_style TEXT,
                emotional_patterns TEXT,
                focus_behavior TEXT,
                communication_preference TEXT,
                fear_patterns TEXT,
                energy_patterns TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dreams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                summary TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                streak_days INTEGER NOT NULL DEFAULT 0,
                completed_tasks_count INTEGER NOT NULL DEFAULT 0,
                momentum_score INTEGER NOT NULL DEFAULT 0,
                last_activity_at TEXT,
                daily_focus_text TEXT,
                daily_focus_task_id INTEGER,
                daily_focus_updated_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dream_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dream_id) REFERENCES dreams (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dream_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                progress INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dream_id) REFERENCES dreams (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dream_lineage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_dream_id INTEGER NOT NULL,
                to_dream_id INTEGER NOT NULL,
                relation TEXT NOT NULL DEFAULT 'evolved_into',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (from_dream_id) REFERENCES dreams (id),
                FOREIGN KEY (to_dream_id) REFERENCES dreams (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dream_check_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dream_id INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                fear_patterns TEXT,
                shame_triggers TEXT,
                external_validation_dependency TEXT,
                intrinsic_motivation TEXT,
                energy_resonance TEXT,
                avoidance_signals TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dream_id) REFERENCES dreams (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                is_completed INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (goal_id) REFERENCES goals (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS progress_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dream_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dream_id) REFERENCES dreams (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reminder_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dream_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                priority INTEGER NOT NULL DEFAULT 50,
                relevance_score INTEGER NOT NULL DEFAULT 50,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                cooldown_key TEXT,
                next_attempt_at TEXT DEFAULT CURRENT_TIMESTAMP,
                delivered_at TEXT,
                last_error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dream_id) REFERENCES dreams (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_behavior_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                engagement_score INTEGER NOT NULL DEFAULT 50,
                churn_risk INTEGER NOT NULL DEFAULT 50,
                motivation_level INTEGER NOT NULL DEFAULT 50,
                consistency_score INTEGER NOT NULL DEFAULT 50,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS identity_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                short_term_memory TEXT,
                mid_term_memory TEXT,
                long_term_compressed_memory TEXT,
                values_profile TEXT,
                fears_profile TEXT,
                motivational_triggers TEXT,
                personality_evolution TEXT,
                confidence_patterns TEXT,
                focus_patterns TEXT,
                emotional_trends TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS identity_change_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                dream_id INTEGER,
                change_type TEXT NOT NULL,
                delta_score INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (dream_id) REFERENCES dreams (id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_rhythm_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                timezone TEXT DEFAULT 'UTC',
                sleep_start_hour INTEGER NOT NULL DEFAULT 23,
                sleep_end_hour INTEGER NOT NULL DEFAULT 7,
                active_start_hour INTEGER NOT NULL DEFAULT 10,
                active_end_hour INTEGER NOT NULL DEFAULT 20,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        _ensure_dreams_summary_column(cursor)
        _ensure_dreams_progress_columns(cursor)
        _ensure_dream_lifecycle_columns(cursor)
        _ensure_reminder_event_columns(cursor)
        _ensure_indexes(cursor)
        conn.commit()
    logger.info("migration completed")


def _ensure_indexes(cursor: sqlite3.Cursor) -> None:
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_dream_id ON messages(dream_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_goals_dream_id ON goals(dream_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_goal_id ON tasks(goal_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_progress_logs_dream_id ON progress_logs(dream_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminder_dream_id ON reminder_events(dream_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminder_status_next ON reminder_events(status, next_attempt_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_identity_change_user_id ON identity_change_events(user_id)")
    logger.info("indexes ensured")


def _ensure_dreams_summary_column(cursor: sqlite3.Cursor) -> None:
    columns = cursor.execute("PRAGMA table_info(dreams)").fetchall()
    column_names = {str(column["name"]) for column in columns}
    if "summary" not in column_names:
        cursor.execute("ALTER TABLE dreams ADD COLUMN summary TEXT")
        logger.info("column added table=dreams column=summary")


def _ensure_dreams_progress_columns(cursor: sqlite3.Cursor) -> None:
    columns = cursor.execute("PRAGMA table_info(dreams)").fetchall()
    column_names = {str(column["name"]) for column in columns}
    required_columns = {
        "streak_days": "ALTER TABLE dreams ADD COLUMN streak_days INTEGER NOT NULL DEFAULT 0",
        "completed_tasks_count": "ALTER TABLE dreams ADD COLUMN completed_tasks_count INTEGER NOT NULL DEFAULT 0",
        "momentum_score": "ALTER TABLE dreams ADD COLUMN momentum_score INTEGER NOT NULL DEFAULT 0",
        "last_activity_at": "ALTER TABLE dreams ADD COLUMN last_activity_at TEXT",
        "daily_focus_text": "ALTER TABLE dreams ADD COLUMN daily_focus_text TEXT",
        "daily_focus_task_id": "ALTER TABLE dreams ADD COLUMN daily_focus_task_id INTEGER",
        "daily_focus_updated_at": "ALTER TABLE dreams ADD COLUMN daily_focus_updated_at TEXT",
    }
    for name, ddl in required_columns.items():
        if name not in column_names:
            cursor.execute(ddl)
            logger.info("column added table=dreams column=%s", name)


def _ensure_dream_lifecycle_columns(cursor: sqlite3.Cursor) -> None:
    columns = cursor.execute("PRAGMA table_info(dreams)").fetchall()
    column_names = {str(column["name"]) for column in columns}
    required_columns = {
        "release_reflection_text": "ALTER TABLE dreams ADD COLUMN release_reflection_text TEXT",
        "released_at": "ALTER TABLE dreams ADD COLUMN released_at TEXT",
        "archived_at": "ALTER TABLE dreams ADD COLUMN archived_at TEXT",
        "deleted_at": "ALTER TABLE dreams ADD COLUMN deleted_at TEXT",
        "paused_at": "ALTER TABLE dreams ADD COLUMN paused_at TEXT",
        "lineage_parent_id": "ALTER TABLE dreams ADD COLUMN lineage_parent_id INTEGER",
        "lineage_child_id": "ALTER TABLE dreams ADD COLUMN lineage_child_id INTEGER",
        "evolution_reason": "ALTER TABLE dreams ADD COLUMN evolution_reason TEXT",
    }
    for name, ddl in required_columns.items():
        if name not in column_names:
            cursor.execute(ddl)
            logger.info("column added table=dreams column=%s", name)


def _ensure_reminder_event_columns(cursor: sqlite3.Cursor) -> None:
    columns = cursor.execute("PRAGMA table_info(reminder_events)").fetchall()
    column_names = {str(column["name"]) for column in columns}
    required_columns = {
        "priority": "ALTER TABLE reminder_events ADD COLUMN priority INTEGER NOT NULL DEFAULT 50",
        "relevance_score": "ALTER TABLE reminder_events ADD COLUMN relevance_score INTEGER NOT NULL DEFAULT 50",
        "attempts": "ALTER TABLE reminder_events ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
        "max_attempts": "ALTER TABLE reminder_events ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3",
        "cooldown_key": "ALTER TABLE reminder_events ADD COLUMN cooldown_key TEXT",
        "next_attempt_at": "ALTER TABLE reminder_events ADD COLUMN next_attempt_at TEXT DEFAULT CURRENT_TIMESTAMP",
        "delivered_at": "ALTER TABLE reminder_events ADD COLUMN delivered_at TEXT",
        "last_error": "ALTER TABLE reminder_events ADD COLUMN last_error TEXT",
    }
    for name, ddl in required_columns.items():
        if name not in column_names:
            cursor.execute(ddl)
            logger.info("column added table=reminder_events column=%s", name)


def normalize_dream_row(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return dict(DEFAULT_DREAM_FIELDS)
    as_dict = dict(row) if not isinstance(row, dict) else dict(row)
    normalized = dict(DEFAULT_DREAM_FIELDS)
    normalized.update(as_dict)
    return normalized


def create_user(telegram_id: int, username: str | None) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO users (telegram_id, username)
            VALUES (?, ?)
            """,
            (telegram_id, username),
        )
        cursor.execute(
            """
            UPDATE users
            SET username = COALESCE(?, username)
            WHERE telegram_id = ?
            """,
            (username, telegram_id),
        )
        conn.commit()
        row = cursor.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Unable to create or fetch user.")
        return int(row["id"])


def get_user(telegram_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def create_dream(
    user_id: int,
    title: str,
    description: str | None = None,
    status: str = "active",
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO dreams (user_id, title, description, status)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, title, description, status),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_dream_title(dream_id: int, title: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE dreams SET title = ? WHERE id = ?",
            (title, dream_id),
        )
        conn.commit()


def get_user_dreams(user_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM dreams
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
        return [normalize_dream_row(row) for row in rows]


def get_dream(dream_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM dreams WHERE id = ?",
            (dream_id,),
        ).fetchone()
        return normalize_dream_row(row) if row else None


def update_dream_status(dream_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE dreams SET status = ? WHERE id = ?",
            (status, dream_id),
        )
        conn.commit()


def release_dream(dream_id: int, reflection_text: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE dreams
            SET status = 'released',
                release_reflection_text = ?,
                released_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (reflection_text, dream_id),
        )
        conn.commit()


def archive_dream(dream_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE dreams
            SET status = 'archived',
                archived_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (dream_id,),
        )
        conn.commit()


def mark_dream_deleted(dream_id: int, reflection_text: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE dreams
            SET status = 'deleted',
                release_reflection_text = ?,
                deleted_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (reflection_text, dream_id),
        )
        conn.commit()


def update_dream_summary(dream_id: int, summary: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE dreams SET summary = ? WHERE id = ?",
            (summary, dream_id),
        )
        conn.commit()


def update_dream_metrics(
    dream_id: int,
    streak_days: int,
    completed_tasks_count: int,
    momentum_score: int,
    last_activity_at: str | None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE dreams
            SET streak_days = ?,
                completed_tasks_count = ?,
                momentum_score = ?,
                last_activity_at = ?
            WHERE id = ?
            """,
            (streak_days, completed_tasks_count, momentum_score, last_activity_at, dream_id),
        )
        conn.commit()


def update_daily_focus(dream_id: int, focus_text: str, focus_task_id: int | None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE dreams
            SET daily_focus_text = ?,
                daily_focus_task_id = ?,
                daily_focus_updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (focus_text, focus_task_id, dream_id),
        )
        conn.commit()


def save_message(dream_id: int, role: str, content: str) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO messages (dream_id, role, content)
            VALUES (?, ?, ?)
            """,
            (dream_id, role, content),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_dream_messages(dream_id: int, limit: int = 30) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE dream_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (dream_id, limit),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def get_last_message(dream_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT role, content, created_at
            FROM messages
            WHERE dream_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (dream_id,),
        ).fetchone()


def create_goal(dream_id: int, title: str, status: str = "active", progress: int = 0) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO goals (dream_id, title, status, progress)
            VALUES (?, ?, ?, ?)
            """,
            (dream_id, title, status, progress),
        )
        conn.commit()
        return int(cursor.lastrowid)


def create_dream_lineage(from_dream_id: int, to_dream_id: int, relation: str = "evolved_into") -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO dream_lineage (from_dream_id, to_dream_id, relation)
            VALUES (?, ?, ?)
            """,
            (from_dream_id, to_dream_id, relation),
        )
        conn.commit()
        return int(cursor.lastrowid)


def save_dream_check_insight(
    dream_id: int,
    outcome: str,
    fear_patterns: str,
    shame_triggers: str,
    external_validation_dependency: str,
    intrinsic_motivation: str,
    energy_resonance: str,
    avoidance_signals: str,
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO dream_check_insights (
                dream_id,
                outcome,
                fear_patterns,
                shame_triggers,
                external_validation_dependency,
                intrinsic_motivation,
                energy_resonance,
                avoidance_signals
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dream_id,
                outcome,
                fear_patterns,
                shame_triggers,
                external_validation_dependency,
                intrinsic_motivation,
                energy_resonance,
                avoidance_signals,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_goals_by_dream(dream_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM goals
            WHERE dream_id = ?
            ORDER BY id DESC
            """,
            (dream_id,),
        ).fetchall()
        return list(rows)


def get_goal(goal_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM goals WHERE id = ?",
            (goal_id,),
        ).fetchone()


def create_task(goal_id: int, title: str) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (goal_id, title)
            VALUES (?, ?)
            """,
            (goal_id, title),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_tasks_by_goal(goal_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE goal_id = ?
            ORDER BY is_completed ASC, id DESC
            """,
            (goal_id,),
        ).fetchall()
        return list(rows)


def get_open_tasks_by_dream(dream_id: int, limit: int = 10) -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT tasks.*, goals.dream_id
            FROM tasks
            JOIN goals ON goals.id = tasks.goal_id
            WHERE goals.dream_id = ? AND tasks.is_completed = 0
            ORDER BY tasks.id ASC
            LIMIT ?
            """,
            (dream_id, limit),
        ).fetchall()
        return list(rows)


def get_task(task_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT tasks.*, goals.dream_id
            FROM tasks
            JOIN goals ON goals.id = tasks.goal_id
            WHERE tasks.id = ?
            """,
            (task_id,),
        ).fetchone()


def complete_task(task_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE tasks
            SET is_completed = 1,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (task_id,),
        )
        conn.commit()


def hard_delete_dream_cascade(dream_id: int) -> None:
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM tasks WHERE goal_id IN (SELECT id FROM goals WHERE dream_id = ?)", (dream_id,))
            conn.execute("DELETE FROM goals WHERE dream_id = ?", (dream_id,))
            conn.execute("DELETE FROM messages WHERE dream_id = ?", (dream_id,))
            conn.execute("DELETE FROM progress_logs WHERE dream_id = ?", (dream_id,))
            conn.execute("DELETE FROM reminder_events WHERE dream_id = ?", (dream_id,))
            conn.execute("DELETE FROM dream_check_insights WHERE dream_id = ?", (dream_id,))
            conn.execute("DELETE FROM dream_lineage WHERE from_dream_id = ? OR to_dream_id = ?", (dream_id, dream_id))
            conn.execute("DELETE FROM identity_change_events WHERE dream_id = ?", (dream_id,))
            conn.execute("DELETE FROM dreams WHERE id = ?", (dream_id,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def create_progress_log(dream_id: int, event_type: str, details: str | None = None) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO progress_logs (dream_id, event_type, details)
            VALUES (?, ?, ?)
            """,
            (dream_id, event_type, details),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_progress_logs(dream_id: int, limit: int = 30) -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM progress_logs
            WHERE dream_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (dream_id, limit),
        ).fetchall()
        return list(rows)


def get_latest_progress_log(dream_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT *
            FROM progress_logs
            WHERE dream_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (dream_id,),
        ).fetchone()


def upsert_user_memory(
    user_id: int,
    motivation_style: str | None = None,
    emotional_patterns: str | None = None,
    focus_behavior: str | None = None,
    communication_preference: str | None = None,
    fear_patterns: str | None = None,
    energy_patterns: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO user_memory (
                user_id,
                motivation_style,
                emotional_patterns,
                focus_behavior,
                communication_preference,
                fear_patterns,
                energy_patterns
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                motivation_style,
                emotional_patterns,
                focus_behavior,
                communication_preference,
                fear_patterns,
                energy_patterns,
            ),
        )
        conn.execute(
            """
            UPDATE user_memory
            SET motivation_style = COALESCE(?, motivation_style),
                emotional_patterns = COALESCE(?, emotional_patterns),
                focus_behavior = COALESCE(?, focus_behavior),
                communication_preference = COALESCE(?, communication_preference),
                fear_patterns = COALESCE(?, fear_patterns),
                energy_patterns = COALESCE(?, energy_patterns),
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (
                motivation_style,
                emotional_patterns,
                focus_behavior,
                communication_preference,
                fear_patterns,
                energy_patterns,
                user_id,
            ),
        )
        conn.commit()


def get_user_memory(user_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM user_memory WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def create_reminder_event(
    dream_id: int,
    event_type: str,
    payload: str | None = None,
    priority: int = 50,
    relevance_score: int = 50,
    cooldown_key: str | None = None,
) -> int:
    if cooldown_key and has_pending_event_by_cooldown(dream_id=dream_id, cooldown_key=cooldown_key):
        return 0
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reminder_events (dream_id, event_type, payload, priority, relevance_score, cooldown_key)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (dream_id, event_type, payload, priority, relevance_score, cooldown_key),
        )
        conn.commit()
        return int(cursor.lastrowid)


def has_pending_event_by_cooldown(dream_id: int, cooldown_key: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM reminder_events
            WHERE dream_id = ?
              AND cooldown_key = ?
              AND status IN ('pending', 'processing')
            LIMIT 1
            """,
            (dream_id, cooldown_key),
        ).fetchone()
        return row is not None


def get_pending_events(dream_id: int, limit: int = 20) -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM reminder_events
            WHERE dream_id = ? AND status = 'pending'
            ORDER BY id DESC
            LIMIT ?
            """,
            (dream_id, limit),
        ).fetchall()
        return list(rows)


def get_due_pending_events(limit: int = 50) -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM reminder_events
            WHERE status = 'pending'
              AND attempts < max_attempts
              AND datetime(COALESCE(next_attempt_at, CURRENT_TIMESTAMP)) <= datetime(CURRENT_TIMESTAMP)
            ORDER BY priority DESC, relevance_score DESC, id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return list(rows)


def mark_event_processing(event_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE reminder_events SET status = 'processing' WHERE id = ?",
            (event_id,),
        )
        conn.commit()


def mark_event_delivered(event_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE reminder_events
            SET status = 'delivered',
                delivered_at = CURRENT_TIMESTAMP,
                last_error = NULL
            WHERE id = ?
            """,
            (event_id,),
        )
        conn.commit()


def mark_event_failed(event_id: int, error_text: str, retry_in_minutes: int = 30) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE reminder_events
            SET status = 'pending',
                attempts = attempts + 1,
                last_error = ?,
                next_attempt_at = datetime(CURRENT_TIMESTAMP, ?)
            WHERE id = ?
            """,
            (error_text[:240], f"+{retry_in_minutes} minutes", event_id),
        )
        conn.commit()


def get_dream_by_id_with_user(dream_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT dreams.*, users.telegram_id, users.username
            FROM dreams
            JOIN users ON users.id = dreams.user_id
            WHERE dreams.id = ?
            """,
            (dream_id,),
        ).fetchone()
        if row is None:
            return None
        normalized = normalize_dream_row(row)
        normalized["telegram_id"] = row["telegram_id"]
        normalized["username"] = row["username"]
        return normalized


def count_user_delivered_events_today(user_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(reminder_events.id) AS cnt
            FROM reminder_events
            JOIN dreams ON dreams.id = reminder_events.dream_id
            WHERE dreams.user_id = ?
              AND reminder_events.status = 'delivered'
              AND date(reminder_events.delivered_at) = date('now')
            """,
            (user_id,),
        ).fetchone()
        return int(row["cnt"]) if row else 0


def was_cooldown_sent_recently(user_id: int, cooldown_key: str, within_minutes: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT reminder_events.id
            FROM reminder_events
            JOIN dreams ON dreams.id = reminder_events.dream_id
            WHERE dreams.user_id = ?
              AND reminder_events.cooldown_key = ?
              AND reminder_events.status = 'delivered'
              AND datetime(reminder_events.delivered_at) >= datetime(CURRENT_TIMESTAMP, ?)
            LIMIT 1
            """,
            (user_id, cooldown_key, f"-{within_minutes} minutes"),
        ).fetchone()
        return row is not None


def upsert_user_behavior_metrics(
    user_id: int,
    engagement_score: int,
    churn_risk: int,
    motivation_level: int,
    consistency_score: int,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO user_behavior_metrics (
                user_id,
                engagement_score,
                churn_risk,
                motivation_level,
                consistency_score
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, engagement_score, churn_risk, motivation_level, consistency_score),
        )
        conn.execute(
            """
            UPDATE user_behavior_metrics
            SET engagement_score = ?,
                churn_risk = ?,
                motivation_level = ?,
                consistency_score = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (engagement_score, churn_risk, motivation_level, consistency_score, user_id),
        )
        conn.commit()


def get_user_behavior_metrics(user_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM user_behavior_metrics WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def upsert_identity_memory(
    user_id: int,
    short_term_memory: str | None = None,
    mid_term_memory: str | None = None,
    long_term_compressed_memory: str | None = None,
    values_profile: str | None = None,
    fears_profile: str | None = None,
    motivational_triggers: str | None = None,
    personality_evolution: str | None = None,
    confidence_patterns: str | None = None,
    focus_patterns: str | None = None,
    emotional_trends: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO identity_memory (user_id)
            VALUES (?)
            """,
            (user_id,),
        )
        conn.execute(
            """
            UPDATE identity_memory
            SET short_term_memory = COALESCE(?, short_term_memory),
                mid_term_memory = COALESCE(?, mid_term_memory),
                long_term_compressed_memory = COALESCE(?, long_term_compressed_memory),
                values_profile = COALESCE(?, values_profile),
                fears_profile = COALESCE(?, fears_profile),
                motivational_triggers = COALESCE(?, motivational_triggers),
                personality_evolution = COALESCE(?, personality_evolution),
                confidence_patterns = COALESCE(?, confidence_patterns),
                focus_patterns = COALESCE(?, focus_patterns),
                emotional_trends = COALESCE(?, emotional_trends),
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (
                short_term_memory,
                mid_term_memory,
                long_term_compressed_memory,
                values_profile,
                fears_profile,
                motivational_triggers,
                personality_evolution,
                confidence_patterns,
                focus_patterns,
                emotional_trends,
                user_id,
            ),
        )
        conn.commit()


def get_identity_memory(user_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM identity_memory WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def create_identity_change_event(
    user_id: int,
    change_type: str,
    delta_score: int,
    notes: str | None = None,
    dream_id: int | None = None,
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO identity_change_events (user_id, dream_id, change_type, delta_score, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, dream_id, change_type, delta_score, notes),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_identity_change_events(user_id: int, limit: int = 50) -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM identity_change_events
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return list(rows)


def upsert_user_rhythm_preferences(
    user_id: int,
    timezone: str = "UTC",
    sleep_start_hour: int = 23,
    sleep_end_hour: int = 7,
    active_start_hour: int = 10,
    active_end_hour: int = 20,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO user_rhythm_preferences (
                user_id, timezone, sleep_start_hour, sleep_end_hour, active_start_hour, active_end_hour
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, timezone, sleep_start_hour, sleep_end_hour, active_start_hour, active_end_hour),
        )
        conn.execute(
            """
            UPDATE user_rhythm_preferences
            SET timezone = ?,
                sleep_start_hour = ?,
                sleep_end_hour = ?,
                active_start_hour = ?,
                active_end_hour = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (timezone, sleep_start_hour, sleep_end_hour, active_start_hour, active_end_hour, user_id),
        )
        conn.commit()


def get_user_rhythm_preferences(user_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM user_rhythm_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
