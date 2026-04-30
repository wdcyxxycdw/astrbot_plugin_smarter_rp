import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from smarter_rp.services.history_service import HistoryService
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


def make_plugin(main_module, tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    plugin = object.__new__(main_module.SmarterRpPlugin)
    plugin.storage = storage
    plugin.sessions = SessionService(storage)
    plugin.history = HistoryService(storage, plugin.sessions, max_history_messages=40)
    return plugin


def run_agent_done(plugin, event, response):
    return asyncio.run(plugin.on_agent_done(event, response))


def list_saved(plugin, origin="origin:history"):
    session = plugin.sessions.get_or_create(origin, None)
    return plugin.history.list_messages(session.id)


def test_on_agent_done_saves_user_and_assistant_messages(main_module, tmp_path):
    plugin = make_plugin(main_module, tmp_path)
    event = SimpleNamespace(unified_msg_origin="origin:history", message_str="Hello")
    response = SimpleNamespace(completion_text="Hi there")

    result = run_agent_done(plugin, event, response)

    messages = list_saved(plugin)
    assert result is None
    assert [(message.role, message.speaker, message.content) for message in messages] == [
        ("user", "User", "Hello"),
        ("assistant", "Assistant", "Hi there"),
    ]


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (SimpleNamespace(completion_text="from completion"), "from completion"),
        (SimpleNamespace(result="from result"), "from result"),
        (SimpleNamespace(content="from content"), "from content"),
        (SimpleNamespace(text="from text"), "from text"),
        ("from string", "from string"),
    ],
)
def test_on_agent_done_extracts_assistant_text_from_supported_response_shapes(
    main_module, tmp_path, response, expected
):
    plugin = make_plugin(main_module, tmp_path)
    event = SimpleNamespace(unified_msg_origin="origin:history", message_str="Hello")

    run_agent_done(plugin, event, response)

    messages = list_saved(plugin)
    assert messages[-1].role == "assistant"
    assert messages[-1].speaker == "Assistant"
    assert messages[-1].content == expected


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (SimpleNamespace(unified_msg_origin="origin:history", message_str="from message_str", message="from message", raw_message="from raw"), "from message_str"),
        (SimpleNamespace(unified_msg_origin="origin:history", message_str="", message="from message", raw_message="from raw"), "from message"),
        (SimpleNamespace(unified_msg_origin="origin:history", message_str="", message="", raw_message="from raw"), "from raw"),
    ],
)
def test_on_agent_done_extracts_user_text_in_priority_order(main_module, tmp_path, event, expected):
    plugin = make_plugin(main_module, tmp_path)

    run_agent_done(plugin, event, "assistant")

    messages = list_saved(plugin)
    assert messages[0].role == "user"
    assert messages[0].speaker == "User"
    assert messages[0].content == expected


def test_on_agent_done_does_not_save_blank_messages(main_module, tmp_path):
    plugin = make_plugin(main_module, tmp_path)
    event = SimpleNamespace(unified_msg_origin="origin:history", message_str="", message="", raw_message="")
    response = SimpleNamespace(completion_text="", result="", content="", text="")

    run_agent_done(plugin, event, response)

    assert list_saved(plugin) == []


def test_on_agent_done_does_not_save_whitespace_only_user_text(main_module, tmp_path):
    plugin = make_plugin(main_module, tmp_path)
    event = SimpleNamespace(unified_msg_origin="origin:history", message_str="   ", message="\n\t", raw_message="  \n")

    run_agent_done(plugin, event, "assistant")

    messages = list_saved(plugin)
    assert [(message.role, message.content) for message in messages] == [("assistant", "assistant")]


def test_on_agent_done_does_not_save_whitespace_only_assistant_text(main_module, tmp_path):
    plugin = make_plugin(main_module, tmp_path)
    event = SimpleNamespace(unified_msg_origin="origin:history", message_str="user")

    run_agent_done(plugin, event, "\n\t ")

    messages = list_saved(plugin)
    assert [(message.role, message.content) for message in messages] == [("user", "user")]


def test_on_agent_done_uses_unknown_origin_when_missing(main_module, tmp_path):
    plugin = make_plugin(main_module, tmp_path)
    event = SimpleNamespace(message_str="Hello")

    run_agent_done(plugin, event, "Hi")

    messages = list_saved(plugin, "unknown")
    assert [message.content for message in messages] == ["Hello", "Hi"]
