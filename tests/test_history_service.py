from __future__ import annotations

from pathlib import Path

from smarter_rp.models import RpMessage
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage


def make_services(tmp_path: Path) -> tuple[Storage, SessionService, HistoryService]:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    sessions = SessionService(storage)
    history = HistoryService(storage, sessions, max_history_messages=4)
    return storage, sessions, history


def test_rp_message_defaults():
    message = RpMessage(
        id="message_1",
        session_id="session_1",
        role="user",
        speaker="User",
        content="Hello",
    )

    assert message.visible is True
    assert message.turn_number == 0
    assert message.metadata == {}
    assert message.created_at == 0


def test_append_messages_updates_session_recent_and_turn_count(tmp_path: Path):
    _, sessions, history = make_services(tmp_path)
    session = sessions.get_or_create("origin-history", "account_1")

    user_message = history.append_message(session.id, role="user", speaker="User", content="Hello")
    assistant_message = history.append_message(
        session.id,
        role="assistant",
        speaker="Alice",
        content="Hi",
        metadata={"mood": "warm"},
    )

    messages = history.list_messages(session.id)
    refreshed = sessions.get_by_id(session.id)

    assert [message.id for message in messages] == [user_message.id, assistant_message.id]
    assert [message.turn_number for message in messages] == [1, 1]
    assert assistant_message.metadata == {"mood": "warm"}
    assert refreshed.turn_count == 1
    assert refreshed.recent_messages == [
        {"id": user_message.id, "role": "user", "speaker": "User", "content": "Hello", "turn_number": 1},
        {"id": assistant_message.id, "role": "assistant", "speaker": "Alice", "content": "Hi", "turn_number": 1},
    ]


def test_visible_system_before_first_user_does_not_increment_turn(tmp_path: Path):
    _, sessions, history = make_services(tmp_path)
    session = sessions.get_or_create("origin-system-first", None)

    system_message = history.append_message(
        session.id,
        role="system",
        speaker="System",
        content="Prologue",
        visible=True,
    )
    user_message = history.append_message(session.id, role="user", speaker="User", content="Hello")

    assert system_message.turn_number == 0
    assert user_message.turn_number == 1
    assert [message.turn_number for message in history.list_messages(session.id)] == [0, 1]
    assert sessions.get_by_id(session.id).turn_count == 1


def test_assistant_before_first_user_does_not_increment_turn(tmp_path: Path):
    _, sessions, history = make_services(tmp_path)
    session = sessions.get_or_create("origin-assistant-first", None)

    assistant_message = history.append_message(session.id, role="assistant", speaker="Alice", content="Hi")
    user_message = history.append_message(session.id, role="user", speaker="User", content="Hello")

    assert assistant_message.turn_number == 0
    assert user_message.turn_number == 1
    assert [message.turn_number for message in history.list_messages(session.id)] == [0, 1]
    assert sessions.get_by_id(session.id).turn_count == 1


def test_assistant_after_user_shares_user_turn(tmp_path: Path):
    _, sessions, history = make_services(tmp_path)
    session = sessions.get_or_create("origin-assistant-shares-turn", None)

    user_message = history.append_message(session.id, role="user", speaker="User", content="Hello")
    assistant_message = history.append_message(session.id, role="assistant", speaker="Alice", content="Hi")

    assert user_message.turn_number == 1
    assert assistant_message.turn_number == 1
    assert [message.turn_number for message in history.list_messages(session.id)] == [1, 1]
    assert sessions.get_by_id(session.id).turn_count == 1


def test_append_message_ids_do_not_collide_for_same_content_in_same_second(tmp_path: Path, monkeypatch):
    _, sessions, history = make_services(tmp_path)
    session = sessions.get_or_create("origin-collision", None)
    monkeypatch.setattr("smarter_rp.services.history_service.now_ts", lambda: 100)

    first = history.append_message(session.id, role="user", speaker="User", content="same")
    second = history.append_message(session.id, role="user", speaker="User", content="same")

    assert first.id != second.id
    assert [message.content for message in history.list_messages(session.id)] == ["same", "same"]


def test_history_trims_old_visible_messages(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    sessions = SessionService(storage)
    history = HistoryService(storage, sessions, max_history_messages=3)
    session = sessions.get_or_create("origin-trim", None)

    for index in range(5):
        history.append_message(session.id, role="user", speaker="User", content=f"u{index}")

    messages = history.list_messages(session.id)
    refreshed = sessions.get_by_id(session.id)

    assert [message.content for message in messages] == ["u2", "u3", "u4"]
    assert [message["content"] for message in refreshed.recent_messages] == ["u2", "u3", "u4"]
    assert refreshed.turn_count == 5


def test_invisible_messages_are_listed_only_when_requested_and_not_trimmed(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    sessions = SessionService(storage)
    history = HistoryService(storage, sessions, max_history_messages=1)
    session = sessions.get_or_create("origin-invisible", None)

    hidden = history.append_message(
        session.id,
        role="system",
        speaker="System",
        content="hidden",
        visible=False,
    )
    history.append_message(session.id, role="user", speaker="User", content="u1")
    history.append_message(session.id, role="user", speaker="User", content="u2")

    assert [message.content for message in history.list_messages(session.id)] == ["u2"]
    assert [message.id for message in history.list_messages(session.id, visible_only=False)] == [hidden.id, history.list_messages(session.id)[0].id]


def test_clear_history_and_undo_latest_turn(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    sessions = SessionService(storage)
    history = HistoryService(storage, sessions, max_history_messages=10)
    session = sessions.get_or_create("origin-undo", None)
    history.append_message(session.id, role="user", speaker="User", content="u1")
    history.append_message(session.id, role="assistant", speaker="Bot", content="a1")
    history.append_message(session.id, role="user", speaker="User", content="u2")
    history.append_message(session.id, role="assistant", speaker="Bot", content="a2")

    removed = history.undo_latest_turn(session.id)

    assert [message.content for message in removed] == ["u2", "a2"]
    assert [message.content for message in history.list_messages(session.id)] == ["u1", "a1"]
    assert sessions.get_by_id(session.id).turn_count == 1

    history.clear_history(session.id)

    assert history.list_messages(session.id) == []
    refreshed = sessions.get_by_id(session.id)
    assert refreshed.recent_messages == []
    assert refreshed.turn_count == 0


def test_undo_latest_turn_returns_empty_when_no_visible_messages(tmp_path: Path):
    _, sessions, history = make_services(tmp_path)
    session = sessions.get_or_create("origin-empty-undo", None)
    history.append_message(session.id, role="system", speaker="System", content="hidden", visible=False)

    assert history.undo_latest_turn(session.id) == []
    assert [message.content for message in history.list_messages(session.id, visible_only=False)] == ["hidden"]
