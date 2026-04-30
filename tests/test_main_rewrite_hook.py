import asyncio
import importlib
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from smarter_rp.models import Lorebook, LorebookEntry
from smarter_rp.services.account_service import AccountService
from smarter_rp.services.character_service import CharacterService
from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.lorebook_matcher import LorebookMatcher
from smarter_rp.services.lorebook_service import LorebookService
from smarter_rp.services.memory_retrieval import MemoryRetriever
from smarter_rp.services.memory_service import MemoryService
from smarter_rp.services.prompt_builder import PromptBuilder
from smarter_rp.services.request_rewriter import RequestRewriter
from smarter_rp.services.session_service import SessionService
from smarter_rp.services.tool_service import ToolService
from smarter_rp.storage import Storage


@pytest.fixture()
def main_module(monkeypatch):
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    event_module = types.ModuleType("astrbot.api.event")
    filter_module = types.SimpleNamespace(
        command=lambda *_args, **_kwargs: (lambda func: func),
        llm_tool=lambda *_args, **_kwargs: (lambda func: func),
    )
    star_module = types.ModuleType("astrbot.api.star")

    class FakeStar:
        def __init__(self, context):
            self.context = context

    def fake_register(*_args, **_kwargs):
        return lambda cls: cls

    event_module.filter = filter_module
    star_module.Context = object
    star_module.Star = FakeStar
    star_module.register = fake_register

    monkeypatch.setitem(sys.modules, "astrbot", astrbot_module)
    monkeypatch.setitem(sys.modules, "astrbot.api", api_module)
    monkeypatch.setitem(sys.modules, "astrbot.api.event", event_module)
    monkeypatch.setitem(sys.modules, "astrbot.api.star", star_module)
    sys.modules.pop("main", None)
    return importlib.import_module("main")


class FailingMemoryExtractor:
    def run_if_needed(self, *_args):
        raise RuntimeError("boom")


class FakeRewriter:
    def __init__(self):
        self.calls = []

    def rewrite(self, event, req):
        self.calls.append((event, req))
        req.system_prompt = "rewritten by fake"
        return SimpleNamespace(rewritten=True, reason="rewritten")


def run_llm_request(plugin, event, req):
    return asyncio.run(plugin.on_llm_request(event, req))


def collect_async_generator(async_generator):
    async def collect():
        return [item async for item in async_generator]

    return asyncio.run(collect())


def make_real_plugin(main_module, tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    plugin = object.__new__(main_module.SmarterRpPlugin)
    plugin.storage = storage
    plugin.accounts = AccountService(storage)
    plugin.sessions = SessionService(storage)
    plugin.characters = CharacterService(storage)
    plugin.characters.ensure_default_character()
    plugin.history = HistoryService(storage, plugin.sessions, max_history_messages=40)
    plugin.lorebooks = LorebookService(storage)
    plugin.lorebook_matcher = LorebookMatcher()
    plugin.memory = MemoryService(storage, plugin.sessions)
    plugin.memory_retriever = MemoryRetriever(plugin.memory)
    plugin.prompt_builder = PromptBuilder(max_prompt_chars=4000)
    plugin.debug = DebugService(storage)
    plugin.tool_service = ToolService(
        lorebook_service=plugin.lorebooks,
        lorebook_matcher=plugin.lorebook_matcher,
        memory_retriever=plugin.memory_retriever,
    )
    plugin.rewriter = RequestRewriter(
        accounts=plugin.accounts,
        sessions=plugin.sessions,
        characters=plugin.characters,
        prompt_builder=plugin.prompt_builder,
        debug=plugin.debug,
        history=plugin.history,
        lorebooks=plugin.lorebooks,
        lorebook_matcher=plugin.lorebook_matcher,
        memory_retriever=plugin.memory_retriever,
        tool_service=plugin.tool_service,
    )
    return plugin


def make_event():
    return SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:1",
    )


def make_request():
    return SimpleNamespace(
        prompt="Hello",
        system_prompt="old",
        contexts=["old context"],
        tools=[{"name": "transfer_to_agent"}],
        image_urls=["img"],
    )


