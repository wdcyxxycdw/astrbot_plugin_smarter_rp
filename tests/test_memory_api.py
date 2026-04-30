from pathlib import Path

from fastapi.testclient import TestClient

from smarter_rp.services.memory_service import MemoryService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage
from smarter_rp.web.app import create_app


def make_storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    return storage


def serialized_memory(memory) -> dict:
    return {
        "id": memory.id,
        "session_id": memory.session_id,
        "type": memory.type,
        "content": memory.content,
        "importance": memory.importance,
        "confidence": memory.confidence,
        "source_message_ids": memory.source_message_ids,
        "turn_range": list(memory.turn_range) if memory.turn_range is not None else None,
        "embedding_id": memory.embedding_id,
        "embedding_version": memory.embedding_version,
        "metadata": memory.metadata,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


def serialized_status(session, memory_count: int) -> dict:
    return {
        "id": session.id,
        "unified_msg_origin": session.unified_msg_origin,
        "summary": session.summary,
        "state": session.state,
        "memory_count": memory_count,
        "last_memory_hits": session.last_memory_hits,
        "turn_count": session.turn_count,
        "updated_at": session.updated_at,
    }


def test_memory_sessions_requires_token(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    response = client.get("/api/memory/sessions")

    assert response.status_code == 401


def test_memory_sessions_list_returns_statuses(tmp_path: Path):
    storage = make_storage(tmp_path)
    sessions = SessionService(storage)
    memory_service = MemoryService(storage, sessions)
    session = sessions.get_or_create("origin_1", None)
    session.summary = "Known facts"
    session.state = {"mood": "calm"}
    session.last_memory_hits = [{"memory_id": "memory_1", "reason": "recent"}]
    session.turn_count = 3
    session = sessions.save_session_state(session)
    memory_service.create_event_memory(session.id, "Alice met Bob", 7, 0.9)
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.get("/api/memory/sessions?token=secret-token")

    assert response.status_code == 200
    assert response.json() == [serialized_status(session, 1)]


def test_memory_session_detail_returns_status_and_memories(tmp_path: Path):
    storage = make_storage(tmp_path)
    sessions = SessionService(storage)
    memory_service = MemoryService(storage, sessions)
    session = sessions.get_or_create("origin_1", "account_1")
    memory = memory_service.create_event_memory(
        session.id,
        "Alice keeps a silver key",
        8,
        0.75,
        source_message_ids=["message_1"],
        turn_range=(1, 2),
        embedding_id="embedding_1",
        embedding_version="v1",
        metadata={"source": "test"},
    )
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.get(f"/api/memory/sessions/{session.id}?token=secret-token")

    assert response.status_code == 200
    assert response.json() == {
        "status": serialized_status(session, 1),
        "memories": [serialized_memory(memory)],
        "pagination": {"limit": 100, "offset": 0, "total": 1},
    }


def test_memory_session_detail_supports_limit_and_offset(tmp_path: Path):
    storage = make_storage(tmp_path)
    sessions = SessionService(storage)
    memory_service = MemoryService(storage, sessions)
    session = sessions.get_or_create("origin_1", None)
    first = memory_service.create_event_memory(session.id, "First fact", 5, 0.8)
    second = memory_service.create_event_memory(session.id, "Second fact", 5, 0.8)
    expected = sorted([first, second], key=lambda memory: (memory.created_at, memory.id))
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.get(f"/api/memory/sessions/{session.id}?token=secret-token&limit=1&offset=1")

    assert response.status_code == 200
    assert response.json() == {
        "status": serialized_status(session, 2),
        "memories": [serialized_memory(expected[1])],
        "pagination": {"limit": 1, "offset": 1, "total": 2},
    }


def test_memory_delete_memory_removes_memory(tmp_path: Path):
    storage = make_storage(tmp_path)
    sessions = SessionService(storage)
    memory_service = MemoryService(storage, sessions)
    session = sessions.get_or_create("origin_1", None)
    memory = memory_service.create_event_memory(session.id, "A fact", 5, 0.8)
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.delete(f"/api/memory/memories/{memory.id}?token=secret-token")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert memory_service.get_memory(memory.id) is None


def test_memory_clear_session_removes_memories_and_state(tmp_path: Path):
    storage = make_storage(tmp_path)
    sessions = SessionService(storage)
    memory_service = MemoryService(storage, sessions)
    session = sessions.get_or_create("origin_1", None)
    session.summary = "Summary"
    session.state = {"location": "garden"}
    session.last_memory_hits = [{"memory_id": "memory_1"}]
    session = sessions.save_session_state(session)
    memory_service.create_event_memory(session.id, "A fact", 5, 0.8)
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.delete(f"/api/memory/sessions/{session.id}?token=secret-token")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert memory_service.list_memories(session.id) == []
    loaded = sessions.get_by_id(session.id)
    assert loaded.summary == ""
    assert loaded.state == {}
    assert loaded.last_memory_hits == []
    assert loaded.memory_processed_turn == 0


def test_memory_api_returns_404_for_missing_resources(tmp_path: Path):
    storage = make_storage(tmp_path)
    sessions = SessionService(storage)
    session = sessions.get_or_create("origin_1", None)
    client = TestClient(create_app(token="secret-token", storage=storage))

    detail_response = client.get("/api/memory/sessions/session_missing?token=secret-token")
    delete_response = client.delete("/api/memory/memories/memory_missing?token=secret-token")
    clear_response = client.delete("/api/memory/sessions/session_missing?token=secret-token")

    assert session.id != "session_missing"
    assert detail_response.status_code == 404
    assert delete_response.status_code == 404
    assert clear_response.status_code == 404


def test_memory_sessions_without_storage_returns_empty_list():
    client = TestClient(create_app(token="secret-token"))

    response = client.get("/api/memory/sessions?token=secret-token")

    assert response.status_code == 200
    assert response.json() == []


def test_memory_mutations_without_storage_return_503():
    client = TestClient(create_app(token="secret-token"))

    delete_response = client.delete("/api/memory/memories/memory_1?token=secret-token")
    clear_response = client.delete("/api/memory/sessions/session_1?token=secret-token")

    assert delete_response.status_code == 503
    assert clear_response.status_code == 503
