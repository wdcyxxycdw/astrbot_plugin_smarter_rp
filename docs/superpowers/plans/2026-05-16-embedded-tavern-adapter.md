# Embedded Tavern Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first embedded Tavern adapter: AstrBot runs a localhost WebSocket Bridge Server, and a SillyTavern extension connects to it, binds accounts to characters, auto-creates per-session chats, generates replies, and returns them to AstrBot.

**Architecture:** Replace the old self-contained RP runtime with a thin AstrBot plugin plus an embedded WebSocket job broker. Keep role cards, chat files, prompt assembly, and generation inside SillyTavern via a companion extension using `SillyTavern.getContext()`. The first version is localhost-only, unauthenticated, single-extension, and globally serial.

**Tech Stack:** Python 3.10+, AstrBot plugin APIs, FastAPI WebSocket, Uvicorn, pytest, httpx, vanilla SillyTavern UI extension JavaScript, Node.js built-in `node:test` for pure JS helper tests.

**Important user preference:** Do not create git commits unless the user explicitly asks. The plan omits commit steps intentionally.

---

## File Structure

### Python plugin side

- Replace `main.py`: remove old prompt rewrite/runtime/WebUI hooks; initialize storage, session state, and embedded bridge server; intercept normal messages; send generate jobs to the SillyTavern extension.
- Modify `metadata.yaml`: describe the embedded Tavern adapter; remove plugin-page/WebUI metadata if present.
- Modify `requirements.txt`: keep `fastapi`, `uvicorn`, `httpx`; no extra dependency is needed for FastAPI WebSocket routes.
- Replace `smarter_rp/config.py`: minimal `bridge`, `behavior`, `storage` config.
- Replace `smarter_rp/storage.py`: minimal SQLite helpers for session overrides and settings.
- Create `smarter_rp/session_state.py`: enable/disable current AstrBot session.
- Create `smarter_rp/embedded_bridge.py`: WebSocket bridge server, single extension connection, pending job futures, timeout handling, late-result discard.
- Keep `smarter_rp/__init__.py`.
- Delete old runtime modules after replacement: `smarter_rp/models.py`, `smarter_rp/ids.py`, `smarter_rp/services/`, `smarter_rp/web/`, `pages/`, `webui/`.

### SillyTavern extension side

- Create `sillytavern_extension/astrbot-smarter-rp/manifest.json`: SillyTavern extension manifest.
- Create `sillytavern_extension/astrbot-smarter-rp/index.js`: extension startup, WebSocket connection, settings UI binding, job handling.
- Create `sillytavern_extension/astrbot-smarter-rp/lib.js`: pure helper functions for keys, chat names, payload validation, settings mutation.
- Create `sillytavern_extension/astrbot-smarter-rp/settings.html`: settings drawer.
- Create `sillytavern_extension/astrbot-smarter-rp/style.css`: minimal styles.
- Create `tests_js/astrbot_extension_lib.test.mjs`: Node built-in tests for pure extension helpers.

### Tests

- Replace Python tests with focused bridge tests:
  - `tests/conftest.py`
  - `tests/test_config.py`
  - `tests/test_session_state.py`
  - `tests/test_embedded_bridge.py`
  - `tests/test_main_embedded_bridge.py`
- Delete old tests that target the removed runtime/WebUI.

---

### Task 1: Minimal Config, Storage, and Session State

**Files:**
- Modify: `smarter_rp/config.py`
- Modify: `smarter_rp/storage.py`
- Create: `smarter_rp/session_state.py`
- Test: `tests/test_config.py`
- Test: `tests/test_session_state.py`

- [ ] **Step 1: Replace config tests**

Write `tests/test_config.py`:

```python
import pytest

from smarter_rp.config import SmarterRpConfig


def test_default_config_uses_embedded_bridge():
    config = SmarterRpConfig.default()

    assert config.bridge == {
        "mode": "embedded",
        "host": "127.0.0.1",
        "port": 8008,
        "timeout_seconds": 120,
    }
    assert config.behavior["default_enabled"] is True
    assert config.behavior["fallback_message"] == "RP 后端暂时不可用。"
    assert config.storage["backend"] == "sqlite"


def test_config_merges_bridge_override():
    config = SmarterRpConfig.from_mapping({"bridge": {"port": 8765, "timeout_seconds": 5}})

    assert config.bridge["mode"] == "embedded"
    assert config.bridge["host"] == "127.0.0.1"
    assert config.bridge["port"] == 8765
    assert config.bridge["timeout_seconds"] == 5


def test_config_rejects_unknown_section():
    with pytest.raises(ValueError, match="unknown config section"):
        SmarterRpConfig.from_mapping({"rewrite": {"enabled_by_default": True}})


def test_config_rejects_non_mapping_section():
    with pytest.raises(ValueError, match="config section bridge must be a mapping"):
        SmarterRpConfig.from_mapping({"bridge": "bad"})
```

- [ ] **Step 2: Replace session state tests**

Write `tests/test_session_state.py`:

```python
from smarter_rp.session_state import SessionStateService
from smarter_rp.storage import Storage


def test_session_defaults_to_enabled(tmp_path):
    storage = Storage(tmp_path / "state.db")
    storage.initialize()
    service = SessionStateService(storage, default_enabled=True)

    assert service.is_enabled("session-1") is True


def test_session_defaults_to_disabled_when_configured(tmp_path):
    storage = Storage(tmp_path / "state.db")
    storage.initialize()
    service = SessionStateService(storage, default_enabled=False)

    assert service.is_enabled("session-1") is False


def test_disable_and_enable_session(tmp_path):
    storage = Storage(tmp_path / "state.db")
    storage.initialize()
    service = SessionStateService(storage, default_enabled=True)

    service.disable("session-1")
    assert service.is_enabled("session-1") is False

    service.enable("session-1")
    assert service.is_enabled("session-1") is True
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
python -m pytest -q tests/test_config.py tests/test_session_state.py
```