def test_on_llm_request_delegates_to_request_rewriter(main_module):
    plugin = object.__new__(main_module.SmarterRpPlugin)
    plugin.rewriter = FakeRewriter()
    event = make_event()
    req = make_request()

    result = run_llm_request(plugin, event, req)

    assert result is None
    assert plugin.rewriter.calls == [(event, req)]
    assert req.system_prompt == "rewritten by fake"


def test_on_llm_request_active_request_rewrites(main_module, tmp_path):
    plugin = make_real_plugin(main_module, tmp_path)
    event = make_event()
    req = make_request()

    run_llm_request(plugin, event, req)

    assert "Smarter RP" in req.system_prompt
    assert req.contexts == []
    assert req.prompt == "Hello"
    assert req.tools == [{"name": "transfer_to_agent"}]
    assert req.image_urls == ["img"]


def test_on_llm_request_account_disabled_passes_unchanged(main_module, tmp_path):
    plugin = make_real_plugin(main_module, tmp_path)
    event = make_event()
    profile = plugin.accounts.get_or_create(plugin.accounts.extract_identity(event))
    plugin.accounts.update_profile(profile.id, default_enabled=False)
    req = make_request()

    run_llm_request(plugin, event, req)

    assert req.system_prompt == "old"
    assert req.contexts == ["old context"]
    assert req.prompt == "Hello"
    assert req.tools == [{"name": "transfer_to_agent"}]
    assert req.image_urls == ["img"]


def test_on_llm_request_session_paused_passes_unchanged(main_module, tmp_path):
    plugin = make_real_plugin(main_module, tmp_path)
    event = make_event()
    profile = plugin.accounts.get_or_create(plugin.accounts.extract_identity(event))
    session = plugin.sessions.get_or_create(event.unified_msg_origin, profile.id)
    plugin.sessions.set_paused(session.id, True)
    req = make_request()

    run_llm_request(plugin, event, req)

    assert req.system_prompt == "old"
    assert req.contexts == ["old context"]
    assert req.prompt == "Hello"
    assert req.tools == [{"name": "transfer_to_agent"}]
    assert req.image_urls == ["img"]


class FakeProvider:
    def __init__(self):
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return '{"summary":"sum","state":{},"events":[]}'


def test_resolve_memory_provider_uses_configured_provider(main_module, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.SmarterRpPlugin, "_resolve_data_dir", lambda self: tmp_path)
    provider = FakeProvider()
    context = SimpleNamespace(provider_manager=SimpleNamespace(providers={"memory_provider": provider}))
    plugin = main_module.SmarterRpPlugin(
        context,
        {"webui": {"enabled": False}, "memory": {"memory_provider_id": "memory_provider"}},
    )

    resolved = plugin._resolve_memory_provider()

    assert resolved is not None
    assert resolved.complete("prompt") == '{"summary":"sum","state":{},"events":[]}'
    assert provider.prompts == ["prompt"]


def test_forget_memory_task_does_not_remove_newer_task(main_module, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.SmarterRpPlugin, "_resolve_data_dir", lambda self: tmp_path)
    plugin = main_module.SmarterRpPlugin(object(), {"webui": {"enabled": False}})
    old_task = SimpleNamespace()
    new_task = SimpleNamespace()
    plugin._memory_tasks["session_1"] = new_task

    plugin._forget_memory_task("session_1", old_task)

    assert plugin._memory_tasks["session_1"] is new_task


def test_schedule_memory_job_ignores_stopping_plugin(main_module, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.SmarterRpPlugin, "_resolve_data_dir", lambda self: tmp_path)
    plugin = main_module.SmarterRpPlugin(object(), {"webui": {"enabled": False}})
    plugin._stopping = True

    plugin._schedule_memory_job("session_1")

    assert plugin._memory_tasks == {}


