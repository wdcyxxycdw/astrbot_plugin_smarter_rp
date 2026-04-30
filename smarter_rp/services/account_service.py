from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from smarter_rp.ids import make_stable_id
from smarter_rp.models import AccountProfile
from smarter_rp.storage import Storage, dumps_json, loads_json, now_ts


@dataclass(frozen=True, slots=True)
class AccountIdentity:
    adapter_name: str
    platform: str
    account_id: str
    display_name: str = ""


_MISSING = object()


class AccountService:
    def __init__(self, storage: Storage):
        self.storage = storage

    def extract_identity(self, event: object) -> AccountIdentity:
        message_obj = self._safe_getattr(event, "message_obj")
        origin = self._string_value(self._safe_getattr(event, "unified_msg_origin"))
        origin_parts = origin.split(":") if origin else []

        adapter_name = self._first_string(
            self._safe_getattr(event, "adapter_name"),
            self._safe_getattr(message_obj, "adapter_name"),
            origin_parts[0] if len(origin_parts) > 0 else _MISSING,
            "unknown",
        )
        platform = self._first_string(
            self._safe_getattr(event, "platform"),
            self._safe_getattr(message_obj, "platform"),
            self._safe_getattr(event, "type"),
            "unknown",
        )
        account_id = self._first_string(
            self._safe_getattr(event, "account_id"),
            self._safe_getattr(event, "self_id"),
            self._safe_getattr(event, "bot_id"),
            self._safe_getattr(message_obj, "self_id"),
            self._safe_getattr(message_obj, "bot_id"),
            origin_parts[1] if len(origin_parts) > 1 else _MISSING,
            "unknown",
        )
        display_name = self._first_string(
            self._safe_getattr(event, "display_name"),
            self._safe_getattr(event, "nickname"),
            self._safe_getattr(message_obj, "display_name"),
            "",
        )
        return AccountIdentity(adapter_name, platform, account_id, display_name)

    def get_or_create(self, identity: AccountIdentity) -> AccountProfile:
        row = self.storage.fetch_one(
            """
            SELECT * FROM account_profiles
            WHERE adapter_name = ? AND platform = ? AND account_id = ?
            """,
            (identity.adapter_name, identity.platform, identity.account_id),
        )
        if row is not None:
            return self._from_row(row)

        timestamp = now_ts()
        profile = AccountProfile(
            id=make_stable_id(
                "account",
                identity.adapter_name,
                identity.platform,
                identity.account_id,
            ),
            adapter_name=identity.adapter_name,
            platform=identity.platform,
            account_id=identity.account_id,
            display_name=identity.display_name,
            default_enabled=True,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.storage.execute(
            """
            INSERT INTO account_profiles(
                id,
                adapter_name,
                platform,
                account_id,
                display_name,
                default_enabled,
                default_character_id,
                data_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.id,
                profile.adapter_name,
                profile.platform,
                profile.account_id,
                profile.display_name,
                int(profile.default_enabled),
                profile.default_character_id,
                self._to_json(profile),
                profile.created_at,
                profile.updated_at,
            ),
        )
        return profile

    def get_by_id(self, profile_id: str) -> AccountProfile:
        row = self.storage.fetch_one(
            "SELECT * FROM account_profiles WHERE id = ?",
            (profile_id,),
        )
        if row is None:
            raise KeyError(profile_id)
        return self._from_row(row)

    def list_profiles(self) -> list[AccountProfile]:
        rows = self.storage.fetch_all(
            "SELECT * FROM account_profiles ORDER BY created_at, id"
        )
        return [self._from_row(row) for row in rows]

    def update_profile(
        self,
        profile_id: str,
        *,
        default_enabled: bool | None = None,
        default_character_id: str | None | object = _MISSING,
        default_lorebook_ids: list[str] | None = None,
        display_name: str | None = None,
    ) -> AccountProfile:
        profile = self.get_by_id(profile_id)
        if default_enabled is not None:
            profile.default_enabled = default_enabled
        if default_character_id is not _MISSING:
            profile.default_character_id = default_character_id
        if default_lorebook_ids is not None:
            profile.default_lorebook_ids = list(default_lorebook_ids)
        if display_name is not None:
            profile.display_name = display_name
        profile.updated_at = now_ts()

        self.storage.execute(
            """
            UPDATE account_profiles
            SET display_name = ?,
                default_enabled = ?,
                default_character_id = ?,
                data_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                profile.display_name,
                int(profile.default_enabled),
                profile.default_character_id,
                self._to_json(profile),
                profile.updated_at,
                profile.id,
            ),
        )
        return profile

    def _from_row(self, row: sqlite3.Row) -> AccountProfile:
        data = loads_json(row["data_json"])
        if not isinstance(data, dict):
            data = {}

        return AccountProfile(
            id=row["id"],
            adapter_name=row["adapter_name"],
            platform=row["platform"],
            account_id=row["account_id"],
            display_name=row["display_name"],
            default_character_id=row["default_character_id"],
            default_lorebook_ids=self._string_list_value(data.get("default_lorebook_ids")),
            default_enabled=bool(row["default_enabled"]),
            prompt_overrides=self._dict_value(data.get("prompt_overrides")),
            metadata=self._dict_value(data.get("metadata")),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    def _to_json(self, profile: AccountProfile) -> str:
        return dumps_json(
            {
                "default_lorebook_ids": profile.default_lorebook_ids,
                "prompt_overrides": profile.prompt_overrides,
                "metadata": profile.metadata,
            }
        )

    def _safe_getattr(self, target: object, name: str) -> Any:
        try:
            return getattr(target, name)
        except Exception:
            return _MISSING

    def _first_string(self, *values: object) -> str:
        for value in values:
            text = self._string_value(value)
            if text != "":
                return text
        return ""

    def _string_value(self, value: object) -> str:
        if value is _MISSING or value is None:
            return ""
        return str(value)

    def _string_list_value(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

    def _dict_value(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}
