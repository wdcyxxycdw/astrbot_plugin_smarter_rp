import json
from pathlib import Path
from types import SimpleNamespace

from smarter_rp.models import MemoryHit, MemoryRetrievalResult
from smarter_rp.services.account_service import AccountService
from smarter_rp.services.character_service import CharacterService
from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.prompt_builder import PromptBuilder
from smarter_rp.services.request_rewriter import RequestRewriter
from smarter_rp.services.session_service import SessionService
from smarter_rp.services.tool_service import ToolService
from smarter_rp.storage import Storage


def make_rewriter(tmp_path: Path) -> tuple[RequestRewriter, Storage]:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    rewriter = RequestRewriter(
        accounts=AccountService(storage),
        sessions=SessionService(storage),
        characters=CharacterService(storage),
        prompt_builder=PromptBuilder(max_prompt_chars=4000),
        debug=DebugService(storage),
    )
    return rewriter, storage


def test_rewrite_preserves_original_system_prompt_and_appends_configured_global_prompt(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    rewriter = RequestRewriter(
        accounts=AccountService(storage),
        sessions=SessionService(storage),
        characters=CharacterService(storage),
        prompt_builder=PromptBuilder(max_prompt_chars=4000, global_prompt="Custom global directive"),
        debug=DebugService(storage),
    )
    event = SimpleNamespace(adapter_name="adapter", platform="platform", account_id="bot", unified_msg_origin="origin:preserve")
    request = SimpleNamespace(prompt="Hello", system_prompt="Original AstrBot system prompt", contexts=[])

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert request.system_prompt.startswith("Original AstrBot system prompt\n\n[Smarter RP]\n")
    assert "[Global RP System Rules]\nCustom global directive" in request.system_prompt
    assert request.system_prompt.index("Original AstrBot system prompt") < request.system_prompt.index("[Smarter RP]")


def test_rewrite_without_original_system_prompt_still_sets_smarter_rp_prompt(tmp_path: Path):
    rewriter, _ = make_rewriter(tmp_path)
    event = SimpleNamespace(adapter_name="adapter", platform="platform", account_id="bot", unified_msg_origin="origin:empty-system")
    request = SimpleNamespace(prompt="Hello", contexts=[])

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert request.system_prompt.startswith("[Smarter RP]\n")
    assert "[Global RP System Rules]" in request.system_prompt


def test_rewrite_default_active_session_mutates_prompt(tmp_path: Path):
    rewriter, _ = make_rewriter(tmp_path)
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:1",
    )
    request = SimpleNamespace(
        prompt="Hello",
        system_prompt="old",
        contexts=["old context"],
        tools=[{"name": "transfer_to_agent"}],
        image_urls=["img"],
    )

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert result.reason == "rewritten"
    assert result.account_profile_id is not None
    assert result.session_id is not None
    assert "Smarter RP" in request.system_prompt
    assert request.contexts == []
    assert request.prompt == "Hello"
    assert request.image_urls == ["img"]
    assert request.tools == [{"name": "transfer_to_agent"}]


class FakeMemoryRetriever:
    def retrieve(self, *_args):
        return MemoryRetrievalResult(
            hits=[
                MemoryHit(
                    memory_id="memory_1",
                    content="Alice remembers the silver key.",
                    importance=5,
                    confidence=0.9,
                    score=1.0,
                    reason="keyword",
                )
            ],
            debug={"query": "Hello", "candidate_count": 1},
        )


