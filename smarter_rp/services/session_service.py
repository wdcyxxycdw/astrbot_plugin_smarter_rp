from __future__ import annotations

import sqlite3
from typing import Any

from smarter_rp.ids import make_stable_id
from smarter_rp.models import RpSession
from smarter_rp.storage import Storage, dumps_json, loads_json, now_ts


_MISSING = object()


class SessionService:
    def __init__(self, storage: Storage):
        self.storage = storage

    def get_or_create(self, unified_msg_origin: str, account_profile_id: str | None) -> RpSession:
        row = self.storage.fetch_one(
            "SELECT * FROM rp_sessions WHERE unified_msg_origin = ?",
            (unified_msg_origin,),
        )
        if row is not None:
            return self._from_row(row)

        timestamp = now_ts()
        session = RpSession(
            id=make_stable_id("session", unified_msg_origin),
            unified_msg_origin=unified_msg_origin,
            account_profile_id=account_profile_id,
            paused=False,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.storage.execute(
            """
            INSERT INTO rp_sessions(
                id,
                unified_msg_origin,
                account_profile_id,
                paused,
                active_character_id,
                data_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.unified_msg_origin,
                session.account_profile_id,
                int(session.paused),
                session.active_character_id,
                self._to_json(session),
                session.created_at,
                session.updated_at,
            ),
        )
        return session

    def get_by_id(self, session_id: str) -> RpSession:
        row = self.storage.fetch_one(
            "SELECT * FROM rp_sessions WHERE id = ?",
            (session_id,),
        )
        if row is None:
            raise KeyError(session_id)
        return self._from_row(row)

    def list_sessions(self) -> list[RpSession]:
        rows = self.storage.fetch_all(
            "SELECT * FROM rp_sessions ORDER BY created_at, id",
        )
        return [self._from_row(row) for row in rows]

    def update_session_controls(
        self,
        session_id: str,
        *,
        paused: bool | None = None,
        active_character_id: str | None | object = _MISSING,
        active_lorebook_ids: list[str] | None = None,
    ) -> RpSession:
        session = self.get_by_id(session_id)
        if paused is not None:
            session.paused = paused
        if active_character_id is not _MISSING:
            session.active_character_id = active_character_id
        if active_lorebook_ids is not None:
            session.active_lorebook_ids = active_lorebook_ids
        return self.save_session_state(session)

    def set_paused(self, session_id: str, paused: bool) -> RpSession:
        session = self.get_by_id(session_id)
        session.paused = paused
        return self.save_session_state(session)

    def save_session_state(self, session: RpSession) -> RpSession:
        session.updated_at = now_ts()
        self.storage.execute(
            """
            UPDATE rp_sessions
            SET paused = ?, active_character_id = ?, updated_at = ?, data_json = ?
            WHERE id = ?
            """,
            (
                int(session.paused),
                session.active_character_id,
                session.updated_at,
                self._to_json(session),
                session.id,
            ),
        )
        return session

    def _from_row(self, row: sqlite3.Row) -> RpSession:
        data = loads_json(row["data_json"])
        if not isinstance(data, dict):
            data = {}

        return RpSession(
            id=row["id"],
            unified_msg_origin=row["unified_msg_origin"],
            account_profile_id=row["account_profile_id"],
            paused=bool(row["paused"]),
            active_character_id=row["active_character_id"],
            active_lorebook_ids=self._list_value(data.get("active_lorebook_ids")),
            summary=str(data.get("summary", "")),
            state=self._dict_value(data.get("state")),
            recent_messages=self._list_value(data.get("recent_messages")),
            last_lore_hits=self._list_value(data.get("last_lore_hits")),
            last_memory_hits=self._list_value(data.get("last_memory_hits")),
            turn_count=int(data.get("turn_count", 0)),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    def _to_json(self, session: RpSession) -> str:
        return dumps_json(
            {
                "active_lorebook_ids": session.active_lorebook_ids,
                "summary": session.summary,
                "state": session.state,
                "recent_messages": session.recent_messages,
                "last_lore_hits": session.last_lore_hits,
                "last_memory_hits": session.last_memory_hits,
                "turn_count": session.turn_count,
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
