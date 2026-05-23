import asyncio
import importlib
import inspect
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


class FakeEvent:
    unified_msg_origin = "session-1"
    adapter_name = "aiocqhttp"
    platform = "qq"
    self_id = "bot-1"
    sender_id = "user-1"
    sender_name = "Alice"
    session_name = "测试群"

    def __init__(self, message_str="hello"):
        self.message_str = message_str
        self.stopped = False

    def get_message_str(self):
        return self.message_str

    def stop_event(self):
        self.stopped = True

    def plain_result(self, text):
        return text


class FakeBridgeServer:
    def __init__(self, *args, reply="bridge reply", error=None, start_error=None, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.reply = reply
        self.error = error
        self.start_error = start_error
        self.calls = []
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True
        if self.start_error:
            raise self.start_error

    async def stop(self):
        self.stopped = True

    async def generate(self, payload):
        self.calls.append(payload)
        if self.error:
            raise self.error
        return self.reply


class FakeWorker:
    def __init__(self, client=None, bindings=None, reply="worker reply", error=None):
        self.client = client
        self.bindings = bindings
        self.reply = reply
        self.error = error
        self.calls = []

    async def generate(self, payload):
        self.calls.append(payload)
        if self.error:
            raise self.error
        return self.reply


class FakeSessionState:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.disabled = []
        self.enabled_sessions = []

    def is_enabled(self, session_id):
        return self.enabled

    def disable(self, session_id):
        self.disabled.append(session_id)
        self.enabled = False

    def enable(self, session_id):
        self.enabled_sessions.append(session_id)
        self.enabled = True


def import_main(astrbot_stubs):
    sys.modules.pop("main", None)
    module = importlib.import_module("main")
    assert astrbot_stubs.command_calls == [(("rp",), {})]
    assert astrbot_stubs.message_decorator_calls == [((astrbot_stubs.event_message_type.ALL,), {})]
    return module


def make_plugin(main_module, *, enabled=True, worker=None, bridge=None, fallback="fallback"):
    plugin = object.__new__(main_module.SmarterRpPlugin)
    plugin.config_model = SimpleNamespace(behavior={"fallback_message": fallback})
    plugin.session_state = FakeSessionState(enabled=enabled)
    plugin.bridge_server = bridge
    plugin.worker = worker or FakeWorker()
    plugin.bindings = None
    plugin.client = None
    plugin.tavern_process = None
    plugin.webui_server = None
    plugin._use_legacy_bridge = bridge is not None
    return plugin


async def invoke(value):
    if inspect.isasyncgen(value):
        return [item async for item in value]
    if inspect.isawaitable(value):
        result = await value
        return [] if result is None else [result]
    return [] if value is None else [value]


def run(value):
    return asyncio.run(invoke(value))


def test_rp_off_disables_current_session(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    plugin = make_plugin(main_module, enabled=True)
    event = FakeEvent()

    results = run(plugin.rp(event, "off"))

    assert results == ["RP disabled for this conversation."]
    assert plugin.session_state.disabled == ["session-1"]


def test_rp_on_enables_current_session(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    plugin = make_plugin(main_module, enabled=False)
    event = FakeEvent()

    results = run(plugin.rp(event, "on"))

    assert results == ["RP enabled for this conversation."]
    assert plugin.session_state.enabled_sessions == ["session-1"]


def test_default_message_calls_worker_sends_reply_and_stops(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    worker = FakeWorker(reply="worker reply")
    plugin = make_plugin(main_module, enabled=True, worker=worker)
    event = FakeEvent("hello")

    results = run(plugin.on_message(event))

    assert results == ["worker reply"]
    assert worker.calls == [{
        "adapter": {"name": "aiocqhttp", "platform": "qq", "accountId": "bot-1"},
        "session": {"id": "session-1", "displayName": "测试群"},
        "user": {"id": "user-1", "name": "Alice"},
        "message": {"text": "hello"},
    }]
    assert event.stopped is True


def test_disabled_message_does_not_call_worker_or_stop(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    worker = FakeWorker(reply="worker reply")
    plugin = make_plugin(main_module, enabled=False, worker=worker)
    event = FakeEvent("hello")

    results = run(plugin.on_message(event))

    assert results == []
    assert worker.calls == []
    assert event.stopped is False


def test_worker_error_sends_fallback_and_stops(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    worker = FakeWorker(error=main_module.MissingTavernBindingError("missing binding"))
    plugin = make_plugin(main_module, enabled=True, worker=worker, fallback="backend down")
    event = FakeEvent("hello")

    results = run(plugin.on_message(event))

    assert results == ["backend down"]
    assert len(worker.calls) == 1
    assert event.stopped is True


def test_empty_and_rp_command_messages_are_ignored(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    worker = FakeWorker(reply="worker reply")
    plugin = make_plugin(main_module, enabled=True, worker=worker)

    assert run(plugin.on_message(FakeEvent("   "))) == []
    assert run(plugin.on_message(FakeEvent("/rp"))) == []
    assert run(plugin.on_message(FakeEvent("/rp off"))) == []
    assert worker.calls == []


def test_non_rp_slash_command_messages_are_ignored(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    worker = FakeWorker(reply="worker reply")
    plugin = make_plugin(main_module, enabled=True, worker=worker)
    event = FakeEvent("/help")

    results = run(plugin.on_message(event))

    assert results == []
    assert worker.calls == []
    assert event.stopped is False


def test_default_initialize_starts_managed_process_and_webui_without_bridge(monkeypatch, tmp_path, astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    events = []

    class FakeClient:
        def __init__(self, base_url, *, timeout_seconds, auth):
            events.append(("client", base_url, timeout_seconds, auth))
            self.closed = False

        async def aclose(self):
            events.append("client.close")
            self.closed = True

    class FakeProcess:
        def __init__(self, **kwargs):
            events.append(("process", kwargs["base_url"], kwargs["install_dir"]))

        async def start(self):
            events.append("process.start")

        async def stop(self):
            events.append("process.stop")

    class FakeWebUi:
        def __init__(self, *, client, bindings, config, webui_token=None):
            events.append(("webui", client.__class__.__name__, bindings.__class__.__name__, config.tavern["mode"], bool(webui_token)))

        async def start(self):
            events.append("webui.start")

        async def stop(self):
            events.append("webui.stop")

    class FailingBridge:
        def __init__(self, *args, **kwargs):
            raise AssertionError("legacy bridge should not be created in default managed mode")

    monkeypatch.setattr(main_module, "SillyTavernClient", FakeClient)
    monkeypatch.setattr(main_module, "TavernProcessManager", FakeProcess)
    monkeypatch.setattr(main_module, "WebUiServer", FakeWebUi)
    monkeypatch.setattr(main_module, "BridgeServer", FailingBridge)

    context = SimpleNamespace(get_plugin_data_dir=lambda: tmp_path)
    plugin = main_module.SmarterRpPlugin(context, {})
    run(plugin.initialize())
    run(plugin.terminate())

    assert events == [
        ("client", "http://127.0.0.1:8001", 120, {"enabled": False, "username": "", "password": "", "token": ""}),
        ("process", "http://127.0.0.1:8001", "~/.local/share/astrbot-smarter-rp/SillyTavern"),
        ("webui", "FakeClient", "TavernBindingService", "managed", True),
        "process.start",
        "webui.start",
        "webui.stop",
        "process.stop",
        "client.close",
    ]


def test_default_webui_token_is_persisted_and_discoverable_by_file(monkeypatch, tmp_path, astrbot_stubs):
    main_module = import_main(astrbot_stubs)

    class FakeClient:
        async def aclose(self):
            pass

    class FakeWebUi:
        def __init__(self, *, client, bindings, config, webui_token=None):
            self.webui_token = webui_token

    monkeypatch.setattr(main_module, "SillyTavernClient", lambda *args, **kwargs: FakeClient())
    monkeypatch.setattr(main_module, "WebUiServer", FakeWebUi)

    context = SimpleNamespace(get_plugin_data_dir=lambda: tmp_path)
    plugin = main_module.SmarterRpPlugin(context, {"tavern": {"auto_start": False}})
    token_file = tmp_path / "webui_token.txt"

    assert token_file.read_text(encoding="utf-8").strip() == plugin.webui_token
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    message = run(plugin.rp(FakeEvent(), "webui"))[0]
    assert message == f"WebUI: http://127.0.0.1:8010\nToken: read {token_file} on the server."
    assert plugin.webui_token not in message

    second_plugin = main_module.SmarterRpPlugin(context, {"tavern": {"auto_start": False}})
    assert second_plugin.webui_token == plugin.webui_token


def test_configured_webui_token_overrides_generated_token_file(monkeypatch, tmp_path, astrbot_stubs):
    main_module = import_main(astrbot_stubs)

    class FakeClient:
        async def aclose(self):
            pass

    class FakeWebUi:
        def __init__(self, *, client, bindings, config, webui_token=None):
            self.webui_token = webui_token

    monkeypatch.setattr(main_module, "SillyTavernClient", lambda *args, **kwargs: FakeClient())
    monkeypatch.setattr(main_module, "WebUiServer", FakeWebUi)

    token_file = tmp_path / "webui_token.txt"
    token_file.write_text("generated-token\n", encoding="utf-8")
    context = SimpleNamespace(get_plugin_data_dir=lambda: tmp_path)
    plugin = main_module.SmarterRpPlugin(
        context,
        {"tavern": {"auto_start": False}, "webui": {"token": "configured-token"}},
    )

    assert plugin.webui_token == "configured-token"
    assert token_file.read_text(encoding="utf-8").strip() == "generated-token"
    message = run(plugin.rp(FakeEvent(), "webui"))[0]
    assert message == "WebUI: http://127.0.0.1:8010\nToken: configured in webui.token."
    assert "configured-token" not in message


def test_terminate_stops_only_started_default_components_in_reverse_order(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    events = []
    client = SimpleNamespace(aclose=lambda: _async_append(events, "client.close"))
    plugin = make_plugin(main_module)
    plugin.webui_server = SimpleNamespace(stop=lambda: _async_append(events, "webui.stop"))
    plugin.tavern_process = SimpleNamespace(stop=lambda: _async_append(events, "process.stop"))
    plugin.client = client
    plugin.bridge_server = FakeBridgeServer()
    plugin._use_legacy_bridge = False

    run(plugin.terminate())

    assert events == ["webui.stop", "process.stop", "client.close"]
    assert plugin.bridge_server.stopped is False


def test_explicit_legacy_mode_starts_and_calls_bridge(monkeypatch, tmp_path, astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    created = []

    class RecordingBridge(FakeBridgeServer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    class FailingClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("browserless client should not be created in legacy mode")

    monkeypatch.setattr(main_module, "BridgeServer", RecordingBridge)
    monkeypatch.setattr(main_module, "SillyTavernClient", FailingClient)

    context = SimpleNamespace(get_plugin_data_dir=lambda: tmp_path)
    plugin = main_module.SmarterRpPlugin(context, {"tavern": {"mode": "legacy_ws"}})
    run(plugin.initialize())
    results = run(plugin.on_message(FakeEvent("hello")))
    run(plugin.terminate())

    assert results == ["bridge reply"]
    assert len(created) == 1
    assert created[0].started is True
    assert created[0].stopped is True
    assert len(created[0].calls) == 1


def test_legacy_bridge_error_sends_fallback_and_stops(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    bridge = FakeBridgeServer(error=main_module.BridgeUnavailableError("boom"))
    plugin = make_plugin(main_module, enabled=True, bridge=bridge, fallback="backend down")
    event = FakeEvent("hello")

    results = run(plugin.on_message(event))

    assert results == ["backend down"]
    assert len(bridge.calls) == 1
    assert event.stopped is True


def test_initialize_keeps_plugin_alive_when_legacy_bridge_start_fails(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    bridge = FakeBridgeServer(start_error=main_module.BridgeUnavailableError("port busy"))
    plugin = make_plugin(main_module, enabled=True, bridge=bridge)

    run(plugin.initialize())

    assert bridge.started is True


def test_rp_bind_binding_and_unbind_use_current_account(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    calls = []

    class FakeBindings:
        def __init__(self):
            self.binding = None

        def set_account_binding(self, adapter, platform, account_id, character_id):
            calls.append(("set", adapter, platform, account_id, character_id))
            self.binding = SimpleNamespace(character_id=character_id)

        def get_account_binding(self, adapter, platform, account_id):
            calls.append(("get", adapter, platform, account_id))
            return self.binding

        def delete_account_binding(self, adapter, platform, account_id):
            calls.append(("delete", adapter, platform, account_id))
            self.binding = None

    plugin = make_plugin(main_module)
    plugin.bindings = FakeBindings()
    event = FakeEvent()

    assert run(plugin.rp(event, "bind", "7")) == ["RP account bound to SillyTavern character 7."]
    assert run(plugin.rp(event, "binding")) == ["Current RP binding: character 7."]
    assert run(plugin.rp(event, "unbind")) == ["RP account binding removed."]
    assert run(plugin.rp(event, "binding")) == ["Current RP binding: none."]
    assert calls == [
        ("set", "aiocqhttp", "qq", "bot-1", "7"),
        ("get", "aiocqhttp", "qq", "bot-1"),
        ("delete", "aiocqhttp", "qq", "bot-1"),
        ("get", "aiocqhttp", "qq", "bot-1"),
    ]


def _async_append(events, item):
    async def append():
        events.append(item)
    return append()
