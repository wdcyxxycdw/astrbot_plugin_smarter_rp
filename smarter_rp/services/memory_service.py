from __future__ import annotations

import sqlite3
from typing import Any, Literal

from smarter_rp.ids import make_stable_id
from smarter_rp.models import Memory, RpSession
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage, dumps_json, loads_json, now_ts


class MemoryService:
    def __init__(self, storage: Storage, sessions: SessionService):
        self.storage = storage
        self.sessions = sessions

    def create_event_memory(
        self,
        session_id: str,
        content: str,
        importance: int,
        confidence: float,
        source_message_ids: list[str] | None = None,
        turn_range: tuple[int, int] | list[int] | None = None,
        embedding_id: str | None = None,
        embedding_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Memory:
        self.sessions.get_by_id(session_id)
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("content cannot be empty")

        source_ids = self._list_value(source_message_ids)
        parsed_turn_range = self._turn_range_value(turn_range)
        memory_id = make_stable_id("memory", session_id, "event", clean_content, source_ids, parsed_turn_range)
        existing = self.get_memory(memory_id)
        if existing is not None:
            return self.update_memory(
                memory_id,
                importance=importance,
                confidence=confidence,
                embedding_id=embedding_id,
                embedding_version=embedding_version,
                metadata={**existing.metadata, **self._dict_value(metadata)},
            )

        timestamp = now_ts()
        memory = Memory(
            id=memory_id,
            session_id=session_id,
            type="event",
            content=clean_content,
            importance=self._clamp_int(importance, 1, 10),
            confidence=self._clamp_float(confidence, 0.0, 1.0),
            source_message_ids=source_ids,
            turn_range=parsed_turn_range,
            embedding_id=embedding_id,
            embedding_version=embedding_version,
            metadata=self._dict_value(metadata),
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.storage.execute(
            """
            INSERT INTO memories(
                id,
                session_id,
                type,
                content,
                importance,
                confidence,
                data_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.session_id,
                memory.type,
                memory.content,
                memory.importance,
                memory.confidence,
                self._to_json(memory),
                memory.created_at,
                memory.updated_at,
            ),
        )
        return memory

    def list_memories(self, session_id: str, limit: int | None = 100) -> list[Memory]:
        self.sessions.get_by_id(session_id)
        params: list[Any] = [session_id]
        sql = "SELECT * FROM memories WHERE session_id = ? ORDER BY created_at, id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(1, int(limit)))
        rows = self.storage.fetch_all(sql, params)
        return [self._from_row(row) for row in rows]

    def get_memory(self, memory_id: str) -> Memory | None:
        row = self.storage.fetch_one("SELECT * FROM memories WHERE id = ?", (memory_id,))
        if row is None:
            return None
        return self._from_row(row)

    def update_memory(self, memory_id: str, **fields: Any) -> Memory:
        memory = self.get_memory(memory_id)
        if memory is None:
            raise KeyError(memory_id)
        for name, value in fields.items():
            if name in {"id", "session_id", "type", "created_at", "updated_at"}:
                raise ValueError(f"Immutable memory field: {name}")
            if not hasattr(memory, name):
                raise ValueError(f"Unknown memory field: {name}")
            if name == "content":
                value = str(value).strip()
                if not value:
                    raise ValueError("content cannot be empty")
            elif name == "importance":
                value = self._clamp_int(value, 1, 10)
            elif name == "confidence":
                value = self._clamp_float(value, 0.0, 1.0)
            elif name == "source_message_ids":
                value = self._list_value(value)
            elif name == "turn_range":
                value = self._turn_range_value(value)
            elif name == "metadata":
                value = self._dict_value(value)
            elif name in {"embedding_id", "embedding_version"}:
                value = self._optional_str(value)
            setattr(memory, name, value)
        memory.updated_at = now_ts()
        self.storage.execute(
            """
            UPDATE memories
            SET content = ?, importance = ?, confidence = ?, data_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                memory.content,
                memory.importance,
                memory.confidence,
                self._to_json(memory),
                memory.updated_at,
                memory.id,
            ),
        )
        return memory

    def delete_memory(self, memory_id: str) -> bool:
        with self.storage.connection() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0

    def clear_session_memory(self, session_id: str) -> RpSession:
        session = self.sessions.get_by_id(session_id)
        self.storage.execute("DELETE FROM memories WHERE session_id = ?", (session_id,))
        session.summary = ""
        session.state = {}
        session.last_memory_hits = []
        session.memory_processed_turn = 0
        return self.sessions.save_session_state(session)

    def update_session_memory_state(self, session_id: str, summary: str, state: dict[str, Any]) -> RpSession:
        session = self.sessions.get_by_id(session_id)
        session.summary = summary
        session.state = self._dict_value(state)
        return self.sessions.save_session_state(session)

    def _from_row(self, row: sqlite3.Row) -> Memory:
        data = loads_json(row["data_json"])
        if not isinstance(data, dict):
            data = {}

        memory_type: Literal["event", "state_snapshot", "note"] = "event"
        if row["type"] in ("event", "state_snapshot", "note"):
            memory_type = row["type"]

        return Memory(
            id=row["id"],
            session_id=row["session_id"],
            type=memory_type,
            content=row["content"],
            importance=int(row["importance"]),
            confidence=float(row["confidence"]),
            source_message_ids=self._list_value(data.get("source_message_ids")),
            turn_range=self._turn_range_value(data.get("turn_range")),
            embedding_id=self._optional_str(data.get("embedding_id")),
            embedding_version=self._optional_str(data.get("embedding_version")),
            metadata=self._dict_value(data.get("metadata")),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    def _to_json(self, memory: Memory) -> str:
        return dumps_json(
            {
                "source_message_ids": memory.source_message_ids,
                "turn_range": list(memory.turn_range) if memory.turn_range is not None else None,
                "embedding_id": memory.embedding_id,
                "embedding_version": memory.embedding_version,
                "metadata": memory.metadata,
            }
        )

    def _list_value(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        return []

    def _dict_value(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    def _turn_range_value(self, value: Any) -> tuple[int, int] | None:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                return (int(value[0]), int(value[1]))
            except (TypeError, ValueError):
                return None
        return None

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def _clamp_int(self, value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, int(value)))

    def _clamp_float(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, float(value)))
