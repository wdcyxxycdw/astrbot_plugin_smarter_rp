from pathlib import Path

from smarter_rp.ids import make_stable_id
from smarter_rp.models import RpSession
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage, dumps_json


def test_make_stable_id_is_deterministic_and_prefixed():
    first = make_stable_id("session", "aiocqhttp", "123", "group:456")
    second = make_stable_id("session", "aiocqhttp", "123", "group:456")

    assert first == second
    assert first.startswith("session_")


def test_make_stable_id_preserves_part_boundaries():
    assert make_stable_id("x", "a", "b") != make_stable_id("x", "a\x1fb")


def test_make_stable_id_preserves_type_boundaries():
    assert make_stable_id("x", 1) != make_stable_id("x", "1")


def test_make_stable_id_is_stable_for_mapping_key_order():
    assert make_stable_id("x", {"a": 1, "b": 2}) == make_stable_id("x", {"b": 2, "a": 1})


def test_rp_session_defaults_to_not_paused():
    session = RpSession(
        id="session_1",
        unified_msg_origin="aiocqhttp:123:group:456",
        account_profile_id="account_1",
    )

    assert session.paused is False
    assert session.active_lorebook_ids == []
    assert session.turn_count == 0


def test_session_service_get_or_create_creates_active_session(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    service = SessionService(storage)

    session = service.get_or_create("aiocqhttp:123:group:456", "account_1")

    assert session.unified_msg_origin == "aiocqhttp:123:group:456"
    assert session.account_profile_id == "account_1"
    assert session.paused is False


def test_session_service_get_or_create_is_idempotent(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    service = SessionService(storage)

    first = service.get_or_create("aiocqhttp:123:group:456", "account_1")
    second = service.get_or_create("aiocqhttp:123:group:456", "account_2")

    assert second.id == first.id
    assert second.account_profile_id == "account_1"

    row = storage.fetch_one(
        "SELECT COUNT(*) AS count FROM rp_sessions WHERE unified_msg_origin = ?",
        ("aiocqhttp:123:group:456",),
    )
    assert row is not None
    assert row["count"] == 1


def test_session_service_set_paused_pauses_and_resumes(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    service = SessionService(storage)
    session = service.get_or_create("aiocqhttp:123:group:456", "account_1")

    paused_session = service.set_paused(session.id, True)
    paused_row = storage.fetch_one(
        "SELECT paused, updated_at FROM rp_sessions WHERE id = ?",
        (session.id,),
    )
    resumed_session = service.set_paused(session.id, False)
    resumed_row = storage.fetch_one(
        "SELECT paused, updated_at FROM rp_sessions WHERE id = ?",
        (session.id,),
    )

    assert paused_session.paused is True
    assert paused_row is not None
    assert paused_row["paused"] == 1
    assert paused_row["updated_at"] >= session.created_at

    assert resumed_session.paused is False
    assert resumed_row is not None
    assert resumed_row["paused"] == 0
    assert resumed_row["updated_at"] >= session.created_at
    assert service.get_by_id(session.id).paused is False


def test_session_service_lists_sessions(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    service = SessionService(storage)

    service.get_or_create("origin:1", "account_1")
    service.get_or_create("origin:2", "account_1")

    sessions = service.list_sessions()

    assert [session.unified_msg_origin for session in sessions] == ["origin:1", "origin:2"]


def test_session_service_updates_active_character_and_lorebooks(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    service = SessionService(storage)
    session = service.get_or_create("origin:1", "account_1")

    updated = service.update_session_controls(
        session.id,
        active_character_id="character_1",
        active_lorebook_ids=["lore_1"],
    )

    loaded = service.get_by_id(session.id)

    assert updated.active_character_id == "character_1"
    assert updated.active_lorebook_ids == ["lore_1"]
    assert loaded.active_character_id == "character_1"
    assert loaded.active_lorebook_ids == ["lore_1"]


def test_session_service_clears_active_character_only_when_explicit_none(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    service = SessionService(storage)
    session = service.get_or_create("origin:1", "account_1")

    service.update_session_controls(session.id, active_character_id="character_1")
    omitted = service.update_session_controls(session.id, paused=True)
    cleared = service.update_session_controls(session.id, active_character_id=None)
    row = storage.fetch_one(
        "SELECT active_character_id FROM rp_sessions WHERE id = ?",
        (session.id,),
    )

    assert omitted.active_character_id == "character_1"
    assert service.get_by_id(session.id).active_character_id is None
    assert cleared.active_character_id is None
    assert row is not None
    assert row["active_character_id"] is None


def test_session_service_get_by_id_preserves_data_json_fields(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    service = SessionService(storage)
    data = {
        "active_lorebook_ids": ["lorebook_1", "lorebook_2"],
        "summary": "角色已经见面。",
        "state": {"location": "library", "mood": "curious"},
        "recent_messages": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好，旅行者。"},
        ],
        "last_lore_hits": [{"entry_id": "lore_1", "score": 0.8}],
        "last_memory_hits": [{"memory_id": "memory_1", "score": 0.9}],
        "turn_count": 7,
    }

    storage.execute(
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
            "session_data_json",
            "aiocqhttp:123:group:789",
            "account_1",
            0,
            "character_1",
            dumps_json(data),
            100,
            200,
        ),
    )

    session = service.get_by_id("session_data_json")

    assert session.active_lorebook_ids == data["active_lorebook_ids"]
    assert session.summary == data["summary"]
    assert session.state == data["state"]
    assert session.recent_messages == data["recent_messages"]
    assert session.last_lore_hits == data["last_lore_hits"]
    assert session.last_memory_hits == data["last_memory_hits"]
    assert session.turn_count == data["turn_count"]
