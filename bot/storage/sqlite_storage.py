"""
sqlite_storage.py
=================
Persistent FSM storage backed by SQLite.

Why: the default MemoryStorage loses all user states on bot restart,
causing "Экран устарел" errors and losing active onboarding flows.
This implementation survives restarts and requires zero extra infrastructure.

Usage in main.py:
    from bot.storage.sqlite_storage import SQLiteFSMStorage
    storage = SQLiteFSMStorage()
    dp = Dispatcher(storage=storage)
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, DefaultKeyBuilder, StateType, StorageKey

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


def _mechta_db_dir() -> Path:
    override = os.getenv("MECHTA_DB_DIR", "").strip()
    if override:
        return Path(override)
    return BASE_DIR / "database"


DB_DIR = _mechta_db_dir()
_FSM_DB_PATH = DB_DIR / "fsm.db"


def _get_fsm_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_FSM_DB_PATH, check_same_thread=False, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_fsm_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fsm_states (
            key TEXT PRIMARY KEY,
            state TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fsm_data (
            key TEXT PRIMARY KEY,
            data TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fsm_states_key ON fsm_states(key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fsm_data_key ON fsm_data(key)")
    conn.commit()


class SQLiteFSMStorage(BaseStorage):
    """
    Persistent aiogram FSM storage using SQLite.
    Thread-safe via WAL mode + busy_timeout.
    """

    def __init__(self) -> None:
        self._conn = _get_fsm_connection()
        _ensure_fsm_tables(self._conn)
        logger.info("SQLiteFSMStorage initialized path=%s (MECHTA_DB_DIR=%s)", _FSM_DB_PATH, os.getenv("MECHTA_DB_DIR", ""))

    def _make_key(self, key: StorageKey) -> str:
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}"

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        db_key = self._make_key(key)
        state_value = state.state if isinstance(state, State) else state
        try:
            self._conn.execute(
                """
                INSERT INTO fsm_states (key, state, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET state=excluded.state, updated_at=CURRENT_TIMESTAMP
                """,
                (db_key, state_value),
            )
            self._conn.commit()
        except sqlite3.Error:
            logger.exception("FSM set_state failed key=%s", db_key)

    async def get_state(self, key: StorageKey) -> str | None:
        db_key = self._make_key(key)
        try:
            row = self._conn.execute(
                "SELECT state FROM fsm_states WHERE key = ?", (db_key,)
            ).fetchone()
            return row[0] if row else None
        except sqlite3.Error:
            logger.exception("FSM get_state failed key=%s", db_key)
            return None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        db_key = self._make_key(key)
        try:
            self._conn.execute(
                """
                INSERT INTO fsm_data (key, data, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET data=excluded.data, updated_at=CURRENT_TIMESTAMP
                """,
                (db_key, json.dumps(data, ensure_ascii=False)),
            )
            self._conn.commit()
        except sqlite3.Error:
            logger.exception("FSM set_data failed key=%s", db_key)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        db_key = self._make_key(key)
        try:
            row = self._conn.execute(
                "SELECT data FROM fsm_data WHERE key = ?", (db_key,)
            ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return {}
        except (sqlite3.Error, json.JSONDecodeError):
            logger.exception("FSM get_data failed key=%s", db_key)
            return {}

    async def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            logger.exception("FSM storage close failed")