Expected before implementation: failures because the current config still contains old runtime sections and `session_state.py` does not exist.

- [ ] **Step 4: Replace config implementation**

Replace `smarter_rp/config.py` with:

```python
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "bridge": {
        "mode": "embedded",
        "host": "127.0.0.1",
        "port": 8008,
        "timeout_seconds": 120,
    },
    "behavior": {
        "default_enabled": True,
        "fallback_message": "RP 后端暂时不可用。",
    },
    "storage": {
        "backend": "sqlite",
    },
}


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass(slots=True)
class SmarterRpConfig:
    bridge: dict[str, Any]
    behavior: dict[str, Any]
    storage: dict[str, Any]

    @classmethod
    def default(cls) -> "SmarterRpConfig":
        return cls.from_mapping({})

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "SmarterRpConfig":
        overrides = data or {}
        for key, value in overrides.items():
            if key not in DEFAULT_CONFIG:
                raise ValueError(f"unknown config section: {key}")
            if not isinstance(value, Mapping):
                raise ValueError(f"config section {key} must be a mapping")

        merged = _deep_merge(DEFAULT_CONFIG, overrides)
        return cls(
            bridge=merged["bridge"],
            behavior=merged["behavior"],
            storage=merged["storage"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bridge": deepcopy(self.bridge),
            "behavior": deepcopy(self.behavior),
            "storage": deepcopy(self.storage),
        }
```

- [ ] **Step 5: Replace minimal storage implementation**

Replace `smarter_rp/storage.py` with:

```python
from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_overrides (
        session_id TEXT PRIMARY KEY,
        enabled INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS plugin_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
)


def now_ts() -> int:
    return int(time.time())


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connection() as conn:
            try:
                conn.execute("BEGIN")
                for statement in SCHEMA_STATEMENTS:
                    conn.execute(statement)
                conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, now_ts()),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self.connection() as conn:
            conn.execute(sql, tuple(params))
            conn.commit()

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute(sql, tuple(params)).fetchone()

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return list(conn.execute(sql, tuple(params)).fetchall())
```

- [ ] **Step 6: Create session state service**

Create `smarter_rp/session_state.py`:

```python
from __future__ import annotations

from smarter_rp.storage import Storage, now_ts


class SessionStateService:
    def __init__(self, storage: Storage, default_enabled: bool = True):
        self._storage = storage
        self._default_enabled = default_enabled

    def is_enabled(self, session_id: str) -> bool:
        row = self._storage.fetch_one(
            "SELECT enabled FROM session_overrides WHERE session_id = ?",
            (session_id,),
        )
        if row is None:
            return self._default_enabled
        return bool(row["enabled"])

    def disable(self, session_id: str) -> None:
        self._set_enabled(session_id, False)

    def enable(self, session_id: str) -> None:
        self._set_enabled(session_id, True)

    def _set_enabled(self, session_id: str, enabled: bool) -> None:
        self._storage.execute(
            """
            INSERT INTO session_overrides(session_id, enabled, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (session_id, int(enabled), now_ts()),
        )
```

- [ ] **Step 7: Verify Task 1**

Run:

```bash
python -m pytest -q tests/test_config.py tests/test_session_state.py
```

Expected: all tests pass.

---

### Task 2: Embedded WebSocket Bridge Server

**Files:**
- Create: `smarter_rp/embedded_bridge.py`
- Test: `tests/test_embedded_bridge.py`

- [ ] **Step 1: Write bridge tests**

Create `tests/test_embedded_bridge.py`:

```python
import asyncio

import pytest

from smarter_rp.embedded_bridge import (
    BridgeJobError,
    BridgeServer,
    BridgeTimeoutError,
    BridgeUnavailableError,
)


class FakeConnection:
    def __init__(self):
        self.sent = []

    async def send_json(self, payload):
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_generate_requires_connected_extension():
    server = BridgeServer(host="127.0.0.1", port=8008, timeout_seconds=0.05)

    with pytest.raises(BridgeUnavailableError):
        await server.generate({"message": {"text": "hi"}})


@pytest.mark.asyncio
async def test_generate_sends_job_and_returns_reply():
    server = BridgeServer(host="127.0.0.1", port=8008, timeout_seconds=1)
    connection = FakeConnection()
    await server.register_connection(connection)

    task = asyncio.create_task(server.generate({"message": {"text": "hi"}}))
    await asyncio.sleep(0)

    assert connection.sent[0]["type"] == "generate"
    assert connection.sent[0]["message"] == {"text": "hi"}
    await server.handle_client_message({
        "type": "generate_result",
        "jobId": connection.sent[0]["jobId"],
        "reply": "hello",
        "characterId": "alice",
        "chatId": "chat-1",
    })

    assert await task == "hello"


@pytest.mark.asyncio
async def test_generate_error_raises_job_error():
    server = BridgeServer(host="127.0.0.1", port=8008, timeout_seconds=1)
    connection = FakeConnection()
    await server.register_connection(connection)

    task = asyncio.create_task(server.generate({"message": {"text": "hi"}}))
    await asyncio.sleep(0)
    await server.handle_client_message({
        "type": "generate_error",
        "jobId": connection.sent[0]["jobId"],
        "code": "missing_character_binding",
        "message": "missing binding",
    })

    with pytest.raises(BridgeJobError, match="missing_character_binding"):
        await task


@pytest.mark.asyncio
async def test_generate_times_out_and_discards_late_result():
    server = BridgeServer(host="127.0.0.1", port=8008, timeout_seconds=0.01)
    connection = FakeConnection()
    await server.register_connection(connection)

    with pytest.raises(BridgeTimeoutError):
        await server.generate({"message": {"text": "hi"}})

    await server.handle_client_message({
        "type": "generate_result",
        "jobId": connection.sent[0]["jobId"],
        "reply": "late",
    })
    assert server.pending_job_count == 0


@pytest.mark.asyncio
async def test_result_requires_non_empty_reply():
    server = BridgeServer(host="127.0.0.1", port=8008, timeout_seconds=1)
    connection = FakeConnection()
    await server.register_connection(connection)

    task = asyncio.create_task(server.generate({"message": {"text": "hi"}}))
    await asyncio.sleep(0)
    await server.handle_client_message({
        "type": "generate_result",
        "jobId": connection.sent[0]["jobId"],
        "reply": "   ",
    })

    with pytest.raises(BridgeJobError, match="missing reply"):
        await task
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
python -m pytest -q tests/test_embedded_bridge.py
```