def test_memory_background_error_snapshot_uses_json_envelope(main_module, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.SmarterRpPlugin, "_resolve_data_dir", lambda self: tmp_path)
    plugin = main_module.SmarterRpPlugin(object(), {"webui": {"enabled": False}})
    plugin.memory_extractor = FailingMemoryExtractor()

    asyncio.run(plugin._run_memory_job("session_1"))

    snapshots = plugin.debug.list_snapshots(session_id="session_1", snapshot_type="memory")
    assert snapshots
    payload = json.loads(snapshots[0].content)
    assert payload == {"error": "boom", "kind": "background", "status": "error"}


def test_on_using_llm_tool_saves_started_tool_snapshot(main_module, tmp_path):
    plugin = make_real_plugin(main_module, tmp_path)
    event = SimpleNamespace(unified_msg_origin="origin:tool", tool_name="sc_roll_dice", arguments={"token": "secret", "expression": "d20"})

    asyncio.run(plugin.on_using_llm_tool(event))

    session = plugin.sessions.get_or_create("origin:tool", None)
    snapshots = plugin.debug.list_snapshots(session_id=session.id, snapshot_type="tools")
    assert len(snapshots) == 1
    payload = json.loads(snapshots[0].content)
    assert payload["kind"] == "tool_call"
    assert payload["status"] == "started"
    assert payload["tool_name"] == "sc_roll_dice"
    assert payload["arguments_preview"] == "{'token': '[REDACTED]', 'expression': 'd20'}"


def test_on_llm_tool_respond_saves_completed_or_error_tool_snapshot(main_module, tmp_path):
    plugin = make_real_plugin(main_module, tmp_path)
    completed = SimpleNamespace(unified_msg_origin="origin:tool", tool_name="sc_roll_dice", result={"total": 12})
    errored = SimpleNamespace(unified_msg_origin="origin:tool", tool_name="sc_roll_dice", error=RuntimeError("boom"))

    asyncio.run(plugin.on_llm_tool_respond(completed))
    asyncio.run(plugin.on_llm_tool_respond(errored))

    session = plugin.sessions.get_or_create("origin:tool", None)
    snapshots = plugin.debug.list_snapshots(session_id=session.id, snapshot_type="tools")
    payloads = [json.loads(snapshot.content) for snapshot in snapshots]
    statuses = {payload["status"] for payload in payloads}
    assert statuses == {"completed", "error"}
    assert any(payload.get("result_preview") == "{'total': 12}" for payload in payloads)
    assert any(payload.get("error_preview") == "RuntimeError('boom')" for payload in payloads)


def test_sc_roll_dice_tool_returns_plain_result_json(main_module, tmp_path):
    plugin = make_real_plugin(main_module, tmp_path)
    event = SimpleNamespace(plain_result=lambda text: text)

    results = collect_async_generator(plugin.sc_roll_dice(event, "2d6+3", seed="seed"))

    assert len(results) == 1
    payload = json.loads(results[0])
    assert payload["expression"] == "2d6+3"
    assert payload["total"] == sum(payload["rolls"]) + 3


def test_sc_query_lorebook_tool_uses_active_session_context(main_module, tmp_path):
    plugin = make_real_plugin(main_module, tmp_path)
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:lore-tool",
        plain_result=lambda text: text,
    )
    profile = plugin.accounts.get_or_create(plugin.accounts.extract_identity(event))
    session = plugin.sessions.get_or_create(event.unified_msg_origin, profile.id)
    plugin.lorebooks.create_lorebook(Lorebook("book_1", "Book"))
    plugin.lorebooks.create_entry(LorebookEntry("entry_1", "book_1", "Gate", "Silver gate lore", keys=["silver"]))
    session.active_lorebook_ids = ["book_1"]
    plugin.sessions.save_session_state(session)

    results = collect_async_generator(plugin.sc_query_lorebook(event, "silver gate"))

    payload = json.loads(results[0])
    assert payload["available"] is True
    assert payload["hits"][0]["entry_id"] == "entry_1"


