from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_profiles (
        id TEXT PRIMARY KEY,
        adapter_name TEXT NOT NULL,
        platform TEXT NOT NULL,
        account_id TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        default_enabled INTEGER NOT NULL DEFAULT 1,
        default_character_id TEXT,
        data_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        UNIQUE(adapter_name, platform, account_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS characters (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        data_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp_sessions (
        id TEXT PRIMARY KEY,
        unified_msg_origin TEXT NOT NULL UNIQUE,
        account_profile_id TEXT,
        paused INTEGER NOT NULL DEFAULT 0,
        active_character_id TEXT,
        data_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rp_messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        speaker TEXT NOT NULL,
        content TEXT NOT NULL,
        visible INTEGER NOT NULL DEFAULT 1,
        turn_number INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        data_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lorebooks (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        scope TEXT NOT NULL,
        session_id TEXT,
        data_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lorebook_entries (
        id TEXT PRIMARY KEY,
        lorebook_id TEXT NOT NULL,
        title TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        data_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        type TEXT NOT NULL,
        content TEXT NOT NULL,
        importance INTEGER NOT NULL DEFAULT 1,
        confidence REAL NOT NULL DEFAULT 0,
        data_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS debug_snapshots (
        id TEXT PRIMARY KEY,
        session_id TEXT,
        type TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at INTEGER NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rp_messages_session_turn
        ON rp_messages(session_id, turn_number)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memories_session_type
        ON memories(session_id, type)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memories_session_updated
        ON memories(session_id, updated_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_memories_session_importance
        ON memories(session_id, importance, updated_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_lorebook_entries_lorebook_id
        ON lorebook_entries(lorebook_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_lorebooks_session_id
        ON lorebooks(session_id)
    """,
)


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connection() as conn:
            try:
                conn.execute("BEGIN")
                for statement in SCHEMA_STATEMENTS:
                    conn.execute(statement)
                conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, now_ts()),
                )
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def fetch_table_names(self) -> set[str]:
        rows = self.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {row["name"] for row in rows}

    def get_schema_version(self) -> int:
        row = self.fetch_one("SELECT MAX(version) AS version FROM schema_migrations")
        if row is None:
            return 0
        return int(row["version"] or 0)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self.connection() as conn:
            conn.execute(sql, tuple(params))
            conn.commit()

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute(sql, tuple(params)).fetchone()

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return list(conn.execute(sql, tuple(params)).fetchall())


def now_ts() -> int:
    return int(time.time())


def dumps_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def loads_json(raw: str | None) -> Any:
    if raw is None:
        return {}
    if raw == "":
        raise ValueError("JSON value cannot be empty")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc.msg}") from exc