Expected before implementation: import failure because `smarter_rp.embedded_bridge` does not exist.

- [ ] **Step 3: Implement bridge server**

Create `smarter_rp/embedded_bridge.py`:

```python
from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any, Protocol

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


class BridgeUnavailableError(Exception):
    pass


class BridgeTimeoutError(Exception):
    pass


class BridgeJobError(Exception):
    pass


class JsonConnection(Protocol):
    async def send_json(self, payload: dict[str, Any]) -> None: ...


class BridgeServer:
    def __init__(self, host: str, port: int, timeout_seconds: float):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.app = FastAPI()
        self._connection: JsonConnection | None = None
        self._connection_lock = asyncio.Lock()
        self._generate_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future[str]] = {}
        self._uvicorn_server: uvicorn.Server | None = None
        self._server_task: asyncio.Task | None = None
        self.app.websocket("/ws")(self.websocket_endpoint)

    @property
    def pending_job_count(self) -> int:
        return len(self._pending)

    async def start(self) -> None:
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
        self._uvicorn_server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(self._uvicorn_server.serve())

    async def stop(self) -> None:
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        if self._server_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._server_task
        self._server_task = None
        self._uvicorn_server = None
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(BridgeUnavailableError("bridge server stopped"))
        self._pending.clear()

    async def websocket_endpoint(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._connection_lock:
            if self._connection is not None:
                await websocket.close(code=4409)
                return
            self._connection = websocket
        try:
            while True:
                payload = await websocket.receive_json()
                if isinstance(payload, dict) and payload.get("type") == "hello":
                    await websocket.send_json({
                        "type": "hello_ack",
                        "server": "astrbot-smarter-rp",
                        "version": "0.1.0",
                    })
                    continue
                if isinstance(payload, dict):
                    await self.handle_client_message(payload)
        except WebSocketDisconnect:
            pass
        finally:
            async with self._connection_lock:
                if self._connection is websocket:
                    self._connection = None
            for future in list(self._pending.values()):
                if not future.done():
                    future.set_exception(BridgeUnavailableError("sillytavern extension disconnected"))
            self._pending.clear()

    async def register_connection(self, connection: JsonConnection) -> None:
        async with self._connection_lock:
            self._connection = connection

    async def handle_client_message(self, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("jobId") or "")
        future = self._pending.get(job_id)
        if future is None or future.done():
            return

        message_type = payload.get("type")
        if message_type == "generate_result":
            reply = payload.get("reply")
            if not isinstance(reply, str) or not reply.strip():
                future.set_exception(BridgeJobError("missing reply"))
                return
            future.set_result(reply)
            return

        if message_type == "generate_error":
            code = str(payload.get("code") or "generate_error")
            message = str(payload.get("message") or code)
            future.set_exception(BridgeJobError(f"{code}: {message}"))

    async def generate(self, payload: dict[str, Any]) -> str:
        async with self._generate_lock:
            if self._connection is None:
                raise BridgeUnavailableError("sillytavern extension is not connected")

            job_id = str(uuid.uuid4())
            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            self._pending[job_id] = future
            job = {"type": "generate", "jobId": job_id, **payload}
            try:
                await self._connection.send_json(job)
                return await asyncio.wait_for(future, timeout=self.timeout_seconds)
            except TimeoutError as exc:
                raise BridgeTimeoutError("sillytavern generation timed out") from exc
            finally:
                self._pending.pop(job_id, None)
```

- [ ] **Step 4: Verify Task 2**

Run:

```bash
python -m pytest -q tests/test_embedded_bridge.py
```

Expected: all tests pass.

---

### Task 3: Replace AstrBot Plugin Runtime With Embedded Bridge Flow

**Files:**
- Replace: `main.py`
- Modify: `metadata.yaml`
- Test: `tests/conftest.py`
- Test: `tests/test_main_embedded_bridge.py`

- [ ] **Step 1: Write AstrBot stubs**

Replace `tests/conftest.py` with:

```python
import sys
import types
from types import SimpleNamespace

import pytest


@pytest.fixture()
def astrbot_stubs(monkeypatch):
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    event_module = types.ModuleType("astrbot.api.event")
    star_module = types.ModuleType("astrbot.api.star")

    command_calls = []
    message_decorator_calls = []
    event_message_type = SimpleNamespace(ALL="all")

    def fake_command(*args, **kwargs):
        command_calls.append((args, kwargs))
        return lambda func: func

    def fake_event_message_type(*args, **kwargs):
        message_decorator_calls.append((args, kwargs))
        return lambda func: func

    filter_module = SimpleNamespace(
        command=fake_command,
        event_message_type=fake_event_message_type,
        EventMessageType=event_message_type,
    )

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

    return SimpleNamespace(
        command_calls=command_calls,
        message_decorator_calls=message_decorator_calls,
        event_message_type=event_message_type,
    )
```

- [ ] **Step 2: Write plugin tests**

Create `tests/test_main_embedded_bridge.py`:

