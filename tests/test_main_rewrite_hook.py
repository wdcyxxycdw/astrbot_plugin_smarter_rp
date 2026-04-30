import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from smarter_rp.services.account_service import AccountService
from smarter_rp.services.character_service import CharacterService
from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.prompt_builder import PromptBuilder
from smarter_rp.services.request_rewriter import RequestRewriter
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage


@pytest.fixture()
def main_module(monkeypatch):
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    event_module = types.ModuleType("astrbot.api.event")
    filter_module = types.SimpleNamespace(command=lambda *_args, **_kwargs: (lambda func: func))
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


class FakeRewriter:
    def __init__(self):
        self.calls = []

    def rewrite(self, event, req):
        self.calls.append((event, req))
        req.system_prompt = "rewritten by fake"
        return SimpleNamespace(rewritten=True, reason="rewritten")


def run_llm_request(plugin, event, req):
    return asyncio.run(plugin.on_llm_request(event, req))


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
    plugin.prompt_builder = PromptBuilder(max_prompt_chars=4000)
    plugin.debug = DebugService(storage)
    plugin.rewriter = RequestRewriter(
        accounts=plugin.accounts,
        sessions=plugin.sessions,
        characters=plugin.characters,
        prompt_builder=plugin.prompt_builder,
        debug=plugin.debug,
        history=plugin.history,
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


def test_init_wires_rewriter_services_with_storage(main_module, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.SmarterRpPlugin, "_resolve_data_dir", lambda self: tmp_path)

    plugin = main_module.SmarterRpPlugin(object(), {"webui": {"enabled": False}})

    assert isinstance(plugin.accounts, AccountService)
    assert isinstance(plugin.characters, CharacterService)
    assert isinstance(plugin.history, HistoryService)
    assert isinstance(plugin.prompt_builder, PromptBuilder)
    assert isinstance(plugin.rewriter, RequestRewriter)
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
    assert plugin.characters.list_characters()
