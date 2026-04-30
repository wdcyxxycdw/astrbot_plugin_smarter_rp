from pathlib import Path

from fastapi.testclient import TestClient

from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage
from smarter_rp.web.app import create_app


def make_storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    return storage


def serialized_message(message) -> dict:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "speaker": message.speaker,
        "content": message.content,
        "visible": message.visible,
        "turn_number": message.turn_number,
        "metadata": message.metadata,
        "created_at": message.created_at,
    }


def test_session_history_get_requires_token(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    response = client.get("/api/sessions/session_1/history")

    assert response.status_code == 401


def test_session_history_get_lists_visible_messages_with_limit(tmp_path: Path):
    storage = make_storage(tmp_path)
    sessions = SessionService(storage)
    session = sessions.get_or_create("origin:1", "account_1")
    history = HistoryService(storage, sessions)
    first = history.append_message(
        session.id,
        role="user",
        speaker="Alice",
        content="Hello",
        metadata={"source": "test"},
    )
    second = history.append_message(
        session.id,
        role="assistant",
        speaker="Bob",
        content="Hi",
    )
    history.append_message(
        session.id,
        role="system",
        speaker="System",
        content="Hidden note",
        visible=False,
    )
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.get(f"/api/sessions/{session.id}/history?token=secret-token&limit=1")

    assert response.status_code == 200
    assert response.json() == {"messages": [serialized_message(first)]}
    assert second.id != first.id


def test_session_history_undo_removes_latest_visible_turn_and_refreshes_session(tmp_path: Path):
    storage = make_storage(tmp_path)
    sessions = SessionService(storage)
    session = sessions.get_or_create("origin:1", "account_1")
    history = HistoryService(storage, sessions)
    first_turn = history.append_message(session.id, role="user", speaker="Alice", content="One")
    assistant_first = history.append_message(session.id, role="assistant", speaker="Bob", content="Two")
    second_turn = history.append_message(session.id, role="user", speaker="Alice", content="Three")
    assistant_second = history.append_message(session.id, role="assistant", speaker="Bob", content="Four")
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.post(f"/api/sessions/{session.id}/history/undo?token=secret-token")

    assert response.status_code == 200
    assert response.json() == {
        "removed": [serialized_message(second_turn), serialized_message(assistant_second)]
    }
    assert [message.id for message in history.list_messages(session.id)] == [
        first_turn.id,
        assistant_first.id,
    ]
    loaded = sessions.get_by_id(session.id)
    assert loaded.turn_count == 1
    assert [message["id"] for message in loaded.recent_messages] == [
        first_turn.id,
        assistant_first.id,
    ]


def test_session_history_delete_clears_history_and_refreshes_session(tmp_path: Path):
    storage = make_storage(tmp_path)
    sessions = SessionService(storage)
    session = sessions.get_or_create("origin:1", "account_1")
    history = HistoryService(storage, sessions)
    history.append_message(session.id, role="user", speaker="Alice", content="One")
    history.append_message(session.id, role="assistant", speaker="Bob", content="Two")
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.delete(f"/api/sessions/{session.id}/history?token=secret-token")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert history.list_messages(session.id) == []
    loaded = sessions.get_by_id(session.id)
    assert loaded.turn_count == 0
    assert loaded.recent_messages == []


def test_session_history_without_storage_returns_empty_messages():
    client = TestClient(create_app(token="secret-token"))

    response = client.get("/api/sessions/session_1/history?token=secret-token")

    assert response.status_code == 200
    assert response.json() == {"messages": []}
