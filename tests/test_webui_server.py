import asyncio

import pytest

from smarter_rp.config import SmarterRpConfig
from smarter_rp.web.server import WebUiServer


class FakeBindings:
    pass


class FakeClient:
    pass


def make_server(config=None):
    return WebUiServer(
        client=FakeClient(),
        bindings=FakeBindings(),
        config=config or SmarterRpConfig.default(),
    )


@pytest.mark.asyncio
async def test_start_rejects_public_host():
    config = SmarterRpConfig.default()
    config.webui["host"] = "0.0.0.0"
    server = make_server(config)

    with pytest.raises(ValueError, match="webui.host must remain local"):
        await server.start()


@pytest.mark.asyncio
async def test_repeated_start_does_not_start_second_uvicorn_server(monkeypatch):
    import smarter_rp.uvicorn_runner as uvicorn_runner

    servers = []

    class StartedServer:
        def __init__(self, config):
            self.config = config
            self.started = False
            self.should_exit = False
            servers.append(self)

        async def serve(self):
            self.started = True
            while not self.should_exit:
                await asyncio.sleep(0)

    monkeypatch.setattr(uvicorn_runner.uvicorn, "Server", StartedServer)
    server = make_server()

    await server.start()
    await server.start()
    await server.stop()

    assert len(servers) == 1


@pytest.mark.asyncio
async def test_stop_cleans_server_state(monkeypatch):
    import smarter_rp.uvicorn_runner as uvicorn_runner

    class StartedServer:
        def __init__(self, config):
            self.config = config
            self.started = False
            self.should_exit = False

        async def serve(self):
            self.started = True
            while not self.should_exit:
                await asyncio.sleep(0)

    monkeypatch.setattr(uvicorn_runner.uvicorn, "Server", StartedServer)
    server = make_server()

    await server.start()
    assert server._server is not None
    assert server._task is not None

    await server.stop()

    assert server._server is None
    assert server._task is None


@pytest.mark.asyncio
async def test_start_raises_and_cleans_state_when_task_exits_early(monkeypatch):
    import smarter_rp.uvicorn_runner as uvicorn_runner

    class ExitingServer:
        def __init__(self, config):
            self.config = config
            self.started = False
            self.should_exit = False

        async def serve(self):
            return None

    monkeypatch.setattr(uvicorn_runner.uvicorn, "Server", ExitingServer)
    server = make_server()

    with pytest.raises(RuntimeError, match="WebUI server failed to start"):
        await server.start()

    assert server._server is None
    assert server._task is None
