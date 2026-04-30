import math
import sqlite3
from pathlib import Path

import pytest

from smarter_rp.storage import Storage, dumps_json, loads_json


def test_storage_initializes_database_and_tables(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()

    tables = storage.fetch_table_names()

    assert "schema_migrations" in tables
    assert "account_profiles" in tables
    assert "rp_sessions" in tables
    assert "debug_snapshots" in tables


def test_storage_initialize_is_idempotent(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")

    storage.initialize()
    storage.initialize()

    version = storage.get_schema_version()
    assert version == 1


def test_storage_initialize_does_not_duplicate_migration_rows(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")

    storage.initialize()
    storage.initialize()

    row = storage.fetch_one("SELECT COUNT(*) AS count FROM schema_migrations")
    assert row is not None
    assert row["count"] == 1


class FailingDdlConnection(sqlite3.Connection):
    ddl_count = 0

    def execute(self, sql: str, parameters=(), /):
        if sql.lstrip().upper().startswith("CREATE TABLE"):
            self.ddl_count += 1
            if self.ddl_count == 2:
                raise sqlite3.OperationalError("simulated DDL failure")
        return super().execute(sql, parameters)


class FailingDdlStorage(Storage):
    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, factory=FailingDdlConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def test_initialize_rolls_back_partial_schema_on_migration_failure(tmp_path: Path):
    db_path = tmp_path / "smarter_rp.db"
    storage = FailingDdlStorage(db_path)

    with pytest.raises(sqlite3.OperationalError, match="simulated DDL failure"):
        storage.initialize()

    table_names = storage.fetch_table_names()
    assert "schema_migrations" not in table_names
    assert "account_profiles" not in table_names

    clean_storage = Storage(db_path)
    clean_storage.initialize()

    row = clean_storage.fetch_one("SELECT COUNT(*) AS count FROM schema_migrations")
    assert row is not None
    assert row["count"] == 1


def test_execute_fetch_one_and_fetch_all_basic_behavior(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()

    storage.execute(
        """
        INSERT INTO characters(id, name, data_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("char-1", "Alice", "{}", 1, 1),
    )
    storage.execute(
        """
        INSERT INTO characters(id, name, data_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("char-2", "Bob", "{}", 2, 2),
    )

    row = storage.fetch_one("SELECT name FROM characters WHERE id = ?", ("char-1",))
    rows = storage.fetch_all("SELECT name FROM characters ORDER BY id")

    assert row is not None
    assert row["name"] == "Alice"
    assert [item["name"] for item in rows] == ["Alice", "Bob"]


def test_dumps_json_rejects_nan():
    with pytest.raises(ValueError, match="Out of range float"):
        dumps_json({"score": math.nan})


def test_loads_json_parses_arrays_and_chinese_text():
    assert loads_json('["你好", {"角色": "猫"}]') == ["你好", {"角色": "猫"}]


def test_loads_json_none_returns_empty_dict():
    assert loads_json(None) == {}


def test_loads_json_empty_string_raises_value_error():
    with pytest.raises(ValueError, match="empty"):
        loads_json("")


def test_loads_json_invalid_json_raises_value_error():
    with pytest.raises(ValueError, match="Invalid JSON"):
        loads_json("{bad")


def test_initialize_creates_message_lookup_index(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()

    row = storage.fetch_one(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'index' AND name = 'idx_rp_messages_session_turn'
        """
    )

    assert row is not None
