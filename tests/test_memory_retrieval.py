from pathlib import Path

from smarter_rp.models import LorebookHit, RpMessage
from smarter_rp.services.memory_retrieval import MemoryRetriever
from smarter_rp.services.memory_service import MemoryService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage


def make_services(tmp_path: Path) -> tuple[Storage, SessionService, MemoryService]:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    sessions = SessionService(storage)
    memories = MemoryService(storage, sessions)
    return storage, sessions, memories


def test_keyword_fallback_ranks_by_query_overlap_then_importance_and_recency(tmp_path: Path):
    storage, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:memory", "account_1")
    low = memories.create_event_memory(session.id, "Alice found the silver door.", importance=2, confidence=0.5)
    old_high = memories.create_event_memory(session.id, "Alice found the silver lantern.", importance=8, confidence=0.5)
    recent_high = memories.create_event_memory(session.id, "Alice found the silver map.", importance=8, confidence=0.5)
    best_overlap = memories.create_event_memory(session.id, "Alice found the silver key under the gate.", importance=3, confidence=0.5)
    storage.execute("UPDATE memories SET updated_at = ? WHERE id = ?", (100, old_high.id))
    storage.execute("UPDATE memories SET updated_at = ? WHERE id = ?", (200, recent_high.id))

    result = MemoryRetriever(memories, min_importance=1, max_hits=10).retrieve(
        session,
        current_input="Alice uses the silver key at the gate",
        history_messages=[],
        lore_hits=[],
    )

    assert [hit.memory_id for hit in result.hits] == [
        best_overlap.id,
        recent_high.id,
        old_high.id,
        low.id,
    ]
    assert result.debug["mode"] == "keyword"


def test_query_includes_current_input_recent_visible_history_and_lore_hits(tmp_path: Path):
    _storage, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:query", "account_1")
    memory = memories.create_event_memory(session.id, "dragon bridge oath", importance=5, confidence=0.9)
    history = [
        RpMessage("m1", session.id, "user", "Hero", "old hidden dragon", visible=False),
        RpMessage("m2", session.id, "user", "Hero", "dragon clue 1", visible=True),
        RpMessage("m3", session.id, "assistant", "Alice", "bridge clue 2", visible=True),
        RpMessage("m4", session.id, "user", "Hero", "oath clue 3", visible=True),
        RpMessage("m5", session.id, "system", "System", "dragon system", visible=True),
        RpMessage("m6", session.id, "assistant", "Alice", "bridge clue 4", visible=True),
        RpMessage("m7", session.id, "user", "Hero", "dragon clue 5", visible=True),
    ]
    lore_hits = [LorebookHit("entry_1", "book_1", "Bridge", "ancient bridge oath", "before_history", 0, 0, "keyword")]

    result = MemoryRetriever(memories, min_importance=1).retrieve(
        session,
        current_input="find dragon",
        history_messages=history,
        lore_hits=lore_hits,
    )

    assert result.hits[0].memory_id == memory.id
    query = result.debug["query"]
    assert "find dragon" in query
    assert "dragon clue 1" not in query
    assert "dragon system" not in query
    assert "old hidden dragon" not in query
    assert "bridge clue 2" in query
    assert "oath clue 3" in query
    assert "bridge clue 4" in query
    assert "dragon clue 5" in query
    assert "ancient bridge oath" in query


def test_budget_trimming_marks_filtered_hits(tmp_path: Path):
    _storage, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:budget", "account_1")
    keep = memories.create_event_memory(session.id, "silver key", importance=5, confidence=1)
    trimmed = memories.create_event_memory(session.id, "silver gate " + "x" * 50, importance=5, confidence=1)

    result = MemoryRetriever(memories, min_importance=1, max_chars=len("silver key") + 1).retrieve(
        session,
        current_input="silver",
        history_messages=[],
        lore_hits=[],
    )

    assert [hit.memory_id for hit in result.hits] == [keep.id]
    assert [hit.memory_id for hit in result.filtered] == [trimmed.id]
    assert result.filtered[0].trimmed is True
    assert result.filtered[0].filter_reason == "budget"


