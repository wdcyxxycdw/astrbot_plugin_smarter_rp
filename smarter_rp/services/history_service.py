from __future__ import annotations

import sqlite3
from typing import Any, Literal

from smarter_rp.ids import make_stable_id
from smarter_rp.models import RpMessage
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage, dumps_json, loads_json, now_ts


class HistoryService:
    def __init__(self, storage: Storage, sessions: SessionService, max_history_messages: int = 40):
        self.storage = storage
        self.sessions = sessions
        self.max_history_messages = max(1, int(max_history_messages))

    def append_message(
        self,
        session_id: str,
        *,
        role: Literal["user", "assistant", "system"],
        speaker: str,
        content: str,
        visible: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> RpMessage:
        session = self.sessions.get_by_id(session_id)
        turn_number = session.turn_count
        if role == "user":
            turn_number += 1

        base_timestamp = now_ts()
        existing_count = self._message_count(session_id)
        timestamp = base_timestamp * 1_000_000 + existing_count
        message = RpMessage(
            id=make_stable_id(
                "message",
                session_id,
                role,
                speaker,
                content,
                timestamp,
                existing_count,
            ),
            session_id=session_id,
            role=role,
            speaker=speaker,
            content=content,
            visible=visible,
            turn_number=turn_number,
            metadata=dict(metadata or {}),
            created_at=timestamp,
        )
        self.storage.execute(
            """
            INSERT INTO rp_messages(
                id, session_id, role, speaker, content, visible,
                turn_number, created_at, data_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.session_id,
                message.role,
                message.speaker,
                message.content,
                int(message.visible),
                message.turn_number,
                message.created_at,
                dumps_json({"metadata": message.metadata}),
            ),
        )
        self.trim_history(session_id)
        self.refresh_session_recent(session_id)
        return message

    def list_messages(
        self,
        session_id: str,
        limit: int | None = None,
        visible_only: bool = True,
    ) -> list[RpMessage]:
        params: list[Any] = [session_id]
        where = "session_id = ?"
        if visible_only:
            where += " AND visible = 1"
        sql = f"SELECT * FROM rp_messages WHERE {where} ORDER BY turn_number, created_at, id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(1, int(limit)))
        return [self._from_row(row) for row in self.storage.fetch_all(sql, params)]

    def clear_history(self, session_id: str) -> None:
        self.storage.execute("DELETE FROM rp_messages WHERE session_id = ?", (session_id,))
        self.refresh_session_recent(session_id)

    def undo_latest_turn(self, session_id: str) -> list[RpMessage]:
        row = self.storage.fetch_one(
            "SELECT MAX(turn_number) AS turn_number FROM rp_messages WHERE session_id = ? AND visible = 1",
            (session_id,),
        )
        if row is None or row["turn_number"] is None:
            return []

        turn_number = int(row["turn_number"])
        removed = [
            self._from_row(message_row)
            for message_row in self.storage.fetch_all(
                """
                SELECT * FROM rp_messages
                WHERE session_id = ? AND turn_number = ? AND visible = 1
                ORDER BY turn_number, created_at, id
                """,
                (session_id, turn_number),
            )
        ]
        self.storage.execute(
            "DELETE FROM rp_messages WHERE session_id = ? AND turn_number = ? AND visible = 1",
            (session_id, turn_number),
        )
        self.refresh_session_recent(session_id)
        return removed

    def trim_history(self, session_id: str) -> None:
        rows = self.storage.fetch_all(
            """
            SELECT id FROM rp_messages
            WHERE session_id = ? AND visible = 1
            ORDER BY turn_number DESC, created_at DESC, id DESC
            """,
            (session_id,),
        )
        if len(rows) <= self.max_history_messages:
            return

        keep_ids = {row["id"] for row in rows[: self.max_history_messages]}
        for row in rows:
            if row["id"] not in keep_ids:
                self.storage.execute("DELETE FROM rp_messages WHERE id = ?", (row["id"],))

    def refresh_session_recent(self, session_id: str) -> None:
        session = self.sessions.get_by_id(session_id)
        messages = self.list_messages(session_id)
        recent = messages[-self.max_history_messages :]
        session.recent_messages = [
            {
                "id": message.id,
                "role": message.role,
                "speaker": message.speaker,
                "content": message.content,
                "turn_number": message.turn_number,
            }
            for message in recent
        ]
        session.turn_count = max((message.turn_number for message in messages), default=0)
        self.sessions.save_session_state(session)

    def _message_count(self, session_id: str) -> int:
        row = self.storage.fetch_one(
            "SELECT COUNT(*) AS count FROM rp_messages WHERE session_id = ?",
            (session_id,),
        )
        if row is None:
            return 0
        return int(row["count"])

    def _from_row(self, row: sqlite3.Row) -> RpMessage:
        data = loads_json(row["data_json"])
        if not isinstance(data, dict):
            data = {}
        metadata = data.get("metadata")
        return RpMessage(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            speaker=row["speaker"],
            content=row["content"],
            visible=bool(row["visible"]),
            turn_number=int(row["turn_number"]),
            metadata=metadata if isinstance(metadata, dict) else {},
            created_at=int(row["created_at"]),
        )