```python
import asyncio
import importlib
import inspect
import sys
from types import SimpleNamespace


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
    def __init__(self, reply="bridge reply", error=None):
        self.reply = reply
        self.error = error
        self.calls = []
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

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


def make_plugin(main_module, *, enabled=True, bridge=None, fallback="fallback"):
    plugin = object.__new__(main_module.SmarterRpPlugin)
    plugin.config_model = SimpleNamespace(behavior={"fallback_message": fallback})
    plugin.session_state = FakeSessionState(enabled=enabled)
    plugin.bridge_server = bridge or FakeBridgeServer()
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


def test_enabled_message_calls_bridge_sends_reply_and_stops(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    bridge = FakeBridgeServer(reply="bridge reply")
    plugin = make_plugin(main_module, enabled=True, bridge=bridge)
    event = FakeEvent("hello")

    results = run(plugin.on_message(event))

    assert results == ["bridge reply"]
    assert bridge.calls == [{
        "adapter": {"name": "aiocqhttp", "platform": "qq", "accountId": "bot-1"},
        "session": {"id": "session-1", "displayName": "测试群"},
        "user": {"id": "user-1", "name": "Alice"},
        "message": {"text": "hello"},
    }]
    assert event.stopped is True


def test_disabled_message_does_not_call_bridge_or_stop(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    bridge = FakeBridgeServer(reply="bridge reply")
    plugin = make_plugin(main_module, enabled=False, bridge=bridge)
    event = FakeEvent("hello")

    results = run(plugin.on_message(event))

    assert results == []
    assert bridge.calls == []
    assert event.stopped is False


def test_bridge_error_sends_fallback_and_stops(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    bridge = FakeBridgeServer(error=RuntimeError("boom"))
    plugin = make_plugin(main_module, enabled=True, bridge=bridge, fallback="backend down")
    event = FakeEvent("hello")

    results = run(plugin.on_message(event))

    assert results == ["backend down"]
    assert len(bridge.calls) == 1
    assert event.stopped is True


def test_empty_and_rp_command_messages_are_ignored(astrbot_stubs):
    main_module = import_main(astrbot_stubs)
    bridge = FakeBridgeServer(reply="bridge reply")
    plugin = make_plugin(main_module, enabled=True, bridge=bridge)

    assert run(plugin.on_message(FakeEvent("   "))) == []
    assert run(plugin.on_message(FakeEvent("/rp off"))) == []
    assert bridge.calls == []
```

- [ ] **Step 3: Run failing plugin tests**

Run:

```bash
python -m pytest -q tests/test_main_embedded_bridge.py
```

Expected before implementation: failures because `main.py` still imports old services and does not use `BridgeServer`.

- [ ] **Step 4: Replace `main.py`**

Replace `main.py` with:

```python
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register

from smarter_rp.config import SmarterRpConfig
from smarter_rp.embedded_bridge import BridgeJobError, BridgeServer, BridgeTimeoutError, BridgeUnavailableError
from smarter_rp.session_state import SessionStateService
from smarter_rp.storage import Storage


def _message_handler_decorator():
    decorator = getattr(filter, "event_message_type", None)
    event_message_type = getattr(filter, "EventMessageType", None)
    all_message_types = getattr(event_message_type, "ALL", None)
    if callable(decorator) and all_message_types is not None:
        return decorator(all_message_types)
    if callable(decorator):
        return decorator()
    return lambda func: func


@register("smarter_rp", "smarter-rp", "AstrBot embedded Tavern adapter", "0.1.0")
class SmarterRpPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        super().__init__(context)
        self.config_model = SmarterRpConfig.from_mapping(config or {})
        data_dir = self._resolve_data_dir()
        self.storage = Storage(data_dir / "smarter_rp.db")
        self.storage.initialize()
        self.session_state = SessionStateService(
            self.storage,
            default_enabled=bool(self.config_model.behavior.get("default_enabled", True)),
        )
        self.bridge_server = BridgeServer(
            host=str(self.config_model.bridge.get("host", "127.0.0.1")),
            port=int(self.config_model.bridge.get("port", 8008)),
            timeout_seconds=float(self.config_model.bridge.get("timeout_seconds", 120)),
        )

    async def initialize(self):
        await self.bridge_server.start()

    async def terminate(self):
        await self.bridge_server.stop()

    @filter.command("rp")
    async def rp(self, event, subcommand: str = ""):
        subcommand = self._text_value(subcommand).lower()
        if subcommand == "off":
            self.session_state.disable(self._session_id(event))
            yield self._plain_result(event, "RP disabled for this conversation.")
            return
        if subcommand == "on":
            self.session_state.enable(self._session_id(event))
            yield self._plain_result(event, "RP enabled for this conversation.")
            return
        yield self._plain_result(event, "Usage: /rp on|off")

    @_message_handler_decorator()
    async def on_message(self, event):
        text = self._extract_text(event)
        if not text or text.startswith("/rp"):
            return

        session_id = self._session_id(event)
        if not self.session_state.is_enabled(session_id):
            return

        try:
            reply = await self.bridge_server.generate(self._generate_payload(event))
        except (BridgeUnavailableError, BridgeTimeoutError, BridgeJobError, Exception):
            reply = str(self.config_model.behavior.get("fallback_message", "RP 后端暂时不可用。"))

        self._stop_event(event)
        yield self._plain_result(event, reply)

    def _generate_payload(self, event) -> dict[str, dict[str, str]]:
        session_id = self._session_id(event)
        return {
            "adapter": {
                "name": self._text_value(self._safe_get(event, "adapter_name"), default="unknown"),
                "platform": self._text_value(self._safe_get(event, "platform"), default="unknown"),
                "accountId": self._text_value(self._safe_get(event, "self_id")),
            },
            "session": {
                "id": session_id,
                "displayName": self._text_value(self._safe_get(event, "session_name"), default=session_id),
            },
            "user": {
                "id": self._text_value(self._safe_get(event, "sender_id")),
                "name": self._text_value(self._safe_get(event, "sender_name")),
            },
            "message": {"text": self._extract_text(event)},
        }

    def _plain_result(self, event, text: str):
        plain_result = self._safe_get(event, "plain_result")
        if callable(plain_result):
            return plain_result(text)
        return text

    def _stop_event(self, event) -> None:
        stop_event = self._safe_get(event, "stop_event")
        if callable(stop_event):
            stop_event()

    def _extract_text(self, event) -> str:
        get_message_str = self._safe_get(event, "get_message_str")
        if callable(get_message_str):
            return self._text_value(get_message_str())
        for name in ("message_str", "message", "raw_message"):
            text = self._text_value(self._safe_get(event, name))
            if text:
                return text
        return ""

    def _session_id(self, event) -> str:
        return self._text_value(self._safe_get(event, "unified_msg_origin"), default="unknown")

    def _resolve_data_dir(self) -> Path:
        for name in ("get_plugin_data_dir", "get_data_dir"):
            resolver = self._safe_get(self.context, name)
            if callable(resolver):
                try:
                    data_dir = Path(resolver())
                    data_dir.mkdir(parents=True, exist_ok=True)
                    return data_dir
                except Exception:
                    pass

        for name in ("plugin_data_dir", "plugin_data_path", "data_dir", "data_path"):
            value = self._safe_get(self.context, name)
            if value:
                try:
                    data_dir = Path(value)
                    data_dir.mkdir(parents=True, exist_ok=True)
                    return data_dir
                except Exception:
                    pass

        data_dir = Path(__file__).resolve().parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def _safe_get(self, obj, attr: str):
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(attr)
        try:
            return getattr(obj, attr, None)
        except Exception:
            return None

    def _text_value(self, value, default: str = "") -> str:
        if value is None:
            return default
        text = str(value).strip()
        return text or default
```

