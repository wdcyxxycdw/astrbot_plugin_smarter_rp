import asyncio
import importlib
import sys
import types
from types import SimpleNamespace

import pytest


class FakeEvent:
    def __init__(self, **attrs):
        self.results = []
        for key, value in attrs.items():
            setattr(self, key, value)

    def plain_result(self, text):
        self.results.append(text)
        return text


class FakeWebui:
    def __init__(self, port, url="http://127.0.0.1:8000/?token=secret-token", should_raise=False):
        self.port = port
        self.url = url
        self.should_raise = should_raise
        self.called = False

    def url_for_display(self):
        self.called = True
        if self.should_raise:
            raise AssertionError("url_for_display must not be called")
        return self.url


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


class FakeSessions:
    def __init__(self, session):
        self.session = session
        self.calls = []

    def get_or_create(self, unified_msg_origin, account_profile_id):
        self.calls.append((unified_msg_origin, account_profile_id))
        return self.session


class FakeDebug:
    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.calls = []

    def list_snapshots(self, **kwargs):
        self.calls.append(kwargs)
        return self.snapshots


def make_plugin(main_module, *, enabled=True, port=8000, webui=None, sessions=None, debug=None):
    plugin = object.__new__(main_module.SmarterRpPlugin)
    plugin.config_model = SimpleNamespace(webui={"enabled": enabled})
    plugin.webui = webui or FakeWebui(port)
    plugin.sessions = sessions
    plugin.debug = debug
    return plugin


async def collect_rp_result(plugin, event, subcommand):
    return [result async for result in plugin.rp_root(event, subcommand)]


async def collect_webui_result(plugin, event):
    return await collect_rp_result(plugin, event, "webui")


def run_webui_command(plugin, event):
    return asyncio.run(collect_webui_result(plugin, event))


def run_rp_command(plugin, event, subcommand):
    return asyncio.run(collect_rp_result(plugin, event, subcommand))


def test_webui_command_unknown_event_does_not_return_token_or_call_url(main_module):
    fake_webui = FakeWebui(8000, should_raise=True)
    plugin = make_plugin(main_module, webui=fake_webui)
    event = FakeEvent(unified_msg_origin="unknown:123")

    results = run_webui_command(plugin, event)

    assert results == ["请在私聊中使用 /rp webui 获取 WebUI 管理链接。"]
    assert "token=" not in results[0]
    assert fake_webui.called is False


def test_webui_command_group_event_does_not_return_token_or_call_url(main_module):
    fake_webui = FakeWebui(8000, should_raise=True)
    plugin = make_plugin(main_module, webui=fake_webui)
    event = FakeEvent(unified_msg_origin="group:123")

    results = run_webui_command(plugin, event)

    assert results == ["请在私聊中使用 /rp webui 获取 WebUI 管理链接。"]
    assert "token=" not in results[0]
    assert fake_webui.called is False


def test_webui_command_private_event_with_fixed_port_returns_full_url(main_module):
    fake_webui = FakeWebui(8000, url="http://127.0.0.1:8000/?token=secret-token")
    plugin = make_plugin(main_module, webui=fake_webui)
    event = FakeEvent(is_private=True)

    results = run_webui_command(plugin, event)

    assert results == ["Smarter RP WebUI: http://127.0.0.1:8000/?token=secret-token"]
    assert fake_webui.called is True


def test_webui_command_port_zero_does_not_return_url_even_for_private_event(main_module):
    fake_webui = FakeWebui(0, should_raise=True)
    plugin = make_plugin(main_module, webui=fake_webui)
    event = FakeEvent(is_private=True)

    results = run_webui_command(plugin, event)

    assert len(results) == 1
    assert "random port" in results[0]
    assert ":0" not in results[0]
    assert "token=" not in results[0]
    assert fake_webui.called is False


def test_webui_command_disabled_does_not_return_url(main_module):
    fake_webui = FakeWebui(8000, should_raise=True)
    plugin = make_plugin(main_module, enabled=False, webui=fake_webui)
    event = FakeEvent(is_private=True)

    results = run_webui_command(plugin, event)

    assert results == ["Smarter RP WebUI is disabled."]
    assert "token=" not in results[0]
    assert fake_webui.called is False


def test_debug_command_returns_short_session_summary_without_token(main_module):
    session = SimpleNamespace(id="session_1", paused=True)
    snapshot = SimpleNamespace(id="debug_prompt_1")
    sessions = FakeSessions(session)
    debug = FakeDebug([snapshot])
    plugin = make_plugin(main_module, sessions=sessions, debug=debug)
    event = FakeEvent(unified_msg_origin="origin:1")

    results = run_rp_command(plugin, event, "debug")

    assert results == [
        "Smarter RP debug: paused=yes; latest prompt snapshot=debug_prompt_1. Open WebUI Debug page for details."
    ]
    assert sessions.calls == [("origin:1", None)]
    assert debug.calls == [{"limit": 1, "session_id": "session_1", "snapshot_type": "prompt"}]
    assert "token=" not in results[0]


def test_debug_command_reports_no_latest_prompt_snapshot(main_module):
    session = SimpleNamespace(id="session_1", paused=False)
    plugin = make_plugin(main_module, sessions=FakeSessions(session), debug=FakeDebug([]))
    event = FakeEvent(unified_msg_origin="origin:1")

    results = run_rp_command(plugin, event, "debug")

    assert results == [
        "Smarter RP debug: paused=no; latest prompt snapshot=none. Open WebUI Debug page for details."
    ]
