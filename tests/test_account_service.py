from pathlib import Path
from types import SimpleNamespace

import pytest

from smarter_rp.services.account_service import AccountIdentity, AccountService
from smarter_rp.storage import Storage, loads_json


def make_service(tmp_path: Path) -> tuple[Storage, AccountService]:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    return storage, AccountService(storage)


def test_get_or_create_creates_enabled_profile_with_empty_lorebooks(tmp_path: Path):
    storage, service = make_service(tmp_path)

    profile = service.get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Alice")
    )

    row = storage.fetch_one("SELECT * FROM account_profiles WHERE id = ?", (profile.id,))
    assert row is not None
    assert profile.adapter_name == "aiocqhttp"
    assert profile.platform == "qq"
    assert profile.account_id == "bot-123"
    assert profile.display_name == "Bot Alice"
    assert profile.default_enabled is True
    assert profile.default_lorebook_ids == []
    assert row["default_enabled"] == 1
    assert loads_json(row["data_json"])["default_lorebook_ids"] == []


def test_get_or_create_is_idempotent_and_does_not_overwrite_display_name(tmp_path: Path):
    storage, service = make_service(tmp_path)

    first = service.get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Alice")
    )
    second = service.get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Changed")
    )

    row = storage.fetch_one(
        """
        SELECT COUNT(*) AS count FROM account_profiles
        WHERE adapter_name = ? AND platform = ? AND account_id = ?
        """,
        ("aiocqhttp", "qq", "bot-123"),
    )
    assert second.id == first.id
    assert second.display_name == "Bot Alice"
    assert row is not None
    assert row["count"] == 1


def test_update_profile_persists_control_fields(tmp_path: Path):
    _, service = make_service(tmp_path)
    profile = service.get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Alice")
    )

    updated = service.update_profile(
        profile.id,
        default_enabled=False,
        default_character_id="character_1",
        default_lorebook_ids=["lore_1", "lore_2"],
    )
    loaded = service.get_by_id(profile.id)

    assert updated.default_enabled is False
    assert updated.default_character_id == "character_1"
    assert updated.default_lorebook_ids == ["lore_1", "lore_2"]
    assert loaded.default_enabled is False
    assert loaded.default_character_id == "character_1"
    assert loaded.default_lorebook_ids == ["lore_1", "lore_2"]


def test_update_profile_can_clear_default_character_id(tmp_path: Path):
    storage, service = make_service(tmp_path)
    profile = service.get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Alice")
    )
    service.update_profile(profile.id, default_character_id="character_1")

    updated = service.update_profile(profile.id, default_character_id=None)
    loaded = service.get_by_id(profile.id)
    row = storage.fetch_one(
        "SELECT default_character_id FROM account_profiles WHERE id = ?",
        (profile.id,),
    )

    assert updated.default_character_id is None
    assert loaded.default_character_id is None
    assert row is not None
    assert row["default_character_id"] is None


def test_update_profile_can_update_display_name(tmp_path: Path):
    _, service = make_service(tmp_path)
    profile = service.get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Alice")
    )

    updated = service.update_profile(profile.id, display_name="Bot Renamed")

    assert updated.display_name == "Bot Renamed"
    assert service.get_by_id(profile.id).display_name == "Bot Renamed"


def test_get_by_id_raises_key_error_when_missing(tmp_path: Path):
    _, service = make_service(tmp_path)

    with pytest.raises(KeyError):
        service.get_by_id("account_missing")


def test_extract_identity_prefers_explicit_event_fields(tmp_path: Path):
    _, service = make_service(tmp_path)
    event = SimpleNamespace(
        adapter_name="explicit-adapter",
        platform="explicit-platform",
        account_id="explicit-account",
        display_name="Explicit Bot",
        self_id="fallback-self",
        unified_msg_origin="origin-adapter:origin-account:group:456",
        message_obj=SimpleNamespace(
            adapter_name="message-adapter",
            platform="message-platform",
            self_id="message-self",
            display_name="Message Bot",
        ),
    )

    identity = service.extract_identity(event)

    assert identity == AccountIdentity(
        "explicit-adapter",
        "explicit-platform",
        "explicit-account",
        "Explicit Bot",
    )


def test_extract_identity_falls_back_to_message_obj_and_origin(tmp_path: Path):
    _, service = make_service(tmp_path)
    event = SimpleNamespace(
        type="group",
        unified_msg_origin="aiocqhttp:bot-123:group:456",
        message_obj=SimpleNamespace(platform="qq", self_id="bot-from-message"),
    )

    identity = service.extract_identity(event)

    assert identity == AccountIdentity("aiocqhttp", "qq", "bot-from-message", "")


def test_extract_identity_uses_origin_account_id_when_message_obj_has_no_bot_id(tmp_path: Path):
    _, service = make_service(tmp_path)
    event = SimpleNamespace(
        type="group",
        unified_msg_origin="aiocqhttp:bot-123:group:456",
        message_obj=SimpleNamespace(platform="qq"),
    )

    identity = service.extract_identity(event)

    assert identity == AccountIdentity("aiocqhttp", "qq", "bot-123", "")


def test_extract_identity_handles_unknown_objects_without_raising(tmp_path: Path):
    _, service = make_service(tmp_path)

    identity = service.extract_identity(object())

    assert identity == AccountIdentity("unknown", "unknown", "unknown", "")


def test_list_profiles_returns_profiles_in_stable_order(tmp_path: Path):
    _, service = make_service(tmp_path)
    first = service.get_or_create(AccountIdentity("aiocqhttp", "qq", "bot-1", "Bot 1"))
    second = service.get_or_create(AccountIdentity("aiocqhttp", "qq", "bot-2", "Bot 2"))

    profiles = service.list_profiles()

    assert {profile.id for profile in profiles} == {first.id, second.id}
    assert profiles == sorted(profiles, key=lambda profile: (profile.created_at, profile.id))