- [ ] **Step 5: Update metadata**

Replace `metadata.yaml` with:

```yaml
name: smarter_rp
desc: AstrBot embedded Tavern adapter
version: 0.1.0
author: smarter-rp
repo: ""
```

- [ ] **Step 6: Verify Task 3**

Run:

```bash
python -m pytest -q tests/test_main_embedded_bridge.py
```

Expected: all tests pass.

---

### Task 4: SillyTavern Extension Pure Helpers

**Files:**
- Create: `sillytavern_extension/astrbot-smarter-rp/lib.js`
- Create: `tests_js/astrbot_extension_lib.test.mjs`

- [ ] **Step 1: Write JS helper tests**

Create `tests_js/astrbot_extension_lib.test.mjs`:

```javascript
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  bindingKey,
  chatBindingKey,
  createDefaultSettings,
  findAccountBinding,
  makeChatName,
  shortSessionId,
  validateGenerateJob,
} from '../sillytavern_extension/astrbot-smarter-rp/lib.js';

test('bindingKey combines adapter platform and account', () => {
  assert.equal(bindingKey({ adapter: 'aiocqhttp', platform: 'qq', accountId: '123' }), 'aiocqhttp:qq:123');
});

test('chatBindingKey includes session id', () => {
  assert.equal(
    chatBindingKey({ adapter: 'aiocqhttp', platform: 'qq', accountId: '123', sessionId: 'session-1' }),
    'aiocqhttp:qq:123:session-1',
  );
});

test('makeChatName uses readable AstrBot source', () => {
  assert.equal(makeChatName({ platform: 'qq', displayName: '测试群', sessionId: 'abcdef123456' }), '[AstrBot] qq-测试群-abcdef');
});

test('shortSessionId removes unsafe empty value', () => {
  assert.equal(shortSessionId('abcdef123456'), 'abcdef');
  assert.equal(shortSessionId(''), 'unknown');
});

test('findAccountBinding matches adapter facts', () => {
  const settings = createDefaultSettings();
  settings.accountBindings.push({ adapter: 'aiocqhttp', platform: 'qq', accountId: '123', characterId: 'alice' });

  assert.deepEqual(findAccountBinding(settings, { name: 'aiocqhttp', platform: 'qq', accountId: '123' }), {
    adapter: 'aiocqhttp',
    platform: 'qq',
    accountId: '123',
    characterId: 'alice',
  });
});

test('validateGenerateJob accepts minimal valid job', () => {
  assert.equal(validateGenerateJob({
    type: 'generate',
    jobId: 'job-1',
    adapter: { name: 'aiocqhttp', platform: 'qq', accountId: '123' },
    session: { id: 'session-1', displayName: '测试群' },
    user: { id: 'user-1', name: 'Alice' },
    message: { text: 'hello' },
  }).ok, true);
});

test('validateGenerateJob rejects missing message text', () => {
  assert.deepEqual(validateGenerateJob({ type: 'generate', jobId: 'job-1' }), {
    ok: false,
    code: 'invalid_generate_job',
    message: 'message.text is required',
  });
});
```

- [ ] **Step 2: Run failing JS tests**

Run:

```bash
node --test tests_js/astrbot_extension_lib.test.mjs
```

Expected before implementation: module not found.

- [ ] **Step 3: Implement helpers**

Create `sillytavern_extension/astrbot-smarter-rp/lib.js`:

