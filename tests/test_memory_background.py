import json
from pathlib import Path

from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.memory_extractor import MemoryExtractor, MemoryTriggerPolicy
from smarter_rp.services.memory_service import MemoryService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage


class FakeProvider:
    def __init__(self, output: str):
        self.output = output
        self.prompts = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.output


def make_services(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    sessions = SessionService(storage)
    history = HistoryService(storage, sessions, max_history_messages=100)
    memory = MemoryService(storage, sessions)
    debug = DebugService(storage)
    extractor = MemoryExtractor(memory, history, debug, min_state_confidence=0.65)
    return storage, sessions, history, memory, debug, extractor


def test_run_if_needed_debugs_provider_unavailable_when_trigger_fires(tmp_path: Path):
    _, sessions, history, _, debug, extractor = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", None)
    history.append_message(session.id, role="user", speaker="User", content="hello")

    result = extractor.run_if_needed(
        session.id,
        MemoryTriggerPolicy(every_turns=1, history_chars_threshold=9999),
        None,
    )
    snapshots = debug.list_snapshots(session_id=session.id, snapshot_type="memory")

    assert result.triggered is True
    assert result.reason == "provider_unavailable"
    assert len(snapshots) == 1
    content = json.loads(snapshots[0].content)
    assert content["kind"] == "extraction"
    assert content["status"] == "provider_unavailable"
    assert content["trigger_reason"] == "every_turns"


def test_run_if_needed_debugs_malformed_provider_output(tmp_path: Path):
    _, sessions, history, _, debug, extractor = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", None)
    history.append_message(session.id, role="user", speaker="User", content="Alice finds a silver key.")
    provider = FakeProvider(
        '{"events":[{"content":"Alice found a key","importance":"high","confidence":"likely","source_message_ids":[],"turn_range":[1,1]}]}'
    )

    result = extractor.run_if_needed(
        session.id,
        MemoryTriggerPolicy(every_turns=1, history_chars_threshold=9999),
        provider,
    )

    snapshots = debug.list_snapshots(session_id=session.id, snapshot_type="memory")
    assert result.triggered is True
    assert result.reason == "parse_failed"
    assert json.loads(snapshots[0].content)["status"] == "parse_failed"


def test_run_if_needed_applies_provider_json_output(tmp_path: Path):
    _, sessions, history, memory, debug, extractor = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", None)
    first = history.append_message(session.id, role="user", speaker="User", content="Alice finds a silver key.")
    second = history.append_message(session.id, role="assistant", speaker="Assistant", content="The key hums softly.")
    provider = FakeProvider(
        json.dumps(
            {
                "summary": "Alice has a humming silver key.",
                "state": {"location": "library", "mood": {"value": "curious", "confidence": 0.9}},
                "events": [
                    {
                        "content": "Alice found a humming silver key.",
                        "importance": 8,
                        "confidence": 0.85,
                        "source_message_ids": [first.id, second.id],
                        "turn_range": [1, 2],
                    }
                ],
            }
        )
    )

    result = extractor.run_if_needed(
        session.id,
        MemoryTriggerPolicy(every_turns=1, history_chars_threshold=9999),
        provider,
    )

    loaded = sessions.get_by_id(session.id)
    memories = memory.list_memories(session.id, limit=None)
    snapshots = debug.list_snapshots(session_id=session.id, snapshot_type="memory")

    assert result.triggered is True
    assert result.reason == "completed"
    assert result.summary_updated is True
    assert result.state_updated is True
    assert result.memories_created == 1
    assert loaded.summary == "Alice has a humming silver key."
    assert loaded.state == {"location": "library", "mood": "curious"}
    assert loaded.memory_processed_turn == 1
    assert len(memories) == 1
    assert memories[0].content == "Alice found a humming silver key."
    assert memories[0].source_message_ids == [first.id, second.id]
    assert memories[0].turn_range == (1, 2)
    assert memories[0].importance == 8
    assert memories[0].confidence == 0.85
    assert json.loads(snapshots[0].content)["status"] == "completed"
    assert provider.prompts


def test_run_if_needed_counts_only_new_memories_when_events_deduplicate(tmp_path: Path):
    _, sessions, history, memory, _debug, extractor = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", None)
    message = history.append_message(session.id, role="user", speaker="User", content="Alice keeps the key.")
    duplicate_event = {
        "content": "Alice keeps the key.",
        "importance": 8,
        "confidence": 0.9,
        "source_message_ids": [message.id],
        "turn_range": [1, 1],
    }
    provider = FakeProvider(
        json.dumps(
            {
                "summary": "",
                "state": {},
                "events": [duplicate_event, duplicate_event],
            }
        )
    )

    result = extractor.run_if_needed(
        session.id,
        MemoryTriggerPolicy(every_turns=1, history_chars_threshold=9999),
        provider,
    )

    assert result.reason == "completed"
    assert result.memories_created == 1
    assert len(memory.list_memories(session.id, limit=None)) == 1


def test_run_if_needed_advances_checkpoint_without_events(tmp_path: Path):
    _, sessions, history, memory, _debug, extractor = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", None)
    history.append_message(session.id, role="user", speaker="User", content="Alice enters town.")
    provider = FakeProvider(json.dumps({"summary": "Alice is in town.", "state": {}, "events": []}))

    result = extractor.run_if_needed(
        session.id,
        MemoryTriggerPolicy(every_turns=1, history_chars_threshold=9999),
        provider,
    )
    second_result = extractor.run_if_needed(
        session.id,
        MemoryTriggerPolicy(every_turns=1, history_chars_threshold=9999),
        provider,
    )

    loaded = sessions.get_by_id(session.id)
    assert result.reason == "completed"
    assert result.memories_created == 0
    assert second_result.triggered is False
    assert second_result.reason == "no_new_turns"
    assert loaded.summary == "Alice is in town."
    assert loaded.memory_processed_turn == 1
    assert memory.list_memories(session.id, limit=None) == []
