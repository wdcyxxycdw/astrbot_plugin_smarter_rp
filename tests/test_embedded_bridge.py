import asyncio

import pytest

from smarter_rp.embedded_bridge import (
    BridgeJobError,
    BridgeServer,
    BridgeTimeoutError,
    BridgeUnavailableError,
    PendingJob,
)


class FakeConnection:
    def __init__(self):
        self.sent = []

    async def send_json(self, payload):
        self.sent.append(payload)


class DisconnectingWebSocket:
    def __init__(self, server, replacement):
        self.server = server
        self.replacement = replacement
        self.replacement_pending = None

    async def accept(self):
        pass

    async def close(self, code):
        pass

    async def receive_json(self):
        replacement_id = await self.server.register_connection(self.replacement)
        self.replacement_pending = asyncio.get_running_loop().create_future()
        self.server._pending["new-job"] = PendingJob(future=self.replacement_pending, connection_id=replacement_id)
        from starlette.websockets import WebSocketDisconnect

        raise WebSocketDisconnect


@pytest.mark.asyncio
async def test_stale_websocket_disconnect_does_not_clear_new_pending_job():
    server = BridgeServer(host="127.0.0.1", port=8008, timeout_seconds=1)
    replacement = FakeConnection()
    old_websocket = DisconnectingWebSocket(server, replacement)

    await server.websocket_endpoint(old_websocket)

    assert replacement in server._connections.values()
    assert server._pending["new-job"].future is old_websocket.replacement_pending
    assert not old_websocket.replacement_pending.done()


@pytest.mark.asyncio
async def test_start_raises_when_uvicorn_exits_before_startup(monkeypatch):
    import smarter_rp.uvicorn_runner as uvicorn_runner

    class ExitingServer:
        def __init__(self, config):
            self.config = config
            self.started = False
            self.should_exit = False

        async def serve(self):
            return None

    monkeypatch.setattr(uvicorn_runner.uvicorn, "Server", ExitingServer)
    server = BridgeServer(host="127.0.0.1", port=8008, timeout_seconds=1)

    with pytest.raises(BridgeUnavailableError, match="failed to start"):
        await server.start()


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
async def test_generate_dispatches_concurrent_jobs_to_multiple_connections():
    server = BridgeServer(host="127.0.0.1", port=8008, timeout_seconds=1)
    first_connection = FakeConnection()
    second_connection = FakeConnection()
    await server.register_connection(first_connection)
    await server.register_connection(second_connection)

    first_task = asyncio.create_task(server.generate({"session": {"id": "session-1"}, "message": {"text": "one"}}))
    second_task = asyncio.create_task(server.generate({"session": {"id": "session-2"}, "message": {"text": "two"}}))
    await asyncio.sleep(0)

    assert len(first_connection.sent) == 1
    assert len(second_connection.sent) == 1
    await server.handle_client_message({"type": "generate_result", "jobId": first_connection.sent[0]["jobId"], "reply": "reply one"})
    await server.handle_client_message({"type": "generate_result", "jobId": second_connection.sent[0]["jobId"], "reply": "reply two"})

    assert await first_task == "reply one"
    assert await second_task == "reply two"


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
