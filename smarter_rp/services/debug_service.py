from __future__ import annotations

import re
import sqlite3
import time
from typing import Any, cast

from smarter_rp.ids import make_stable_id
from smarter_rp.models import DebugSnapshot
from smarter_rp.storage import Storage, now_ts

_REDACTED = "[REDACTED]"

_SECRET_KEYS = r"token|api[_-]?key|apikey|access_token|refresh_token|id_token|auth_token|authorization"
_UNQUOTED_SECRET_KEYS = r"token|api[_-]?key|apikey|access_token|refresh_token|id_token|auth_token"
_QUOTED_KEY_VALUE_PATTERN = re.compile(
    rf"(\b|[\"'])({_SECRET_KEYS})([\"']?\s*[:=]\s*)([\"'])([^\"']*)([\"'])",
    re.IGNORECASE,
)
_UNQUOTED_AUTHORIZATION_PATTERN = re.compile(
    r"(\b|[\"'])(authorization)([\"']?\s*[:=]\s*)(?!\s*[\"'])([^\n\r,;&}]+)",
    re.IGNORECASE,
)
_UNQUOTED_KEY_VALUE_PATTERN = re.compile(
    rf"(\b|[\"'])({_UNQUOTED_SECRET_KEYS})([\"']?\s*[:=]\s*)([^\s,;&\"'}}]+)",
    re.IGNORECASE,
)
_AUTH_BEARER_PATTERN = re.compile(
    r"\b(Authorization\s*:\s*Bearer\s+)([^\s,;&]+)",
    re.IGNORECASE,
)
_STANDALONE_SK_PATTERN = re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]*")


def redact_sensitive_text(text: str) -> str:
    redacted = _QUOTED_KEY_VALUE_PATTERN.sub(r"\1\2\3\4" + _REDACTED + r"\6", text)
    redacted = _UNQUOTED_AUTHORIZATION_PATTERN.sub(r"\1\2\3" + _REDACTED, redacted)
    redacted = _UNQUOTED_KEY_VALUE_PATTERN.sub(r"\1\2\3" + _REDACTED, redacted)
    redacted = _AUTH_BEARER_PATTERN.sub(r"\1" + _REDACTED, redacted)
    return _STANDALONE_SK_PATTERN.sub(_REDACTED, redacted)


class DebugService:
    def __init__(self, storage: Storage):
        self.storage = storage

    def save_snapshot(
        self,
        session_id: str | None,
        snapshot_type: str,
        content: str,
    ) -> DebugSnapshot:
        timestamp = now_ts()
        redacted_content = redact_sensitive_text(content)
        snapshot = DebugSnapshot(
            id=self._make_snapshot_id(
                session_id,
                snapshot_type,
                timestamp,
                redacted_content,
            ),
            session_id=session_id,
            type=cast(DebugSnapshot.__annotations__["type"], snapshot_type),
            content=redacted_content,
            created_at=timestamp,
        )
        self.storage.execute(
            """
            INSERT INTO debug_snapshots(id, session_id, type, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                snapshot.id,
                snapshot.session_id,
                snapshot.type,
                snapshot.content,
                snapshot.created_at,
            ),
        )
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> DebugSnapshot | None:
        row = self.storage.fetch_one(
            "SELECT * FROM debug_snapshots WHERE id = ?",
            (snapshot_id,),
        )
        if row is None:
            return None
        return self._from_row(row)

    def list_snapshots(
        self,
        limit: int = 20,
        session_id: str | None = None,
        snapshot_type: str | None = None,
    ) -> list[DebugSnapshot]:
        safe_limit = max(1, min(int(limit), 100))
        clauses: list[str] = []
        params: list[Any] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if snapshot_type is not None:
            clauses.append("type = ?")
            params.append(snapshot_type)

        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.storage.fetch_all(
            f"""
            SELECT * FROM debug_snapshots
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (*params, safe_limit),
        )
        return [self._from_row(row) for row in rows]

    def _make_snapshot_id(
        self,
        session_id: str | None,
        snapshot_type: str,
        timestamp: int,
        content: str,
    ) -> str:
        parts: tuple[Any, ...] = (
            session_id or "global",
            snapshot_type,
            timestamp,
            time.time_ns(),
            content[:64],
            len(content),
        )
        return make_stable_id("debug", *parts)

    def _from_row(self, row: sqlite3.Row) -> DebugSnapshot:
        return DebugSnapshot(
            id=row["id"],
            session_id=row["session_id"],
            type=cast(DebugSnapshot.__annotations__["type"], row["type"]),
            content=row["content"],
            created_at=int(row["created_at"]),
        )