```javascript
export function createDefaultSettings() {
  return {
    bridgeUrl: 'ws://127.0.0.1:8008/ws',
    accountBindings: [],
    chatBindings: {},
  };
}

export function cleanPart(value, fallback = 'unknown') {
  const text = String(value ?? '').trim();
  return text || fallback;
}

export function shortSessionId(sessionId) {
  const text = cleanPart(sessionId);
  return text === 'unknown' ? text : text.slice(0, 6);
}

export function bindingKey({ adapter, platform, accountId }) {
  return [cleanPart(adapter), cleanPart(platform), cleanPart(accountId)].join(':');
}

export function chatBindingKey({ adapter, platform, accountId, sessionId }) {
  return [cleanPart(adapter), cleanPart(platform), cleanPart(accountId), cleanPart(sessionId)].join(':');
}

export function makeChatName({ platform, displayName, sessionId }) {
  return `[AstrBot] ${cleanPart(platform)}-${cleanPart(displayName)}-${shortSessionId(sessionId)}`;
}

export function findAccountBinding(settings, adapter) {
  const key = bindingKey({ adapter: adapter.name, platform: adapter.platform, accountId: adapter.accountId });
  return settings.accountBindings.find((binding) => bindingKey(binding) === key) ?? null;
}

export function validateGenerateJob(job) {
  if (!job || job.type !== 'generate') {
    return { ok: false, code: 'invalid_generate_job', message: 'type must be generate' };
  }
  if (!cleanPart(job.jobId, '')) {
    return { ok: false, code: 'invalid_generate_job', message: 'jobId is required' };
  }
  if (!cleanPart(job?.message?.text, '')) {
    return { ok: false, code: 'invalid_generate_job', message: 'message.text is required' };
  }
  if (!cleanPart(job?.adapter?.accountId, '')) {
    return { ok: false, code: 'invalid_generate_job', message: 'adapter.accountId is required' };
  }
  if (!cleanPart(job?.session?.id, '')) {
    return { ok: false, code: 'invalid_generate_job', message: 'session.id is required' };
  }
  return { ok: true };
}
```

- [ ] **Step 4: Verify Task 4**

Run:

```bash
node --test tests_js/astrbot_extension_lib.test.mjs
```

Expected: all JS helper tests pass.

---

### Task 5: SillyTavern Extension Integration

**Files:**
- Create: `sillytavern_extension/astrbot-smarter-rp/manifest.json`
- Create: `sillytavern_extension/astrbot-smarter-rp/index.js`
- Create: `sillytavern_extension/astrbot-smarter-rp/settings.html`
- Create: `sillytavern_extension/astrbot-smarter-rp/style.css`

- [ ] **Step 1: Create manifest**

Create `sillytavern_extension/astrbot-smarter-rp/manifest.json`:

```json
{
  "display_name": "AstrBot Smarter RP Bridge",
  "loading_order": 1,
  "requires": [],
  "optional": [],
  "dependencies": [],
  "js": "index.js",
  "css": "style.css",
  "author": "smarter-rp",
  "version": "0.1.0",
  "homePage": "",
  "auto_update": false,
  "minimum_client_version": "1.0.0"
}
```

- [ ] **Step 2: Create settings template**

Create `sillytavern_extension/astrbot-smarter-rp/settings.html`:

```html
<div id="astrbot-smarter-rp-settings" class="astrbot-smarter-rp-settings">
  <div class="inline-drawer">
    <div class="inline-drawer-toggle inline-drawer-header">
      <b>AstrBot Smarter RP Bridge</b>
      <div class="inline-drawer-icon fa-solid fa-circle-chevron-down down"></div>
    </div>
    <div class="inline-drawer-content">
      <label for="astrbot_bridge_url">Bridge URL</label>
      <input id="astrbot_bridge_url" class="text_pole" type="text" />
      <label for="astrbot_binding_adapter">Adapter</label>
      <input id="astrbot_binding_adapter" class="text_pole" type="text" placeholder="aiocqhttp" />
      <label for="astrbot_binding_platform">Platform</label>
      <input id="astrbot_binding_platform" class="text_pole" type="text" placeholder="qq" />
      <label for="astrbot_binding_account">Account ID</label>
      <input id="astrbot_binding_account" class="text_pole" type="text" />
      <label for="astrbot_binding_character">Character ID / index</label>
      <input id="astrbot_binding_character" class="text_pole" type="text" />
      <div class="astrbot-smarter-rp-row">
        <button id="astrbot_add_binding" class="menu_button">Add binding</button>
        <button id="astrbot_connect_bridge" class="menu_button">Connect</button>
      </div>
      <pre id="astrbot_bridge_status">Disconnected</pre>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Create styles**

Create `sillytavern_extension/astrbot-smarter-rp/style.css`:

```css
.astrbot-smarter-rp-settings input {
  width: 100%;
}

.astrbot-smarter-rp-row {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

#astrbot_bridge_status {
  white-space: pre-wrap;
  margin-top: 0.5rem;
}
```

- [ ] **Step 4: Create extension integration**

Create `sillytavern_extension/astrbot-smarter-rp/index.js`:

```javascript
import {
  chatBindingKey,
  createDefaultSettings,
  findAccountBinding,
  makeChatName,
  validateGenerateJob,
} from './lib.js';

const EXTENSION_NAME = 'astrbot-smarter-rp';
const SETTINGS_KEY = 'astrbot_smarter_rp';

let socket = null;
let settings = createDefaultSettings();

function context() {
  return SillyTavern.getContext();
}

function setStatus(text) {
  const element = document.querySelector('#astrbot_bridge_status');
  if (element) element.textContent = text;
}

function saveSettings() {
  const ctx = context();
  ctx.extensionSettings[SETTINGS_KEY] = settings;
  ctx.saveSettingsDebounced();
}

function loadSettings() {
  const ctx = context();
  settings = { ...createDefaultSettings(), ...(ctx.extensionSettings[SETTINGS_KEY] ?? {}) };
  settings.accountBindings = Array.isArray(settings.accountBindings) ? settings.accountBindings : [];
  settings.chatBindings = settings.chatBindings && typeof settings.chatBindings === 'object' ? settings.chatBindings : {};
}

