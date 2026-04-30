from pathlib import Path

import pytest

from smarter_rp.models import AccountProfile, Character, Lorebook, LorebookEntry, MemoryHit, MemoryRetrievalResult, RpSession
from smarter_rp.services.lorebook_matcher import LorebookMatcher
from smarter_rp.services.lorebook_service import LorebookService
from smarter_rp.services.memory_retrieval import MemoryRetriever
from smarter_rp.services.memory_service import MemoryService
from smarter_rp.services.session_service import SessionService
from smarter_rp.services.tool_service import ToolService
from smarter_rp.storage import Storage


class NamedTool:
    def __init__(self, name):
        self.name = name


class FuncNamedTool:
    def __init__(self, func_name):
        self.func_name = func_name


class ToolNamedTool:
    def __init__(self, tool_name):
        self.tool_name = tool_name


class FunctionDictTool:
    def __init__(self, name):
        self.function = {"name": name}


class StubMemoryRetriever:
    def retrieve(self, session, current_input, history_messages, lore_hits):
        assert session.id == "session_1"
        assert current_input == "silver gate"
        return MemoryRetrievalResult(
            hits=[MemoryHit("memory_1", "Alice found the silver key.", 3, 0.8, 2.5, "keyword")]
        )


def names(tools):
    return [ToolService().extract_tool_name(tool) for tool in tools]


def make_session(**kwargs):
    values = {
        "id": "session_1",
        "unified_msg_origin": "origin",
        "account_profile_id": "profile_1",
        "turn_count": 1,
    }
    values.update(kwargs)
    return RpSession(**values)


def make_profile(**kwargs):
    values = {
        "id": "profile_1",
        "adapter_name": "aiocqhttp",
        "platform": "qq",
        "account_id": "10000",
        "default_lorebook_ids": [],
    }
    values.update(kwargs)
    return AccountProfile(**values)


def make_character(**kwargs):
    values = {"id": "char_1", "name": "Alice", "linked_lorebook_ids": []}
    values.update(kwargs)
    return Character(**values)