def test_rewrite_uses_temp_extra_user_content_parts_when_available(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    sessions = SessionService(storage)
    history = HistoryService(storage, sessions)
    rewriter = RequestRewriter(
        accounts=AccountService(storage),
        sessions=sessions,
        characters=CharacterService(storage),
        prompt_builder=PromptBuilder(max_prompt_chars=4000),
        debug=DebugService(storage),
        history=history,
        memory_retriever=FakeMemoryRetriever(),
    )
    event = SimpleNamespace(adapter_name="adapter", platform="platform", account_id="bot", unified_msg_origin="origin:temp")
    session = sessions.get_or_create("origin:temp", None)
    history.append_message(session.id, role="user", speaker="Hero", content="Found a door")
    request = SimpleNamespace(prompt="Hello", system_prompt="old", contexts=[], extra_user_content_parts=[])

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert request.contexts == [{"role": "user", "content": "Found a door"}]
    assert request.prompt == "Hello"
    assert len(request.extra_user_content_parts) == 1
    part = request.extra_user_content_parts[0]
    assert part.__class__.__name__ == "FakeTextPart"
    assert part.marked_temp is True
    assert "Alice remembers the silver key." in part.text
    assert "Current Input" in part.text
    assert "Alice remembers the silver key." not in request.system_prompt
    assert "Current Input" not in request.system_prompt


def test_rewrite_filters_tools_and_saves_tools_debug_snapshot(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    rewriter = RequestRewriter(
        accounts=AccountService(storage),
        sessions=SessionService(storage),
        characters=CharacterService(storage),
        prompt_builder=PromptBuilder(max_prompt_chars=4000),
        debug=DebugService(storage),
        tool_service=ToolService(mode="rp_tools_only"),
    )
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:tools",
    )
    request = SimpleNamespace(
        prompt="Hello",
        system_prompt="old",
        contexts=[],
        tools=[{"name": "normal"}, {"name": "sc_roll_dice"}],
    )

    result = rewriter.rewrite(event, request)

    assert [tool["name"] for tool in request.tools] == ["sc_roll_dice", "sc_query_lorebook", "sc_search_memory"]
    assert "Available RP tools:" in request.system_prompt
    assert request.prompt == "Hello"
    snapshots = DebugService(storage).list_snapshots(session_id=result.session_id, snapshot_type="tools")
    assert len(snapshots) == 1
    payload = json.loads(snapshots[0].content)
    assert payload["kind"] == "request_tools"
    assert payload["status"] == "completed"
    assert payload["field"] == "tools"
    assert payload["final_names"] == ["sc_roll_dice", "sc_query_lorebook", "sc_search_memory"]


def test_rewrite_filters_func_tool_without_inventing_tools_field(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    rewriter = RequestRewriter(
        accounts=AccountService(storage),
        sessions=SessionService(storage),
        characters=CharacterService(storage),
        prompt_builder=PromptBuilder(max_prompt_chars=4000),
        debug=DebugService(storage),
        tool_service=ToolService(mode="keep_subagents_only"),
    )
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:func-tools",
    )
    request = SimpleNamespace(
        prompt="Hello",
        system_prompt="old",
        contexts=[],
        func_tool=[{"name": "normal"}, {"name": "transfer_to_agent"}],
    )

    result = rewriter.rewrite(event, request)

    assert request.func_tool == [{"name": "transfer_to_agent"}]
    assert not hasattr(request, "tools")
    assert "Available RP tools:" not in request.system_prompt
    snapshots = DebugService(storage).list_snapshots(session_id=result.session_id, snapshot_type="tools")
    payload = json.loads(snapshots[0].content)
    assert payload["field"] == "func_tool"
    assert payload["final_names"] == ["transfer_to_agent"]


def test_rewrite_filters_tools_and_func_tool_when_both_exist(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    rewriter = RequestRewriter(
        accounts=AccountService(storage),
        sessions=SessionService(storage),
        characters=CharacterService(storage),
        prompt_builder=PromptBuilder(max_prompt_chars=4000),
        debug=DebugService(storage),
        tool_service=ToolService(mode="keep_subagents_only"),
    )
    event = SimpleNamespace(adapter_name="adapter", platform="platform", account_id="bot", unified_msg_origin="origin:both-tools")
    request = SimpleNamespace(
        prompt="Hello",
        system_prompt="old",
        contexts=[],
        tools=[{"name": "normal"}],
        func_tool=({"name": "transfer_to_writer"}, {"name": "filtered"}),
    )

    result = rewriter.rewrite(event, request)

    assert request.tools == []
    assert request.func_tool == [{"name": "transfer_to_writer"}]
    snapshots = DebugService(storage).list_snapshots(session_id=result.session_id, snapshot_type="tools")
    payloads = [json.loads(snapshot.content) for snapshot in snapshots]
    assert {payload["field"] for payload in payloads} == {"tools", "func_tool"}
    assert any(payload["final_names"] == ["transfer_to_writer"] for payload in payloads)


def test_rewrite_skips_non_list_tool_field_without_overwriting(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    rewriter = RequestRewriter(
        accounts=AccountService(storage),
        sessions=SessionService(storage),
        characters=CharacterService(storage),
        prompt_builder=PromptBuilder(max_prompt_chars=4000),
        debug=DebugService(storage),
        tool_service=ToolService(mode="keep_subagents_only"),
    )
    event = SimpleNamespace(adapter_name="adapter", platform="platform", account_id="bot", unified_msg_origin="origin:object-tools")
    tool_holder = {"name": "transfer_to_writer"}
    request = SimpleNamespace(prompt="Hello", system_prompt="old", contexts=[], tools=tool_holder)

    result = rewriter.rewrite(event, request)

    assert request.tools is tool_holder
    snapshots = DebugService(storage).list_snapshots(session_id=result.session_id, snapshot_type="tools")
    payload = json.loads(snapshots[0].content)
    assert payload["status"] == "skipped"
    assert payload["reason"] == "non_list_tool_field"
    assert payload["field"] == "tools"


def test_rewrite_without_tool_field_does_not_create_tool_snapshot_or_field(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    rewriter = RequestRewriter(
        accounts=AccountService(storage),
        sessions=SessionService(storage),
        characters=CharacterService(storage),
        prompt_builder=PromptBuilder(max_prompt_chars=4000),
        debug=DebugService(storage),
        tool_service=ToolService(mode="keep_all"),
    )
    event = SimpleNamespace(adapter_name="adapter", platform="platform", account_id="bot", unified_msg_origin="origin:no-tools")
    request = SimpleNamespace(prompt="Hello", system_prompt="old", contexts=[])

    result = rewriter.rewrite(event, request)

    assert not hasattr(request, "tools")
    assert not hasattr(request, "func_tool")
    assert DebugService(storage).list_snapshots(session_id=result.session_id, snapshot_type="tools") == []


def test_account_disabled_passes_request_unchanged(tmp_path: Path):
    rewriter, storage = make_rewriter(tmp_path)
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:1",
    )
    profile = AccountService(storage).get_or_create(AccountService(storage).extract_identity(event))
    AccountService(storage).update_profile(profile.id, default_enabled=False)
    request = SimpleNamespace(
        prompt="Hello",
        system_prompt="old",
        contexts=["old context"],
        tools=[{"name": "transfer_to_agent"}],
        image_urls=["img"],
        attachments=["file"],
    )

    result = rewriter.rewrite(event, request)

    assert result.rewritten is False
    assert result.reason == "account_disabled"
    assert result.account_profile_id == profile.id
    assert result.session_id is not None
    assert request.system_prompt == "old"
    assert request.contexts == ["old context"]
    assert request.prompt == "Hello"
    assert request.tools == [{"name": "transfer_to_agent"}]
    assert request.image_urls == ["img"]
    assert request.attachments == ["file"]


def test_session_paused_passes_request_unchanged(tmp_path: Path):
    rewriter, storage = make_rewriter(tmp_path)
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:1",
    )
    profile = AccountService(storage).get_or_create(AccountService(storage).extract_identity(event))
    session = SessionService(storage).get_or_create("origin:1", profile.id)
    SessionService(storage).set_paused(session.id, True)
    request = SimpleNamespace(
        prompt="Hello",
        system_prompt="old",
        contexts=["old context"],
        tools=[{"name": "transfer_to_agent"}],
        image_urls=["img"],
        attachments=["file"],
    )

    result = rewriter.rewrite(event, request)

    assert result.rewritten is False
    assert result.reason == "session_paused"
    assert result.account_profile_id == profile.id
    assert result.session_id == session.id
    assert request.system_prompt == "old"
    assert request.contexts == ["old context"]
    assert request.prompt == "Hello"
    assert request.tools == [{"name": "transfer_to_agent"}]
    assert request.image_urls == ["img"]
    assert request.attachments == ["file"]


def test_rewrite_populates_contexts_from_plugin_history_and_preserves_prompt(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    accounts = AccountService(storage)
    sessions = SessionService(storage)
    history = HistoryService(storage, sessions)
    rewriter = RequestRewriter(
        accounts=accounts,
        sessions=sessions,
        characters=CharacterService(storage),
        prompt_builder=PromptBuilder(max_prompt_chars=4000),
        debug=DebugService(storage),
        history=history,
    )
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:history",
    )
    profile = accounts.get_or_create(accounts.extract_identity(event))
    session = sessions.get_or_create("origin:history", profile.id)
    history.append_message(session.id, role="user", speaker="Hero", content=" Hello ")
    history.append_message(session.id, role="assistant", speaker="Alice", content="Hi back")
    history.append_message(session.id, role="system", speaker="System", content="skip this")
    request = SimpleNamespace(
        prompt="Current prompt",
        system_prompt="old",
        contexts=["old context"],
        tools=[{"name": "tool"}],
        image_urls=["img"],
        attachments=["file"],
    )

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert request.prompt == "Current prompt"
    assert request.contexts == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi back"},
    ]
    assert len(request.extra_user_content_parts) == 1
    assert request.extra_user_content_parts[0].marked_temp is True
    assert "Hero: Hello" in request.extra_user_content_parts[0].text
    assert "Alice: Hi back" in request.extra_user_content_parts[0].text
    assert "skip this" not in request.extra_user_content_parts[0].text
    assert "Hero: Hello" not in request.system_prompt
    assert request.tools == [{"name": "tool"}]
    assert request.image_urls == ["img"]
    assert request.attachments == ["file"]


def test_rewrite_saves_redacted_debug_snapshots(tmp_path: Path):
    rewriter, storage = make_rewriter(tmp_path)
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:1",
    )
    request = SimpleNamespace(
        prompt="Hello token=abc123",
        system_prompt="old Authorization: Bearer secret-token",
        contexts=["old context api_key: sk-test-value"],
        tools=[{"name": "transfer_to_agent"}],
        image_urls=["img"],
    )

    result = rewriter.rewrite(event, request)

    snapshots = storage.fetch_all(
        "SELECT type, content FROM debug_snapshots WHERE session_id = ? ORDER BY type",
        (result.session_id,),
    )
    assert {row["type"] for row in snapshots} == {"prompt", "raw_request"}
    combined = "\n".join(row["content"] for row in snapshots)
    assert "abc123" not in combined
    assert "secret-token" not in combined
    assert "sk-test-value" not in combined
    assert "[REDACTED]" in combined
    assert "prompt" in combined
    assert "system_prompt" in combined
    assert "func_tool" in combined


def test_rewrite_uses_safe_unknown_origin_fallback(tmp_path: Path):
    rewriter, _ = make_rewriter(tmp_path)
    event = SimpleNamespace(adapter_name="adapter", platform="platform", account_id="bot")
    request = SimpleNamespace(prompt=None, system_prompt="old", contexts=["old context"])

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert result.session_id is not None
    assert request.contexts == []
    assert len(request.extra_user_content_parts) == 1
    assert request.extra_user_content_parts[0].marked_temp is True
    assert "Current Input" in request.extra_user_content_parts[0].text
    assert "Current Input" not in request.system_prompt