async function renderSettings() {
  const ctx = context();
  const html = await ctx.renderExtensionTemplateAsync(`third-party/${EXTENSION_NAME}`, 'settings', {});
  document.querySelector('#extensions_settings2').insertAdjacentHTML('beforeend', html);
  document.querySelector('#astrbot_bridge_url').value = settings.bridgeUrl;
  document.querySelector('#astrbot_bridge_url').addEventListener('change', (event) => {
    settings.bridgeUrl = event.target.value.trim() || createDefaultSettings().bridgeUrl;
    saveSettings();
  });
  document.querySelector('#astrbot_add_binding').addEventListener('click', () => {
    const binding = {
      adapter: document.querySelector('#astrbot_binding_adapter').value.trim(),
      platform: document.querySelector('#astrbot_binding_platform').value.trim(),
      accountId: document.querySelector('#astrbot_binding_account').value.trim(),
      characterId: document.querySelector('#astrbot_binding_character').value.trim(),
    };
    settings.accountBindings = settings.accountBindings.filter((existing) => {
      return !(existing.adapter === binding.adapter && existing.platform === binding.platform && existing.accountId === binding.accountId);
    });
    settings.accountBindings.push(binding);
    saveSettings();
    setStatus(`Saved binding for ${binding.adapter}:${binding.platform}:${binding.accountId}`);
  });
  document.querySelector('#astrbot_connect_bridge').addEventListener('click', connectBridge);
}

function sendResult(job, reply, characterId, chatId) {
  socket?.send(JSON.stringify({ type: 'generate_result', jobId: job.jobId, reply, characterId, chatId }));
}

function sendError(jobId, code, message) {
  socket?.send(JSON.stringify({ type: 'generate_error', jobId, code, message }));
}

async function ensureCharacterChat(job, binding) {
  const ctx = context();
  const characterIndex = Number(binding.characterId);
  if (!Number.isInteger(characterIndex) || !ctx.characters[characterIndex]) {
    throw new Error(`missing character binding target: ${binding.characterId}`);
  }

  const key = chatBindingKey({
    adapter: job.adapter.name,
    platform: job.adapter.platform,
    accountId: job.adapter.accountId,
    sessionId: job.session.id,
  });

  await ctx.selectCharacterById(characterIndex, { switchMenu: false });

  let chatBinding = settings.chatBindings[key];
  if (!chatBinding) {
    const chatName = makeChatName({
      platform: job.adapter.platform,
      displayName: job.session.displayName,
      sessionId: job.session.id,
    });
    const character = ctx.characters[characterIndex];
    const headers = ctx.getRequestHeaders();
    const chatHeader = { chat_metadata: {}, user_name: 'unused', character_name: 'unused' };
    const response = await fetch('/api/chats/save', {
      method: 'POST',
      cache: 'no-cache',
      headers,
      body: JSON.stringify({
        ch_name: character.name,
        file_name: chatName,
        chat: [chatHeader],
        avatar_url: character.avatar,
        force: false,
      }),
    });
    if (!response.ok) {
      throw new Error(`failed to create chat: ${response.status}`);
    }
    chatBinding = { characterId: String(characterIndex), chatId: chatName };
    settings.chatBindings[key] = chatBinding;
    saveSettings();
  }

  await ctx.openCharacterChat(chatBinding.chatId);
  return chatBinding;
}

function appendUserMessage(job) {
  const ctx = context();
  ctx.chat.push({
    name: job.user.name || 'User',
    is_user: true,
    is_system: false,
    mes: job.message.text,
    send_date: new Date().toISOString(),
    extra: {},
  });
}

async function handleGenerate(job) {
  const validation = validateGenerateJob(job);
  if (!validation.ok) {
    sendError(job.jobId || '', validation.code, validation.message);
    return;
  }

  const binding = findAccountBinding(settings, job.adapter);
  if (!binding) {
    sendError(job.jobId, 'missing_character_binding', `No character binding for ${job.adapter.name}:${job.adapter.platform}:${job.adapter.accountId}`);
    return;
  }

  try {
    const chatBinding = await ensureCharacterChat(job, binding);
    appendUserMessage(job);
    await context().saveChat();
    const reply = await context().generateQuietPrompt({ quietPrompt: job.message.text });
    sendResult(job, String(reply || '').trim(), chatBinding.characterId, chatBinding.chatId);
  } catch (error) {
    sendError(job.jobId, 'generation_failed', error instanceof Error ? error.message : String(error));
  }
}

function connectBridge() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.close();
  }
  socket = new WebSocket(settings.bridgeUrl);
  socket.addEventListener('open', () => {
    setStatus(`Connected to ${settings.bridgeUrl}`);
    socket.send(JSON.stringify({ type: 'hello', client: 'sillytavern-extension', version: '0.1.0' }));
  });
  socket.addEventListener('close', () => setStatus('Disconnected'));
  socket.addEventListener('error', () => setStatus('Connection error'));
  socket.addEventListener('message', async (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }
    if (payload.type === 'hello_ack') {
      setStatus(`Connected: ${payload.server}`);
      return;
    }
    if (payload.type === 'generate') {
      await handleGenerate(payload);
    }
  });
}

