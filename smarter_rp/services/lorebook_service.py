from __future__ import annotations

import sqlite3
import uuid
from dataclasses import asdict
from typing import Any
from smarter_rp.models import Lorebook, LorebookEntry
from smarter_rp.services.account_service import AccountService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage, dumps_json, loads_json, now_ts


LOREBOOK_SCOPES = {"global", "session"}
LOREBOOK_POSITIONS = {
    "before_character",
    "after_character",
    "before_history",
    "in_history",
    "after_history",
    "post_history",
}
IMMUTABLE_LOREBOOK_FIELDS = {"id", "created_at", "updated_at"}
IMMUTABLE_ENTRY_FIELDS = {"id", "lorebook_id", "created_at", "updated_at"}


class LorebookService:
    def __init__(self, storage: Storage):
        self.storage = storage

    def create_lorebook(self, lorebook: Lorebook) -> Lorebook:
        if not lorebook.id:
            lorebook.id = f"lorebook_{uuid.uuid4().hex}"
        return self._save_lorebook(lorebook)

    def get_lorebook(self, lorebook_id: str) -> Lorebook | None:
        row = self.storage.fetch_one("SELECT * FROM lorebooks WHERE id = ?", (lorebook_id,))
        if row is None:
            return None
        return self._lorebook_from_row(row)

    def list_lorebooks(self) -> list[Lorebook]:
        rows = self.storage.fetch_all("SELECT * FROM lorebooks ORDER BY created_at, rowid")
        return [self._lorebook_from_row(row) for row in rows]

    def update_lorebook(self, lorebook_id: str, **fields: Any) -> Lorebook:
        lorebook = self.get_lorebook(lorebook_id)
        if lorebook is None:
            raise KeyError(lorebook_id)
        for name, value in fields.items():
            if name in IMMUTABLE_LOREBOOK_FIELDS:
                raise ValueError(f"Immutable lorebook field: {name}")
            if not hasattr(lorebook, name):
                raise ValueError(f"Unknown lorebook field: {name}")
            setattr(lorebook, name, value)
        return self._save_lorebook(lorebook)

    def delete_lorebook(self, lorebook_id: str) -> None:
        self.storage.execute("DELETE FROM lorebook_entries WHERE lorebook_id = ?", (lorebook_id,))
        self.storage.execute("DELETE FROM lorebooks WHERE id = ?", (lorebook_id,))

    def create_entry(self, entry: LorebookEntry) -> LorebookEntry:
        if self.get_lorebook(entry.lorebook_id) is None:
            raise KeyError(entry.lorebook_id)
        if not entry.id:
            entry.id = f"entry_{uuid.uuid4().hex}"
        return self._save_entry(entry)

    def get_entry(self, entry_id: str) -> LorebookEntry | None:
        row = self.storage.fetch_one("SELECT * FROM lorebook_entries WHERE id = ?", (entry_id,))
        if row is None:
            return None
        return self._entry_from_row(row)

    def list_entries(self, lorebook_id: str) -> list[LorebookEntry]:
        rows = self.storage.fetch_all(
            "SELECT * FROM lorebook_entries WHERE lorebook_id = ? ORDER BY created_at, rowid",
            (lorebook_id,),
        )
        return [self._entry_from_row(row) for row in rows]

    def update_entry(self, entry_id: str, **fields: Any) -> LorebookEntry:
        entry = self.get_entry(entry_id)
        if entry is None:
            raise KeyError(entry_id)
        for name, value in fields.items():
            if name in IMMUTABLE_ENTRY_FIELDS:
                raise ValueError(f"Immutable lorebook entry field: {name}")
            if not hasattr(entry, name):
                raise ValueError(f"Unknown lorebook entry field: {name}")
            setattr(entry, name, value)
        return self._save_entry(entry)

    def delete_entry(self, entry_id: str) -> None:
        self.storage.execute("DELETE FROM lorebook_entries WHERE id = ?", (entry_id,))

    def set_account_lorebooks(self, account_id: str, lorebook_ids: list[str]) -> None:
        AccountService(self.storage).update_profile(account_id, default_lorebook_ids=list(lorebook_ids))

    def set_session_lorebooks(self, session_id: str, lorebook_ids: list[str]) -> None:
        SessionService(self.storage).update_session_controls(
            session_id, active_lorebook_ids=list(lorebook_ids)
        )

    def export_lorebook(self, book_id: str) -> dict[str, Any]:
        lorebook = self.get_lorebook(book_id)
        if lorebook is None:
            raise KeyError(book_id)
        return {
            "format": "smarter_rp_lorebook_v1",
            "lorebook": self.serialize_lorebook(lorebook),
            "entries": [self.serialize_entry(entry) for entry in self.list_entries(book_id)],
        }

    def import_lorebook(self, data: dict[str, Any]) -> Lorebook:
        if data.get("format") == "smarter_rp_lorebook_v1":
            return self._import_plugin_lorebook(data)
        return self._import_silly_tavern_lorebook(data)

    def serialize_lorebook(self, lorebook: Lorebook) -> dict[str, Any]:
        return asdict(lorebook)

    def serialize_entry(self, entry: LorebookEntry) -> dict[str, Any]:
        return asdict(entry)

    def _save_lorebook(self, lorebook: Lorebook) -> Lorebook:
        self._validate_lorebook(lorebook)
        existing = self.storage.fetch_one(
            "SELECT created_at FROM lorebooks WHERE id = ?", (lorebook.id,)
        )
        timestamp = now_ts()
        if existing is not None:
            lorebook.created_at = int(existing["created_at"])
        elif lorebook.created_at == 0:
            lorebook.created_at = timestamp
        lorebook.updated_at = timestamp
        self.storage.execute(
            """
            INSERT INTO lorebooks(id, name, scope, session_id, data_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                scope = excluded.scope,
                session_id = excluded.session_id,
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
            """,
            (
                lorebook.id,
                lorebook.name,
                lorebook.scope,
                lorebook.session_id,
                self._lorebook_to_json(lorebook),
                lorebook.created_at,
                lorebook.updated_at,
            ),
        )
        return lorebook

    def _save_entry(self, entry: LorebookEntry) -> LorebookEntry:
        self._validate_entry(entry)
        existing = self.storage.fetch_one(
            "SELECT created_at FROM lorebook_entries WHERE id = ?", (entry.id,)
        )
        timestamp = now_ts()
        if existing is not None:
            entry.created_at = int(existing["created_at"])
        elif entry.created_at == 0:
            entry.created_at = timestamp
        entry.updated_at = timestamp
        self.storage.execute(
            """
            INSERT INTO lorebook_entries(
                id, lorebook_id, title, enabled, data_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                lorebook_id = excluded.lorebook_id,
                title = excluded.title,
                enabled = excluded.enabled,
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
            """,
            (
                entry.id,
                entry.lorebook_id,
                entry.title,
                int(entry.enabled),
                self._entry_to_json(entry),
                entry.created_at,
                entry.updated_at,
            ),
        )
        return entry

    def _validate_lorebook(self, lorebook: Lorebook) -> None:
        if lorebook.scope not in LOREBOOK_SCOPES:
            raise ValueError(f"Invalid lorebook scope: {lorebook.scope}")
        if lorebook.scope == "session" and not lorebook.session_id:
            raise ValueError("Session-scoped lorebook requires session_id")

    def _validate_entry(self, entry: LorebookEntry) -> None:
        if entry.position not in LOREBOOK_POSITIONS:
            raise ValueError(f"Invalid lorebook entry position: {entry.position}")
        if not 0.0 <= float(entry.probability) <= 1.0:
            raise ValueError("Lorebook entry probability must be between 0.0 and 1.0")

    def _lorebook_from_row(self, row: sqlite3.Row) -> Lorebook:
        data = loads_json(row["data_json"])
        if not isinstance(data, dict):
            data = {}
        return Lorebook(
            id=row["id"],
            name=row["name"],
            description=str(data.get("description", "")),
            scope=row["scope"],
            session_id=row["session_id"],
            metadata=self._dict_value(data.get("metadata")),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    def _entry_from_row(self, row: sqlite3.Row) -> LorebookEntry:
        data = loads_json(row["data_json"])
        if not isinstance(data, dict):
            data = {}
        return LorebookEntry(
            id=row["id"],
            lorebook_id=row["lorebook_id"],
            title=row["title"],
            content=str(data.get("content", "")),
            enabled=bool(row["enabled"]),
            constant=bool(data.get("constant", False)),
            keys=self._string_list_value(data.get("keys")),
            secondary_keys=self._string_list_value(data.get("secondary_keys")),
            selective=bool(data.get("selective", False)),
            regex=bool(data.get("regex", False)),
            case_sensitive=bool(data.get("case_sensitive", False)),
            position=str(data.get("position", "before_history")),
            depth=int(data.get("depth", 0)),
            priority=int(data.get("priority", 0)),
            order=int(data.get("order", 0)),
            probability=float(data.get("probability", 1.0)),
            cooldown_turns=int(data.get("cooldown_turns", 0)),
            sticky_turns=int(data.get("sticky_turns", 0)),
            recursive=bool(data.get("recursive", False)),
            group=self._optional_string_value(data.get("group")),
            character_filter=self._string_list_value(data.get("character_filter")),
            max_injections_per_chat=self._optional_int_value(data.get("max_injections_per_chat")),
            metadata=self._dict_value(data.get("metadata")),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    def _lorebook_to_json(self, lorebook: Lorebook) -> str:
        return dumps_json({"description": lorebook.description, "metadata": lorebook.metadata})

    def _entry_to_json(self, entry: LorebookEntry) -> str:
        return dumps_json(
            {
                "content": entry.content,
                "constant": entry.constant,
                "keys": entry.keys,
                "secondary_keys": entry.secondary_keys,
                "selective": entry.selective,
                "regex": entry.regex,
                "case_sensitive": entry.case_sensitive,
                "position": entry.position,
                "depth": entry.depth,
                "priority": entry.priority,
                "order": entry.order,
                "probability": entry.probability,
                "cooldown_turns": entry.cooldown_turns,
                "sticky_turns": entry.sticky_turns,
                "recursive": entry.recursive,
                "group": entry.group,
                "character_filter": entry.character_filter,
                "max_injections_per_chat": entry.max_injections_per_chat,
                "metadata": entry.metadata,
            }
        )

    def _import_plugin_lorebook(self, data: dict[str, Any]) -> Lorebook:
        raw_book = self._dict_value(data.get("lorebook"))
        book = Lorebook(
            id=f"lorebook_{uuid.uuid4().hex}",
            name=str(raw_book.get("name", "Imported Lorebook")),
            description=str(raw_book.get("description", "")),
            scope=self._scope_value(raw_book.get("scope")),
            session_id=raw_book.get("session_id") if raw_book.get("scope") == "session" else None,
            metadata=self._dict_value(raw_book.get("metadata")),
        )
        entries = [self._plugin_entry(raw_entry, book.id) for raw_entry in self._entry_items(data.get("entries"))]
        self._validate_lorebook(book)
        for entry in entries:
            self._validate_entry(entry)
        imported = self.create_lorebook(book)
        for entry in entries:
            self.create_entry(entry)
        return imported

    def _import_silly_tavern_lorebook(self, data: dict[str, Any]) -> Lorebook:
        entries = data.get("entries")
        nested_data = data.get("data")
        if entries is None and isinstance(nested_data, dict):
            entries = nested_data.get("entries")
        book = Lorebook(
            id=f"lorebook_{uuid.uuid4().hex}",
            name=str(data.get("name") or data.get("charName") or "Imported Lorebook"),
            description=str(data.get("description", "")),
            scope="global",
        )
        book_entries = [self._silly_tavern_entry(raw_entry, book.id) for raw_entry in self._entry_items(entries)]
        self._validate_lorebook(book)
        for entry in book_entries:
            self._validate_entry(entry)
        imported = self.create_lorebook(book)
        for entry in book_entries:
            self.create_entry(entry)
        return imported

    def _plugin_entry(self, data: dict[str, Any], lorebook_id: str) -> LorebookEntry:
        return LorebookEntry(
            id="",
            lorebook_id=lorebook_id,
            title=str(data.get("title", "")),
            content=str(data.get("content", "")),
            enabled=bool(data.get("enabled", True)),
            constant=bool(data.get("constant", False)),
            keys=self._string_list_value(data.get("keys")),
            secondary_keys=self._string_list_value(data.get("secondary_keys")),
            selective=bool(data.get("selective", False)),
            regex=bool(data.get("regex", False)),
            case_sensitive=bool(data.get("case_sensitive", False)),
            position=self._position_value(data.get("position")),
            depth=int(data.get("depth", 0)),
            priority=int(data.get("priority", 0)),
            order=int(data.get("order", 0)),
            probability=float(data.get("probability", 1.0)),
            cooldown_turns=int(data.get("cooldown_turns", 0)),
            sticky_turns=int(data.get("sticky_turns", 0)),
            recursive=bool(data.get("recursive", False)),
            group=self._optional_string_value(data.get("group")),
            character_filter=self._string_list_value(data.get("character_filter")),
            max_injections_per_chat=self._optional_int_value(data.get("max_injections_per_chat")),
            metadata=self._dict_value(data.get("metadata")),
        )

    def _silly_tavern_entry(self, data: dict[str, Any], lorebook_id: str) -> LorebookEntry:
        return LorebookEntry(
            id="",
            lorebook_id=lorebook_id,
            title=str(data.get("comment") or data.get("title") or data.get("uid") or "Entry"),
            content=str(data.get("content", "")),
            enabled=not bool(data.get("disable", False)),
            constant=bool(data.get("constant", False)),
            keys=self._string_list_value(data.get("key")),
            secondary_keys=self._string_list_value(data.get("keysecondary")),
            selective=bool(data.get("selective", False)),
            regex=bool(data.get("regex", False)),
            case_sensitive=bool(data.get("case_sensitive", False)),
            position=self._position_value(data.get("position")),
            depth=int(data.get("depth", 0)),
            priority=int(data.get("priority", data.get("order", 0))),
            order=int(data.get("order", 0)),
            probability=self._silly_probability(data.get("probability", 100)),
            metadata={"source": "silly_tavern"},
        )

    def _entry_items(self, entries: Any) -> list[dict[str, Any]]:
        if isinstance(entries, dict):
            return [item for item in entries.values() if isinstance(item, dict)]
        if isinstance(entries, list):
            return [item for item in entries if isinstance(item, dict)]
        return []

    def _scope_value(self, value: Any) -> str:
        text = str(value or "global")
        if text in LOREBOOK_SCOPES:
            return text
        return "global"

    def _position_value(self, value: Any) -> str:
        text = str(value or "before_history")
        if text in LOREBOOK_POSITIONS:
            return text
        return "before_history"

    def _silly_probability(self, value: Any) -> float:
        probability = float(value)
        if probability > 1.0:
            probability = probability / 100.0
        if not 0.0 <= probability <= 1.0:
            raise ValueError("Lorebook entry probability must be between 0.0 and 1.0")
        return probability

    def _dict_value(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    def _string_list_value(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

    def _optional_string_value(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def _optional_int_value(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(value)