def test_min_importance_filters_low_importance_memories(tmp_path: Path):
    _storage, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:min", "account_1")
    low = memories.create_event_memory(session.id, "silver key", importance=1, confidence=1)
    high = memories.create_event_memory(session.id, "silver gate", importance=3, confidence=1)

    result = MemoryRetriever(memories, min_importance=2).retrieve(
        session,
        current_input="silver",
        history_messages=[],
        lore_hits=[],
    )

    assert [hit.memory_id for hit in result.hits] == [high.id]
    assert [hit.memory_id for hit in result.filtered] == [low.id]
    assert result.filtered[0].filter_reason == "min_importance"


class StaleVectorAdapter:
    available = True

    def search(self, session_id, query, top_k):
        return [("memory_missing", 99.0)]


class PartialVectorAdapter:
    available = True

    def __init__(self, memory_id):
        self.memory_id = memory_id

    def search(self, session_id, query, top_k):
        return [(self.memory_id, 2.0)]


class ErrorVectorAdapter:
    available = True

    def search(self, session_id, query, top_k):
        raise RuntimeError("vector unavailable")


def test_vector_with_stale_results_falls_back_to_keyword(tmp_path: Path):
    _storage, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:vector-stale", "account_1")
    memory = memories.create_event_memory(session.id, "silver key", importance=5, confidence=1)

    result = MemoryRetriever(memories, min_importance=1, vector_adapter=StaleVectorAdapter()).retrieve(
        session,
        current_input="silver key",
        history_messages=[],
        lore_hits=[],
    )

    assert [hit.memory_id for hit in result.hits] == [memory.id]
    assert result.debug["mode"] == "vector+keyword_fallback"


def test_vector_partial_results_are_filled_by_keyword_without_duplicates(tmp_path: Path):
    _storage, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:vector-partial", "account_1")
    vector_hit = memories.create_event_memory(session.id, "silver key", importance=5, confidence=1)
    keyword_hit = memories.create_event_memory(session.id, "silver gate", importance=4, confidence=1)

    result = MemoryRetriever(
        memories,
        min_importance=1,
        vector_adapter=PartialVectorAdapter(vector_hit.id),
        max_hits=2,
    ).retrieve(session, "silver gate key", [], [])

    assert [hit.memory_id for hit in result.hits] == [vector_hit.id, keyword_hit.id]
    assert result.debug["mode"] == "vector+keyword_fallback"


def test_vector_error_falls_back_to_keyword(tmp_path: Path):
    _storage, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:vector-error", "account_1")
    memory = memories.create_event_memory(session.id, "silver key", importance=5, confidence=1)

    result = MemoryRetriever(memories, min_importance=1, vector_adapter=ErrorVectorAdapter()).retrieve(
        session,
        current_input="silver key",
        history_messages=[],
        lore_hits=[],
    )

    assert [hit.memory_id for hit in result.hits] == [memory.id]
    assert result.debug["mode"] == "keyword"


def test_budget_trimming_continues_to_shorter_candidates(tmp_path: Path):
    _storage, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:budget-skip", "account_1")
    too_long = memories.create_event_memory(session.id, "silver " + "x" * 50, importance=9, confidence=1)
    short = memories.create_event_memory(session.id, "silver key", importance=5, confidence=1)

    result = MemoryRetriever(memories, min_importance=1, max_chars=len("silver key") + 1).retrieve(
        session,
        current_input="silver key",
        history_messages=[],
        lore_hits=[],
    )

    assert [hit.memory_id for hit in result.hits] == [short.id]
    assert too_long.id in [hit.memory_id for hit in result.filtered]
    assert next(hit for hit in result.filtered if hit.memory_id == too_long.id).filter_reason == "budget"


class GateFirstRerankAdapter:
    available = True

    def rerank(self, query, documents, top_k):
        return [
            (document.memory_id, 10 if "gate" in document.content else 1)
            for document in documents
        ]


def test_rerank_adapter_can_reorder_candidates_when_available(tmp_path: Path):
    _storage, sessions, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:rerank", "account_1")
    first = memories.create_event_memory(session.id, "silver key", importance=5, confidence=1)
    second = memories.create_event_memory(session.id, "silver gate", importance=5, confidence=1)

    result = MemoryRetriever(
        memories,
        min_importance=1,
        rerank_adapter=GateFirstRerankAdapter(),
        rerank_top_k=10,
    ).retrieve(session, "silver", [], [])

    assert [hit.memory_id for hit in result.hits] == [second.id, first.id]
    assert result.debug["rerank"] == "adapter"
