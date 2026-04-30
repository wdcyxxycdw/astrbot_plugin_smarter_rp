from __future__ import annotations

import sqlite3
from typing import Any

from smarter_rp.ids import make_stable_id
from smarter_rp.models import AccountProfile, Character, RpSession
from smarter_rp.storage import Storage, dumps_json, loads_json, now_ts


FALLBACK_CHARACTER_ID = "character_builtin_fallback"
_MISSING = object()


class CharacterService:
    def __init__(self, storage: Storage):
        self.storage = storage

    def fallback_character(
        self,
        *,
        id: str = FALLBACK_CHARACTER_ID,
        name: str = "RP Assistant",
        system_prompt: str = "You are a helpful roleplay assistant.",
        description: str = "",
        personality: str = "",
        scenario: str = "",
        metadata: dict[str, Any] | None = None,
        created_at: int = 0,
        updated_at: int = 0,
    ) -> Character:
        return Character(
            id=id,
            name=name or "RP Assistant",
            system_prompt=system_prompt or "You are a helpful roleplay assistant.",
            description=description,
            personality=personality,
            scenario=scenario,
            metadata=dict(metadata or {}),
            created_at=created_at,
            updated_at=updated_at,
        )

    def save_character(self, character: Character) -> Character:
        self._ensure_character_columns()
        existing = self.storage.fetch_one(
            "SELECT created_at FROM characters WHERE id = ?",
            (character.id,),
        )
        timestamp = now_ts()
        if existing is not None:
            character.created_at = int(existing["created_at"])
        elif character.created_at == 0:
            character.created_at = timestamp
        character.updated_at = timestamp

        self.storage.execute(
            """
            INSERT INTO characters(
                id,
                name,
                system_prompt,
                description,
                personality,
                scenario,
                data_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                system_prompt = excluded.system_prompt,
                description = excluded.description,
                personality = excluded.personality,
                scenario = excluded.scenario,
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
            """,
            (
                character.id,
                character.name,
                character.system_prompt,
                character.description,
                character.personality,
                character.scenario,
                self._to_json(character),
                character.created_at,
                character.updated_at,
            ),
        )
        return character

    def get_character(self, character_id: str) -> Character | None:
        self._ensure_character_columns()
        row = self.storage.fetch_one(
            "SELECT * FROM characters WHERE id = ?",
            (character_id,),
        )
        if row is None:
            return None
        return self._from_row(row)

    def list_characters(self) -> list[Character]:
        self._ensure_character_columns()
        rows = self.storage.fetch_all("SELECT * FROM characters ORDER BY created_at, id")
        return [self._from_row(row) for row in rows]

    def character_from_persona(self, persona: object) -> Character:
        name = self._first_string(self._safe_getattr(persona, "name"), "Persona")
        prompt = self._first_string(
            self._safe_getattr(persona, "system_prompt"),
            self._safe_getattr(persona, "prompt"),
        )
        description = self._string_value(self._safe_getattr(persona, "description"))
        personality = self._string_value(self._safe_getattr(persona, "personality"))
        scenario = self._string_value(self._safe_getattr(persona, "scenario"))
        return Character(
            id=make_stable_id(
                "temporary_persona",
                name,
                prompt,
                description,
                personality,
                scenario,
            ),
            name=name,
            system_prompt=prompt,
            description=description,
            personality=personality,
            scenario=scenario,
            metadata={"temporary": True, "source": "astrbot_persona"},
        )

    def resolve_character(
        self,
        session: RpSession,
        account_profile: AccountProfile | None,
        persona: object | None,
    ) -> Character:
        if session.active_character_id:
            character = self.get_character(session.active_character_id)
            if character is not None:
                return character

        if account_profile is not None and account_profile.default_character_id:
            character = self.get_character(account_profile.default_character_id)
            if character is not None:
                return character

        if persona is not None:
            return self.character_from_persona(persona)

        return self.fallback_character()

    def _from_row(self, row: sqlite3.Row) -> Character:
        data = loads_json(row["data_json"])
        if not isinstance(data, dict):
            data = {}
        return Character(
            id=row["id"],
            name=row["name"],
            system_prompt=row["system_prompt"],
            description=row["description"],
            personality=row["personality"],
            scenario=row["scenario"],
            metadata=self._dict_value(data.get("metadata")),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    def _to_json(self, character: Character) -> str:
        return dumps_json({"metadata": character.metadata})

    def _ensure_character_columns(self) -> None:
        columns = {row["name"] for row in self.storage.fetch_all("PRAGMA table_info(characters)")}
        for name in ("system_prompt", "description", "personality", "scenario"):
            if name not in columns:
                self.storage.execute(
                    f"ALTER TABLE characters ADD COLUMN {name} TEXT NOT NULL DEFAULT ''"
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

    def _dict_value(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}
