import json
from pathlib import Path
from types import SimpleNamespace

from smarter_rp.models import MemoryHit, MemoryRetrievalResult
from smarter_rp.services.account_service import AccountService
from smarter_rp.services.character_service import CharacterService
from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.memory_retrieval import MemoryRetriever
from smarter_rp.services.memory_service import MemoryService
from smarter_rp.services.prompt_builder import PromptBuilder
from smarter_rp.services.request_rewriter import RequestRewriter
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage


def make_stack(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    accounts = AccountService(storage)
    sessions = SessionService(storage)
    characters = CharacterService(storage)
    history = HistoryService(storage, sessions)
    debug = DebugService(storage)
    memories = MemoryService(storage, sessions)
    return storage, accounts, sessions, characters, history, debug, memories


def make_event(origin: str = "origin:memory"):
    return SimpleNamespace(adapter_name="adapter", platform="platform", account_id="bot", unified_msg_origin=origin)


def test_request_rewriter_injects_session_memory_and_persists_hits(tmp_path: Path):
    storage, accounts, sessions, characters, history, debug, memories = make_stack(tmp_path)
    event = make_event()
    profile = accounts.get_or_create(accounts.extract_identity(event))
    session = sessions.get_or_create(event.unified_msg_origin, profile.id)
    memories.update_session_memory_state(session.id, "Alice carries a silver key.", {"location": "library"})
    memory = memories.create_event_memory(session.id, "Alice promised Bob to open the silver gate.", importance=5, confidence=0.9)
    history.append_message(session.id, role="user", speaker="Hero", content="Remember Bob")
    rewriter = RequestRewriter(
        accounts,
        sessions,
        characters,
        PromptBuilder(max_prompt_chars=4000),
        debug,
        history=history,
        memory_retriever=MemoryRetriever(memories, min_importance=1),
    )
    request = SimpleNamespace(prompt="Open the silver gate", system_prompt="old", contexts=[])

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert "[Session Summary]" in request.system_prompt
    assert "Alice carries a silver key." in request.system_prompt
    assert "[Session State]" in request.system_prompt
    assert "location: library" in request.system_prompt
    assert "[Relevant Event Memories]" in request.system_prompt
    assert "Alice promised Bob to open the silver gate." in request.system_prompt
    saved = sessions.get_by_id(session.id)
    assert saved.last_memory_hits
    assert saved.last_memory_hits[0]["memory_id"] == memory.id


def test_stale_last_memory_hits_clear_when_retriever_configured_but_no_hits(tmp_path: Path):
    storage, accounts, sessions, characters, history, debug, memories = make_stack(tmp_path)
    event = make_event("origin:stale")
    profile = accounts.get_or_create(accounts.extract_identity(event))
    session = sessions.get_or_create(event.unified_msg_origin, profile.id)
    session.last_memory_hits = [{"memory_id": "old", "content": "stale", "score": 1.0}]
    sessions.save_session_state(session)
    rewriter = RequestRewriter(
        accounts,
        sessions,
        characters,
        PromptBuilder(max_prompt_chars=4000),
        debug,
        history=history,
        memory_retriever=MemoryRetriever(memories, min_importance=1),
    )
    request = SimpleNamespace(prompt="nothing relevant", system_prompt="old", contexts=[])

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert sessions.get_by_id(session.id).last_memory_hits == []
    assert "stale" not in request.system_prompt


class StaticMemoryRetriever:
    def retrieve(self, session, current_input, history_messages, lore_hits):
        return MemoryRetrievalResult(
            hits=[MemoryHit("memory_1", "debug memory content", 4, 0.8, 2.0, "test")],
            debug={"query": current_input, "candidate_count": 1, "mode": "test"},
        )


def test_debug_snapshot_type_memory_includes_retrieval_debug(tmp_path: Path):
    storage, accounts, sessions, characters, history, debug, _memories = make_stack(tmp_path)
    event = make_event("origin:debug")
    rewriter = RequestRewriter(
        accounts,
        sessions,
        characters,
        PromptBuilder(max_prompt_chars=4000),
        debug,
        history=history,
        memory_retriever=StaticMemoryRetriever(),
    )
    request = SimpleNamespace(prompt="debug query", system_prompt="old", contexts=[])

    result = rewriter.rewrite(event, request)

    snapshots = debug.list_snapshots(session_id=result.session_id, snapshot_type="memory")
    assert snapshots
    content = json.loads(snapshots[0].content)
    assert content["kind"] == "retrieval"
    assert content["status"] == "completed"
    assert content["candidate_count"] == 1
    assert content["mode"] == "test"
    assert content["query_chars"] == len("debug query")
    assert "debug query" not in snapshots[0].content
