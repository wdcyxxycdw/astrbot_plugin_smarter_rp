from __future__ import annotations

from dataclasses import dataclass

from smarter_rp.storage import Storage, now_ts


@dataclass(frozen=True)
class AccountBinding:
    adapter: str
    platform: str
    account_id: str
    character_id: str
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class ChatBinding:
    adapter: str
    platform: str
    account_id: str
    session_id: str
    character_id: str
    chat_id: str
    created_at: int
    updated_at: int


def _normalize(value: object) -> str:
    return str(value).strip()


class TavernBindingService:
    def __init__(self, storage: Storage):
        self.storage = storage

    def set_account_binding(self, adapter: object, platform: object, account_id: object, character_id: object) -> AccountBinding:
        normalized_adapter = _normalize(adapter)
        normalized_platform = _normalize(platform)
        normalized_account_id = _normalize(account_id)
        normalized_character_id = _normalize(character_id)
        timestamp = now_ts()
        self.storage.execute(
            """
            INSERT INTO account_bindings(adapter, platform, account_id, character_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(adapter, platform, account_id) DO UPDATE SET
                character_id = excluded.character_id,
                updated_at = excluded.updated_at
            """,
            (normalized_adapter, normalized_platform, normalized_account_id, normalized_character_id, timestamp, timestamp),
        )
        binding = self.get_account_binding(normalized_adapter, normalized_platform, normalized_account_id)
        if binding is None:
            raise RuntimeError("account binding was not saved")
        return binding

    def get_account_binding(self, adapter: object, platform: object, account_id: object) -> AccountBinding | None:
        row = self.storage.fetch_one(
            """
            SELECT adapter, platform, account_id, character_id, created_at, updated_at
            FROM account_bindings
            WHERE adapter = ? AND platform = ? AND account_id = ?
            """,
            (_normalize(adapter), _normalize(platform), _normalize(account_id)),
        )
        if row is None:
            return None
        return AccountBinding(**dict(row))

    def delete_account_binding(self, adapter: object, platform: object, account_id: object) -> None:
        self.storage.execute(
            "DELETE FROM account_bindings WHERE adapter = ? AND platform = ? AND account_id = ?",
            (_normalize(adapter), _normalize(platform), _normalize(account_id)),
        )

    def list_account_bindings(self) -> list[AccountBinding]:
        rows = self.storage.fetch_all(
            """
            SELECT adapter, platform, account_id, character_id, created_at, updated_at
            FROM account_bindings
            ORDER BY adapter, platform, account_id
            """
        )
        return [AccountBinding(**dict(row)) for row in rows]

    def set_chat_binding(
        self,
        adapter: object,
        platform: object,
        account_id: object,
        session_id: object,
        character_id: object,
        chat_id: object,
    ) -> ChatBinding:
        normalized_adapter = _normalize(adapter)
        normalized_platform = _normalize(platform)
        normalized_account_id = _normalize(account_id)
        normalized_session_id = _normalize(session_id)
        normalized_character_id = _normalize(character_id)
        normalized_chat_id = _normalize(chat_id)
        timestamp = now_ts()
        self.storage.execute(
            """
            INSERT INTO chat_bindings(
                adapter, platform, account_id, session_id, character_id, chat_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(adapter, platform, account_id, session_id) DO UPDATE SET
                character_id = excluded.character_id,
                chat_id = excluded.chat_id,
                updated_at = excluded.updated_at
            """,
            (
                normalized_adapter,
                normalized_platform,
                normalized_account_id,
                normalized_session_id,
                normalized_character_id,
                normalized_chat_id,
                timestamp,
                timestamp,
            ),
        )
        binding = self.get_chat_binding(normalized_adapter, normalized_platform, normalized_account_id, normalized_session_id)
        if binding is None:
            raise RuntimeError("chat binding was not saved")
        return binding

    def get_chat_binding(
        self, adapter: object, platform: object, account_id: object, session_id: object
    ) -> ChatBinding | None:
        row = self.storage.fetch_one(
            """
            SELECT adapter, platform, account_id, session_id, character_id, chat_id, created_at, updated_at
            FROM chat_bindings
            WHERE adapter = ? AND platform = ? AND account_id = ? AND session_id = ?
            """,
            (_normalize(adapter), _normalize(platform), _normalize(account_id), _normalize(session_id)),
        )
        if row is None:
            return None
        return ChatBinding(**dict(row))

    def delete_chat_binding(self, adapter: object, platform: object, account_id: object, session_id: object) -> None:
        self.storage.execute(
            "DELETE FROM chat_bindings WHERE adapter = ? AND platform = ? AND account_id = ? AND session_id = ?",
            (_normalize(adapter), _normalize(platform), _normalize(account_id), _normalize(session_id)),
        )

    def list_chat_bindings(self) -> list[ChatBinding]:
        rows = self.storage.fetch_all(
            """
            SELECT adapter, platform, account_id, session_id, character_id, chat_id, created_at, updated_at
            FROM chat_bindings
            ORDER BY adapter, platform, account_id, session_id
            """
        )
        return [ChatBinding(**dict(row)) for row in rows]