def make_services(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    sessions = SessionService(storage)
    lorebooks = LorebookService(storage)
    memories = MemoryService(storage, sessions)
    return storage, sessions, lorebooks, memories


def test_keep_all_mode_preserves_existing_tools_and_adds_rp_tools_without_duplicates():
    service = ToolService()
    tools = [{"name": "normal"}, {"name": "sc_roll_dice"}, NamedTool("other")]

    final_tools, debug = service.filter_tools(tools, mode="keep_all")

    assert names(final_tools) == ["normal", "sc_roll_dice", "other", "sc_query_lorebook", "sc_search_memory"]
    assert debug["mode"] == "keep_all"
    assert debug["original_names"] == ["normal", "sc_roll_dice", "other"]
    assert debug["final_names"] == names(final_tools)


def test_default_keep_subagents_only_preserves_transfer_whitelist_and_filters_others():
    service = ToolService(whitelist=["allowed_tool"])
    tools = [
        {"name": "normal"},
        {"name": "transfer_to_writer"},
        NamedTool("allowed_tool"),
        FuncNamedTool("other_func"),
    ]

    final_tools, debug = service.filter_tools(tools)

    assert names(final_tools) == ["transfer_to_writer", "allowed_tool"]
    assert debug["mode"] == "keep_subagents_only"
    assert {item["name"]: item["reason"] for item in debug["decisions"]} == {
        "normal": "filtered",
        "transfer_to_writer": "subagent",
        "allowed_tool": "whitelist",
        "other_func": "filtered",
    }


def test_rp_tools_only_mode_returns_only_rp_tools_and_dedupes_existing_rp_tool():
    service = ToolService()
    tools = [{"name": "normal"}, {"name": "sc_roll_dice"}, {"name": "transfer_to_writer"}]

    final_tools, _debug = service.filter_tools(tools, mode="rp_tools_only")

    assert names(final_tools) == ["sc_roll_dice", "sc_query_lorebook", "sc_search_memory"]


def test_whitelist_mode_keeps_only_requested_names():
    service = ToolService()
    tools = [{"name": "normal"}, ToolNamedTool("allowed"), {"func_name": "also_allowed"}]

    final_tools, _debug = service.filter_tools(tools, mode="whitelist", whitelist=["allowed", "also_allowed"])

    assert names(final_tools) == ["allowed", "also_allowed"]


def test_whitelist_mode_injects_requested_rp_tools():
    service = ToolService()

    final_tools, debug = service.filter_tools([], mode="whitelist", whitelist=["sc_roll_dice", "normal"])

    assert names(final_tools) == ["sc_roll_dice"]
    assert debug["decisions"] == [{"name": "sc_roll_dice", "kept": True, "reason": "rp_tool"}]


def test_mcp_preservation_is_optional_in_default_mode():
    service = ToolService()
    tools = [{"name": "mcp__filesystem__read_file"}, {"name": "normal"}, {"name": "admin.delete"}]

    without_mcp, _ = service.filter_tools(tools, preserve_mcp=False)
    with_mcp, debug = service.filter_tools(tools, preserve_mcp=True)

    assert names(without_mcp) == []
    assert names(with_mcp) == ["mcp__filesystem__read_file"]
    assert debug["decisions"][0]["reason"] == "mcp"
    assert debug["decisions"][2]["reason"] == "filtered"


def test_duplicate_tool_names_preserve_first_occurrence():
    service = ToolService()
    first = {"name": "transfer_to_writer", "version": 1}
    second = {"name": "transfer_to_writer", "version": 2}

    final_tools, debug = service.filter_tools([first, second])

    assert final_tools == [first]
    assert debug["decisions"][1]["reason"] == "duplicate"


def test_robust_name_extraction_supports_dict_and_object_variants():
    service = ToolService()

    assert service.extract_tool_name({"name": "dict_name"}) == "dict_name"
    assert service.extract_tool_name({"function": {"name": "dict_function_name"}}) == "dict_function_name"
    assert service.extract_tool_name(NamedTool("object_name")) == "object_name"
    assert service.extract_tool_name(FuncNamedTool("func_name")) == "func_name"
    assert service.extract_tool_name(ToolNamedTool("tool_name")) == "tool_name"
    assert service.extract_tool_name(FunctionDictTool("object_function_name")) == "object_function_name"


def test_roll_dice_is_deterministic_with_seed_and_returns_parts():
    service = ToolService()

    first = service.roll_dice("2d6+3", seed=123)
    second = service.roll_dice("2d6+3", seed=123)

    assert first == second
    assert first["expression"] == "2d6+3"
    assert first["count"] == 2
    assert first["sides"] == 6
    assert first["modifier"] == 3
    assert len(first["rolls"]) == 2
    assert first["total"] == sum(first["rolls"]) + 3


@pytest.mark.parametrize("expression", ["20", "0d6", "101d6", "2d1", "2d1001", "2d6+100001", "not dice"])
def test_roll_dice_rejects_invalid_or_unreasonable_expressions(expression):
    with pytest.raises(ValueError):
        ToolService().roll_dice(expression)


def test_query_lorebook_uses_session_ids_before_profile_defaults_and_adds_character_linked_ids(tmp_path: Path):
    _storage, _sessions, lorebooks, _memories = make_services(tmp_path)
    lorebooks.create_lorebook(Lorebook("profile_book", "Profile Book"))
    lorebooks.create_lorebook(Lorebook("session_book", "Session Book"))
    lorebooks.create_lorebook(Lorebook("character_book", "Character Book"))
    lorebooks.create_entry(LorebookEntry("profile_entry", "profile_book", "Profile", "Profile lore", keys=["silver"]))
    lorebooks.create_entry(LorebookEntry("session_entry", "session_book", "Session", "Session lore", keys=["silver"]))
    lorebooks.create_entry(LorebookEntry("character_entry", "character_book", "Character", "Character lore", keys=["silver"]))
    service = ToolService(lorebook_service=lorebooks, lorebook_matcher=LorebookMatcher())

    result = service.query_lorebook(
        profile=make_profile(default_lorebook_ids=["profile_book"]),
        session=make_session(active_lorebook_ids=["session_book"]),
        character=make_character(linked_lorebook_ids=["character_book"]),
        current_input="open the silver gate",
        history_messages=[],
    )

    assert result["active_lorebook_ids"] == ["session_book", "character_book"]
    assert [hit["entry_id"] for hit in result["hits"]] == ["character_entry", "session_entry"]
    assert result["hits"][0]["matched_key"] == "silver"
    assert result["hits"][0]["source"] == "searchable_text"


def test_query_lorebook_uses_profile_defaults_when_session_has_no_active_ids(tmp_path: Path):
    _storage, _sessions, lorebooks, _memories = make_services(tmp_path)
    lorebooks.create_lorebook(Lorebook("profile_book", "Profile Book"))
    lorebooks.create_entry(LorebookEntry("profile_entry", "profile_book", "Profile", "Profile lore", keys=["silver"]))
    service = ToolService(lorebook_service=lorebooks, lorebook_matcher=LorebookMatcher())

    result = service.query_lorebook(
        profile=make_profile(default_lorebook_ids=["profile_book"]),
        session=make_session(),
        character=make_character(),
        current_input="silver",
        history_messages=[],
    )

    assert result["active_lorebook_ids"] == ["profile_book"]
    assert result["hits"][0]["entry_id"] == "profile_entry"


def test_search_memory_returns_relevant_hit_from_injected_retriever():
    service = ToolService(memory_retriever=StubMemoryRetriever())

    result = service.search_memory(make_session(), "silver gate", [], lore_hits=None)

    assert result == {
        "hits": [
            {
                "memory_id": "memory_1",
                "content": "Alice found the silver key.",
                "score": 2.5,
                "reason": "keyword",
                "importance": 3,
                "confidence": 0.8,
            }
        ],
        "available": True,
    }


def test_search_memory_can_use_existing_memory_retriever(tmp_path: Path):
    _storage, sessions, _lorebooks, memories = make_services(tmp_path)
    session = sessions.get_or_create("origin:memory", "profile_1")
    memories.create_event_memory(session.id, "Alice found the silver key.", importance=5, confidence=0.9)
    service = ToolService(memory_retriever=MemoryRetriever(memories, min_importance=1))

    result = service.search_memory(session, "silver key", [], lore_hits=[])

    assert result["hits"][0]["content"] == "Alice found the silver key."
    assert result["hits"][0]["reason"] == "keyword"
