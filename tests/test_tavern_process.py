import asyncio
from pathlib import Path

import pytest

from smarter_rp.tavern_process import TavernProcessError, TavernProcessManager


def run(coro):
    return asyncio.run(coro)


class FakeClient:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    async def health(self):
        self.calls += 1
        if self.results:
            result = self.results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return False

    async def aclose(self):
        pass


class FakeProcess:
    def __init__(self):
        self.terminated = False
        self.killed = False
        self.returncode = None
        self.waited = False

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        self.waited = True
        return self.returncode


class StubbornProcess(FakeProcess):
    async def wait(self):
        self.waited = True
        if self.terminated and not self.killed:
            await asyncio.sleep(10)
        return self.returncode


async def fast_sleep(_seconds):
    pass


def make_install(tmp_path):
    install_dir = tmp_path / "SillyTavern"
    install_dir.mkdir()
    (install_dir / "server.js").write_text("console.log('ok')", encoding="utf-8")
    return install_dir


def test_running_local_service_is_marked_external_and_not_started(tmp_path):
    install_dir = make_install(tmp_path)
    spawned = []

    async def fake_spawn(*args, **kwargs):
        spawned.append((args, kwargs))
        return FakeProcess()

    manager = TavernProcessManager(
        install_dir=install_dir,
        base_url="http://127.0.0.1:8001",
        startup_timeout_seconds=1,
        client_factory=lambda: FakeClient([True]),
        process_factory=fake_spawn,
        sleep=fast_sleep,
    )

    run(manager.start())
    run(manager.stop())

    assert manager.externally_managed is True
    assert spawned == []


def test_missing_server_js_reports_clear_error(tmp_path):
    install_dir = tmp_path / "SillyTavern"
    install_dir.mkdir()

    manager = TavernProcessManager(
        install_dir=install_dir,
        base_url="http://127.0.0.1:8001",
        client_factory=lambda: FakeClient([False]),
        sleep=fast_sleep,
    )

    with pytest.raises(TavernProcessError, match="server.js"):
        run(manager.start())


def test_startup_timeout_terminates_managed_process(tmp_path):
    install_dir = make_install(tmp_path)
    fake_process = FakeProcess()

    async def fake_spawn(*args, **kwargs):
        return fake_process

    manager = TavernProcessManager(
        install_dir=install_dir,
        base_url="http://127.0.0.1:8001",
        startup_timeout_seconds=0,
        client_factory=lambda: FakeClient([False, False, False]),
        process_factory=fake_spawn,
        sleep=fast_sleep,
    )

    with pytest.raises(TavernProcessError, match="ready"):
        run(manager.start())

    assert fake_process.terminated is True
    assert manager.managed_process is None


def test_startup_timeout_waits_exited_managed_process(tmp_path):
    install_dir = make_install(tmp_path)
    fake_process = FakeProcess()
    fake_process.returncode = 1

    async def fake_spawn(*args, **kwargs):
        return fake_process

    manager = TavernProcessManager(
        install_dir=install_dir,
        base_url="http://127.0.0.1:8001",
        startup_timeout_seconds=0,
        client_factory=lambda: FakeClient([False]),
        process_factory=fake_spawn,
        sleep=fast_sleep,
    )

    with pytest.raises(TavernProcessError, match="ready"):
        run(manager.start())

    assert fake_process.waited is True
    assert fake_process.terminated is False
    assert fake_process.killed is False
    assert manager.managed_process is None


def test_stop_only_terminates_managed_subprocess(tmp_path):
    install_dir = make_install(tmp_path)
    fake_process = FakeProcess()

    async def fake_spawn(*args, **kwargs):
        return fake_process

    manager = TavernProcessManager(
        install_dir=install_dir,
        base_url="http://localhost:8001",
        startup_timeout_seconds=1,
        client_factory=lambda: FakeClient([False, True]),
        process_factory=fake_spawn,
        sleep=fast_sleep,
    )

    run(manager.start())
    assert manager.externally_managed is False
    assert manager.managed_process is fake_process

    run(manager.stop())

    assert fake_process.terminated is True
    assert manager.managed_process is None

    external = TavernProcessManager(
        install_dir=install_dir,
        base_url="http://localhost:8001",
        client_factory=lambda: FakeClient([True]),
        sleep=fast_sleep,
    )
    external.managed_process = FakeProcess()
    external.externally_managed = True

    run(external.stop())

    assert external.managed_process.terminated is False


def test_repeated_start_keeps_managed_process_owned_and_stoppable(tmp_path):
    install_dir = make_install(tmp_path)
    fake_process = FakeProcess()
    clients = iter([FakeClient([False, True]), FakeClient([True])])
    spawn_count = 0

    async def fake_spawn(*args, **kwargs):
        nonlocal spawn_count
        spawn_count += 1
        return fake_process

    manager = TavernProcessManager(
        install_dir=install_dir,
        base_url="http://localhost:8001",
        startup_timeout_seconds=1,
        client_factory=lambda: next(clients),
        process_factory=fake_spawn,
        sleep=fast_sleep,
    )

    run(manager.start())
    run(manager.start())
    run(manager.stop())

    assert spawn_count == 1
    assert manager.externally_managed is False
    assert fake_process.terminated is True
    assert manager.managed_process is None


def test_start_clears_and_waits_for_process_that_exits_before_ready(tmp_path):
    install_dir = make_install(tmp_path)
    fake_process = FakeProcess()
    fake_process.returncode = 1

    async def fake_spawn(*args, **kwargs):
        return fake_process

    manager = TavernProcessManager(
        install_dir=install_dir,
        base_url="http://localhost:8001",
        startup_timeout_seconds=1,
        client_factory=lambda: FakeClient([False, False]),
        process_factory=fake_spawn,
        sleep=fast_sleep,
    )

    with pytest.raises(TavernProcessError, match="exited"):
        run(manager.start())

    assert fake_process.waited is True
    assert fake_process.terminated is False
    assert fake_process.killed is False
    assert manager.managed_process is None


def test_terminate_managed_process_kills_when_terminate_timeout_expires(tmp_path, monkeypatch):
    install_dir = make_install(tmp_path)
    fake_process = StubbornProcess()
    manager = TavernProcessManager(
        install_dir=install_dir,
        base_url="http://localhost:8001",
        client_factory=lambda: FakeClient([]),
    )
    manager.managed_process = fake_process

    async def immediate_timeout(awaitable, timeout):
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", immediate_timeout)

    run(manager._terminate_managed_process())

    assert fake_process.terminated is True
    assert fake_process.killed is True
    assert manager.managed_process is None


def test_manager_rejects_non_localhost_base_url(tmp_path):
    with pytest.raises(ValueError, match="localhost"):
        TavernProcessManager(install_dir=Path(tmp_path), base_url="http://10.0.0.2:8001")
