from pathlib import Path

from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.memory_extractor import MemoryExtractor, MemoryTriggerPolicy, parse_memory_extraction
from smarter_rp.services.memory_service import MemoryService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage


def make_services(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    sessions = SessionService(storage)
    history = HistoryService(storage, sessions, max_history_messages=100)
    memory = MemoryService(storage, sessions)
    debug = DebugService(storage)
    extractor = MemoryExtractor(memory, history, debug, min_state_confidence=0.65)
    return storage, sessions, history, memory, debug, extractor


def test_trigger_policy_uses_every_turns_after_latest_memory_turn_end(tmp_path: Path):
    _, sessions, history, memory, _, _ = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", None)
    for index in range(8):
        history.append_message(session.id, role="user", speaker="User", content=f"turn {index + 1}")
    memory.create_event_memory(session.id, "old event", 5, 0.9, turn_range=(1, 2))

    decision = MemoryTriggerPolicy(every_turns=6, history_chars_threshold=9999).should_run(
        sessions.get_by_id(session.id),
        history.list_messages(session.id),
        memory.list_memories(session.id, limit=None),
    )

    assert decision.triggered is True
    assert decision.reason == "every_turns"
    assert decision.start_turn == 3
    assert decision.end_turn == 8


def test_trigger_policy_uses_history_chars_threshold_after_latest_memory_turn_end(tmp_path: Path):
    _, sessions, history, memory, _, _ = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", None)
    history.append_message(session.id, role="user", speaker="User", content="old")
    memory.create_event_memory(session.id, "old event", 5, 0.9, turn_range=(1, 1))
    history.append_message(session.id, role="user", speaker="User", content="x" * 20)

    decision = MemoryTriggerPolicy(every_turns=10, history_chars_threshold=10).should_run(
        sessions.get_by_id(session.id),
        history.list_messages(session.id),
        memory.list_memories(session.id, limit=None),
    )

    assert decision.triggered is True
    assert decision.reason == "history_chars_threshold"
    assert decision.start_turn == 2
    assert decision.end_turn == 2


def test_trigger_policy_uses_session_processed_turn_checkpoint(tmp_path: Path):
    _, sessions, history, memory, _, _ = make_services(tmp_path)
    session = sessions.get_or_create("origin:1", None)
    for index in range(4):
        history.append_message(session.id, role="user", speaker="User", content=f"turn {index + 1}")
    session.memory_processed_turn = 4
    sessions.save_session_state(session)

    decision = MemoryTriggerPolicy(every_turns=1, history_chars_threshold=1).should_run(
        sessions.get_by_id(session.id),
        history.list_messages(session.id),
        memory.list_memories(session.id, limit=None),
    )

    assert decision.triggered is False
    assert decision.reason == "no_new_turns"


def test_parse_memory_extraction_accepts_fenced_json_and_normal_json():
    normal = parse_memory_extraction(
        '{"summary":"Alice has a key.","state":{"location":"library"},"events":[{"content":"Alice found a key.","importance":7,"confidence":0.8,"source_message_ids":["m1"],"turn_range":[1,2]}]}'
    )
    fenced = parse_memory_extraction(
        """```json
{"summary":"Bob arrived.","state":{},"events":[{"content":"Bob arrived.","source_message_ids":["m2"],"turn_range":[3,3]}]}
```"""
    )

    assert normal.ok is True
    assert normal.summary == "Alice has a key."
    assert normal.events[0]["turn_range"] == (1, 2)
    assert fenced.ok is True
    assert fenced.events[0]["content"] == "Bob arrived."
    assert fenced.events[0]["source_message_ids"] == ["m2"]


def test_parse_memory_extraction_rejects_unusable_output_with_error():
    invalid = parse_memory_extraction("not json")
    missing_content = parse_memory_extraction(
        '{"events":[{"content":"","source_message_ids":[],"turn_range":[1,1]}]}'
    )
    bad_score = parse_memory_extraction(
        '{"events":[{"content":"memory","importance":"high","confidence":"likely","source_message_ids":[],"turn_range":[1,1]}]}'
    )

    assert invalid.ok is False
    assert "invalid_json" in invalid.error
    assert missing_content.ok is False
    assert "content" in missing_content.error
    assert bad_score.ok is False
    assert "numeric" in bad_score.error


def test_merge_state_confidence_wrapped_values_and_plain_values(tmp_path: Path):
    _, _, _, _, _, extractor = make_services(tmp_path)

    merged = extractor.merge_state(
        {"location": "hall", "mood": "calm", "hp": 10},
        {
            "location": {"value": "library", "confidence": 0.9},
            "mood": {"value": "angry", "confidence": 0.3},
            "hp": 8,
            "quest": {"value": "find key", "confidence": 0.65},
        },
    )

    assert merged == {
        "location": "library",
        "mood": "calm",
        "hp": 8,
        "quest": "find key",
    }
