from __future__ import annotations

from smarter_rp.storage import Storage, now_ts


class SessionStateService:
    def __init__(self, storage: Storage, default_enabled: bool = True):
        self._storage = storage
        self._default_enabled = default_enabled

    def is_enabled(self, session_id: str) -> bool:
        row = self._storage.fetch_one(
            "SELECT enabled FROM session_overrides WHERE session_id = ?",
            (session_id,),
        )
        if row is None:
            return self._default_enabled
        return bool(row["enabled"])

    def disable(self, session_id: str) -> None:
        self._set_enabled(session_id, False)

    def enable(self, session_id: str) -> None:
        self._set_enabled(session_id, True)

    def _set_enabled(self, session_id: str, enabled: bool) -> None:
        self._storage.execute(
            """
            INSERT INTO session_overrides(session_id, enabled, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (session_id, int(enabled), now_ts()),
        )
