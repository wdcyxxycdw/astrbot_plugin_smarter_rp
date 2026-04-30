from pathlib import Path

import pytest

from smarter_rp.services.memory_service import MemoryService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import SCHEMA_VERSION, Storage, loads_json


def make_services(tmp_path: Path) -> tuple[Storage, SessionService, MemoryService]:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    sessions = SessionService(storage)
    memories = MemoryService(storage, sessions)
    return storage, sessions, memories


def test_create_event_memory_persists_json_fields_and_lists_by_creation(tmp_path: Path):
    storage, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", "account_1")

    first = memories.create_event_memory(
        session.id,
        "  Alice found a key.  ",
        importance=99,
        confidence=-0.5,
        source_message_ids=["msg_1", "msg_2"],
        turn_range=[1, 3],
        embedding_id="embed_1",
        embedding_version="v1",
        metadata={"place": "library"},
    )
    second = memories.create_event_memory(session.id, "Bob arrived.", importance=3, confidence=0.75)

    listed = memories.list_memories(session.id)
    row = storage.fetch_one("SELECT data_json FROM memories WHERE id = ?", (first.id,))

    assert [memory.id for memory in listed] == [memory.id for memory in sorted([first, second], key=lambda memory: (memory.created_at, memory.id))]
    assert first.type == "event"
    assert first.content == "Alice found a key."
    assert first.importance == 10
    assert first.confidence == 0.0
    assert first.source_message_ids == ["msg_1", "msg_2"]
    assert first.turn_range == (1, 3)
    assert first.embedding_id == "embed_1"
    assert first.embedding_version == "v1"
    assert first.metadata == {"place": "library"}
    assert memories.get_memory(first.id) == first
    assert row is not None
    assert loads_json(row["data_json"]) == {
        "source_message_ids": ["msg_1", "msg_2"],
        "turn_range": [1, 3],
        "embedding_id": "embed_1",
        "embedding_version": "v1",
        "metadata": {"place": "library"},
    }


def test_create_event_memory_deduplicates_same_source_turn_and_content(tmp_path: Path):
    _, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", None)

    first = memories.create_event_memory(
        session.id,
        "Alice keeps a key",
        importance=5,
        confidence=0.7,
        source_message_ids=["message_1"],
        turn_range=(1, 1),
        metadata={"first": True},
    )
    second = memories.create_event_memory(
        session.id,
        "Alice keeps a key",
        importance=9,
        confidence=0.95,
        source_message_ids=["message_1"],
        turn_range=(1, 1),
        metadata={"second": True},
    )

    listed = memories.list_memories(session.id, limit=None)

    assert len(listed) == 1
    assert second.id == first.id
    assert listed[0].importance == 9
    assert listed[0].confidence == 0.95
    assert listed[0].metadata == {"first": True, "second": True}


def test_list_memories_supports_limit_and_none(tmp_path: Path):
    _, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", "account_1")

    created = [
        memories.create_event_memory(session.id, f"event {index}", importance=1, confidence=1)
        for index in range(3)
    ]

    expected = sorted(created, key=lambda memory: (memory.created_at, memory.id))

    assert [memory.id for memory in memories.list_memories(session.id, limit=2)] == [
        expected[0].id,
        expected[1].id,
    ]
    assert [memory.id for memory in memories.list_memories(session.id, limit=None)] == [
        memory.id for memory in expected
    ]


def test_update_session_memory_state_persists_summary_and_state(tmp_path: Path):
    _, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", "account_1")

    updated = memories.update_session_memory_state(
        session.id,
        "Alice has a silver key.",
        {"location": "library", "mood": "tense"},
    )
    loaded = sessions.get_by_id(session.id)

    assert updated.summary == "Alice has a silver key."
    assert updated.state == {"location": "library", "mood": "tense"}
    assert loaded.summary == updated.summary
    assert loaded.state == updated.state


def test_update_memory_validates_mutable_fields(tmp_path: Path):
    _, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", "account_1")
    memory = memories.create_event_memory(session.id, "Alice found a key.", importance=5, confidence=0.8)

    updated = memories.update_memory(
        memory.id,
        content="  Alice found the silver key.  ",
        importance=99,
        confidence=-1,
        source_message_ids=["message_1"],
        turn_range=[2, 3],
        metadata={"topic": "key"},
    )

    assert updated.content == "Alice found the silver key."
    assert updated.importance == 10
    assert updated.confidence == 0.0
    assert updated.source_message_ids == ["message_1"]
    assert updated.turn_range == (2, 3)
    assert updated.metadata == {"topic": "key"}
    assert memories.get_memory(memory.id) == updated
    with pytest.raises(ValueError, match="Immutable"):
        memories.update_memory(memory.id, session_id="other")
    with pytest.raises(ValueError, match="content"):
        memories.update_memory(memory.id, content="   ")
    with pytest.raises(KeyError):
        memories.update_memory("missing", content="x")


def test_delete_memory_and_clear_session_memory(tmp_path: Path):
    storage, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", "account_1")
    memory = memories.create_event_memory(session.id, "Alice found a key.", importance=5, confidence=0.8)
    memories.update_session_memory_state(session.id, "Summary", {"location": "library"})
    loaded = sessions.get_by_id(session.id)
    loaded.last_memory_hits = [{"memory_id": memory.id, "score": 1.0}]
    sessions.save_session_state(loaded)

    assert memories.delete_memory(memory.id) is True
    assert memories.delete_memory(memory.id) is False
    second = memories.create_event_memory(session.id, "Bob arrived.", importance=5, confidence=0.8)

    memories.clear_session_memory(session.id)
    cleared = sessions.get_by_id(session.id)
    row = storage.fetch_one("SELECT COUNT(*) AS count FROM memories WHERE session_id = ?", (session.id,))

    assert memories.get_memory(second.id) is None
    assert row is not None
    assert row["count"] == 0
    assert cleared.summary == ""
    assert cleared.state == {}
    assert cleared.last_memory_hits == []


def test_create_event_memory_rejects_missing_session_and_blank_content(tmp_path: Path):
    _, _, memories = make_services(tmp_path)

    with pytest.raises(KeyError):
        memories.create_event_memory("missing", "event", importance=1, confidence=1)
    with pytest.raises(KeyError):
        memories.list_memories("missing")

    sessions = SessionService(memories.storage)
    session = sessions.get_or_create("origin:1", "account_1")
    with pytest.raises(ValueError, match="content"):
        memories.create_event_memory(session.id, "   ", importance=1, confidence=1)


def test_memory_schema_indexes_are_idempotent(tmp_path: Path):
    storage, _, _ = make_services(tmp_path)

    rows = storage.fetch_all("SELECT name FROM sqlite_master WHERE type = 'index'")
    index_names = {row["name"] for row in rows}

    assert storage.get_schema_version() == SCHEMA_VERSION == 1
    assert "idx_memories_session_type" in index_names
    assert "idx_memories_session_updated" in index_names
    assert "idx_memories_session_importance" in index_names