def test_sc_search_memory_tool_uses_active_session_context(main_module, tmp_path):
    plugin = make_real_plugin(main_module, tmp_path)
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:memory-tool",
        plain_result=lambda text: text,
    )
    profile = plugin.accounts.get_or_create(plugin.accounts.extract_identity(event))
    session = plugin.sessions.get_or_create(event.unified_msg_origin, profile.id)
    plugin.memory.create_event_memory(session.id, "Alice found the silver key.", importance=5, confidence=0.9)

    results = collect_async_generator(plugin.sc_search_memory(event, "silver key"))

    payload = json.loads(results[0])
    assert payload["available"] is True
    assert payload["hits"][0]["content"] == "Alice found the silver key."


def test_tool_trace_hooks_support_dict_and_nested_event_shapes(main_module, tmp_path):
    plugin = make_real_plugin(main_module, tmp_path)
    started = {
        "event": {"unified_msg_origin": "origin:nested-tool"},
        "tool_call": {"name": "sc_roll_dice"},
        "arguments": {"token": "secret", "expression": "d20"},
    }
    completed = {
        "event": {"unified_msg_origin": "origin:nested-tool"},
        "function": {"name": "sc_roll_dice"},
        "result": {"api_key": "sk-secret", "total": 12},
    }

    asyncio.run(plugin.on_using_llm_tool(started))
    asyncio.run(plugin.on_llm_tool_respond(completed))

    session = plugin.sessions.get_or_create("origin:nested-tool", None)
    snapshots = plugin.debug.list_snapshots(session_id=session.id, snapshot_type="tools")
    payloads = [json.loads(snapshot.content) for snapshot in snapshots]
    assert {payload["status"] for payload in payloads} == {"started", "completed"}
    assert {payload["tool_name"] for payload in payloads} == {"sc_roll_dice"}
    combined = json.dumps(payloads)
    assert "secret" not in combined
    assert "sk-secret" not in combined
    assert "[REDACTED]" in combined


def test_tool_trace_hooks_ignore_unusual_event_shapes(main_module, tmp_path):
    plugin = make_real_plugin(main_module, tmp_path)

    asyncio.run(plugin.on_using_llm_tool(object()))
    asyncio.run(plugin.on_llm_tool_respond(object()))

    assert plugin.debug.list_snapshots(snapshot_type="tools")


def test_init_wires_rewriter_services_with_storage(main_module, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.SmarterRpPlugin, "_resolve_data_dir", lambda self: tmp_path)

    plugin = main_module.SmarterRpPlugin(object(), {"webui": {"enabled": False}})

    assert isinstance(plugin.accounts, AccountService)
    assert isinstance(plugin.characters, CharacterService)
    assert isinstance(plugin.history, HistoryService)
    assert isinstance(plugin.prompt_builder, PromptBuilder)
    assert isinstance(plugin.rewriter, RequestRewriter)
    assert isinstance(plugin.tool_service, ToolService)
    assert plugin.accounts.storage is plugin.storage
    assert plugin.characters.storage is plugin.storage
    assert plugin.history.storage is plugin.storage
    assert plugin.history.sessions is plugin.sessions
    assert plugin.history.max_history_messages == 40
    assert plugin.rewriter.accounts is plugin.accounts
    assert plugin.rewriter.sessions is plugin.sessions
    assert plugin.rewriter.characters is plugin.characters
    assert plugin.rewriter.prompt_builder is plugin.prompt_builder
    assert plugin.rewriter.debug is plugin.debug
    assert plugin.rewriter.history is plugin.history
    assert plugin.rewriter.tool_service is plugin.tool_service
    assert plugin.tool_service.lorebook_service is plugin.lorebooks
    assert plugin.tool_service.lorebook_matcher is plugin.lorebook_matcher
    assert plugin.tool_service.memory_retriever is plugin.memory_retriever
    assert plugin.tool_service.mode == "keep_subagents_only"
    assert plugin.tool_service.whitelist == []
    assert plugin.tool_service.preserve_mcp is False
    assert plugin.characters.list_characters()
