from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from smarter_rp.models import AccountProfile, Character, RpSession
from smarter_rp.services.character_service import CharacterService, FALLBACK_CHARACTER_ID
from smarter_rp.storage import Storage, loads_json


def make_service(tmp_path: Path) -> tuple[Storage, CharacterService]:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    return storage, CharacterService(storage)


def test_builtin_fallback_character_exists(tmp_path: Path):
    _, service = make_service(tmp_path)

    character = service.fallback_character()

    assert character.id == FALLBACK_CHARACTER_ID
    assert character.name != ""
    assert character.system_prompt != ""
    assert character.metadata == {}


def test_persona_maps_to_temporary_character(tmp_path: Path):
    _, service = make_service(tmp_path)
    persona = SimpleNamespace(
        name="Narrator",
        prompt="prompt fallback",
        system_prompt="system prompt",
        description="description",
        personality="personality",
        scenario="scenario",
    )

    first = service.character_from_persona(persona)
    second = service.character_from_persona(persona)

    assert first.id == second.id
    assert first.id.startswith("temporary_persona_")
    assert first.name == "Narrator"
    assert first.system_prompt == "system prompt"
    assert first.description == "description"
    assert first.personality == "personality"
    assert first.scenario == "scenario"
    assert first.metadata["temporary"] is True
    assert first.metadata["source"] == "astrbot_persona"


def test_resolution_prefers_session_character(tmp_path: Path):
    _, service = make_service(tmp_path)
    account_character = Character(
        id="character_account",
        name="Account Character",
        system_prompt="account prompt",
    )
    session_character = Character(
        id="character_session",
        name="Session Character",
        system_prompt="session prompt",
    )
    service.save_character(account_character)
    service.save_character(session_character)
    session = RpSession(
        id="session_1",
        unified_msg_origin="origin",
        account_profile_id="account_1",
        active_character_id=session_character.id,
    )
    account = AccountProfile(
        id="account_1",
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        default_character_id=account_character.id,
    )
    persona = SimpleNamespace(name="Persona", system_prompt="persona prompt")

    resolved = service.resolve_character(session, account, persona)

    assert resolved.id == session_character.id
    assert resolved.name == "Session Character"


def test_resolution_uses_account_then_persona_then_fallback(tmp_path: Path):
    _, service = make_service(tmp_path)
    account_character = Character(
        id="character_account",
        name="Account Character",
        system_prompt="account prompt",
    )
    service.save_character(account_character)
    session = RpSession(id="session_1", unified_msg_origin="origin", account_profile_id="account_1")
    account = AccountProfile(
        id="account_1",
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        default_character_id=account_character.id,
    )
    persona = SimpleNamespace(name="Persona", system_prompt="persona prompt")

    assert service.resolve_character(session, account, persona).id == account_character.id

    account.default_character_id = "character_missing"
    persona_character = service.resolve_character(session, account, persona)
    assert persona_character.id.startswith("temporary_persona_")
    assert persona_character.name == "Persona"

    fallback = service.resolve_character(session, None, None)
    assert fallback.id == FALLBACK_CHARACTER_ID
    assert fallback.system_prompt != ""


def test_save_get_and_list_characters_persist_columns_and_metadata(tmp_path: Path):
    storage, service = make_service(tmp_path)
    character = Character(
        id="character_1",
        name="Alice",
        system_prompt="You are Alice.",
        description="A traveler",
        personality="Curious",
        scenario="At the gate",
        metadata={"tags": ["hero"]},
    )

    saved = service.save_character(character)
    loaded = service.get_character(character.id)
    listed = service.list_characters()
    row = storage.fetch_one("SELECT * FROM characters WHERE id = ?", (character.id,))

    assert saved.created_at > 0
    assert saved.updated_at > 0
    assert loaded == saved
    assert listed == [saved]
    assert row is not None
    assert row["system_prompt"] == "You are Alice."
    assert row["description"] == "A traveler"
    assert row["personality"] == "Curious"
    assert row["scenario"] == "At the gate"
    assert loads_json(row["data_json"]) == {"metadata": {"tags": ["hero"]}}


def test_save_character_upsert_preserves_created_at_and_refreshes_updated_at(
    tmp_path: Path, monkeypatch
):
    _, service = make_service(tmp_path)
    timestamps = iter([100, 200])
    monkeypatch.setattr("smarter_rp.services.character_service.now_ts", lambda: next(timestamps))
    first_character = Character(
        id="character_1",
        name="Alice",
        system_prompt="You are Alice.",
    )
    replacement_character = Character(
        id="character_1",
        name="Bob",
        system_prompt="You are Bob.",
        created_at=999,
        updated_at=999,
    )

    first_saved = service.save_character(first_character)
    replacement_saved = service.save_character(replacement_character)
    loaded = service.get_character(replacement_character.id)

    assert replacement_saved.created_at == first_saved.created_at
    assert replacement_saved.updated_at == 200
    assert replacement_saved == loaded