jQuery(async () => {
  loadSettings();
  await renderSettings();
  connectBridge();
});
```

- [ ] **Step 5: Verify extension files parse**

Run:

```bash
node --check sillytavern_extension/astrbot-smarter-rp/lib.js
node --check sillytavern_extension/astrbot-smarter-rp/index.js
node --test tests_js/astrbot_extension_lib.test.mjs
```

Expected: both `node --check` commands exit 0; JS helper tests pass.

---

### Task 6: Remove Old Runtime Files and Old Tests

**Files:**
- Delete: `smarter_rp/models.py`
- Delete: `smarter_rp/ids.py`
- Delete: `smarter_rp/services/`
- Delete: `smarter_rp/web/`
- Delete: `pages/`
- Delete: `webui/`
- Delete old tests except the focused tests listed in File Structure.

- [ ] **Step 1: Remove old runtime files**

Run:

```bash
rm -rf smarter_rp/models.py smarter_rp/ids.py smarter_rp/services smarter_rp/web pages webui
```

Expected: command exits 0.

- [ ] **Step 2: Remove old tests**

Run:

```bash
find tests -type f ! -name 'conftest.py' ! -name 'test_config.py' ! -name 'test_session_state.py' ! -name 'test_embedded_bridge.py' ! -name 'test_main_embedded_bridge.py' -delete
```

Expected: command exits 0.

- [ ] **Step 3: Verify no imports reference removed runtime**

Run:

```bash
grep -R "smarter_rp.services\|smarter_rp.web\|PromptBuilder\|RequestRewriter\|WebuiService" -n main.py smarter_rp tests || true
```

Expected: no output.

---

### Task 7: Documentation and Install Guidance

**Files:**
- Modify: `docs/install_backend.md`
- Create: `docs/install_extension.md`
- Keep: `docs/superpowers/specs/2026-05-16-embedded-tavern-adapter-design.md`
- Keep: `docs/superpowers/plans/2026-05-16-embedded-tavern-adapter.md`

- [ ] **Step 1: Update backend install guide**

Replace `docs/install_backend.md` with a short guide that says this project now embeds the AstrBot-side Bridge Server and needs the companion SillyTavern extension:

```markdown
# Embedded Tavern Adapter 安装指南

本插件会在 AstrBot 进程内启动本地 WebSocket Bridge Server，默认地址：

```text
ws://127.0.0.1:8008/ws
```

第一版不做认证，必须保持本机监听，不要暴露到公网。

## AstrBot 配置

```yaml
bridge:
  mode: "embedded"
  host: "127.0.0.1"
  port: 8008
  timeout_seconds: 120
behavior:
  default_enabled: true
  fallback_message: "RP 后端暂时不可用。"
```

## SillyTavern 要求

需要安装本仓库的配套扩展：`sillytavern_extension/astrbot-smarter-rp`。

扩展负责：

- 连接 AstrBot Bridge Server；
- 配置 `adapter/platform/account_id → character`；
- 为新的 AstrBot session 自动创建并复用 SillyTavern chat。

## 故障排查

- AstrBot 返回 fallback：确认 SillyTavern 已打开且扩展已连接。
- 提示缺少角色绑定：在扩展里添加当前 adapter/account 的角色绑定。
- 生成超时：调大 `bridge.timeout_seconds`，并确认 SillyTavern 模型后端可用。
- 端口占用：修改 AstrBot `bridge.port`，并同步修改扩展 Bridge URL。
```

- [ ] **Step 2: Add extension install guide**

Create `docs/install_extension.md`:

```markdown
# SillyTavern 扩展安装指南

把本仓库目录：

```text
sillytavern_extension/astrbot-smarter-rp
```

复制到 SillyTavern 的第三方扩展目录：

```text
public/scripts/extensions/third-party/astrbot-smarter-rp
```

重启或刷新 SillyTavern 后，在 Extensions 面板中启用 `AstrBot Smarter RP Bridge`。

## 配置步骤

1. Bridge URL 填写：`ws://127.0.0.1:8008/ws`。
2. 添加 account binding：
   - Adapter：AstrBot payload 中的 adapter name，例如 `aiocqhttp`。
   - Platform：平台名，例如 `qq`。
   - Account ID：机器人账号 ID。
   - Character ID / index：SillyTavern 当前角色列表中的角色索引。
3. 点击 Connect。

## 自动 chat 绑定

新的 AstrBot session 首次发消息时，扩展会自动创建 chat，名称格式：

```text
[AstrBot] {platform}-{session_display_name}-{session_id短码}
```

内部绑定依赖 `adapter/platform/account_id/session_id`，不依赖 chat 名称。
```

- [ ] **Step 3: Verify docs mention localhost-only boundary**

Run:

```bash
grep -R "127.0.0.1\|不要暴露到公网\|localhost" -n docs/install_backend.md docs/install_extension.md docs/superpowers/specs/2026-05-16-embedded-tavern-adapter-design.md
```

Expected: output includes all three docs.

---

### Task 8: Final Verification

**Files:**
- All files touched by previous tasks.

- [ ] **Step 1: Run Python tests**

Run:

```bash
python -m pytest -q tests
```

Expected: all Python tests pass.

- [ ] **Step 2: Run Python compile check**

Run:

```bash
python -m compileall -q main.py smarter_rp tests
```

Expected: no output and exit 0.

- [ ] **Step 3: Run JavaScript checks**

Run:

```bash
node --check sillytavern_extension/astrbot-smarter-rp/lib.js
node --check sillytavern_extension/astrbot-smarter-rp/index.js
node --test tests_js/astrbot_extension_lib.test.mjs
```

Expected: both syntax checks pass and all JS helper tests pass.

- [ ] **Step 4: Check remaining files**

Run:

```bash
find . -maxdepth 3 -type f | sort
```

Expected: output includes the minimal Python plugin files, focused tests, docs, and SillyTavern extension files; output does not include old `smarter_rp/services`, `smarter_rp/web`, `pages`, or `webui` files.

- [ ] **Step 5: Check git status**

Run:

```bash
git status --short
```

Expected: changed files match the implementation scope. Do not commit.

---

## Self-Review

- Spec coverage: this plan covers embedded Bridge Server, SillyTavern extension connection, account-to-character bindings, automatic session-to-chat bindings, generated chat names, `/rp on|off`, localhost-only no-auth boundary, WebSocket protocol, global serial generation, timeout handling, fallback behavior, and focused tests.
- Placeholder scan: no placeholder markers or deferred implementation notes are intentionally left in the plan.
- Type consistency: Python payload uses `accountId` and `displayName` to match the WebSocket protocol; extension helper keys use `adapter/platform/accountId/sessionId`; result messages use `generate_result` with `jobId` and `reply`.
