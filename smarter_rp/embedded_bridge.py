from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from smarter_rp.uvicorn_runner import UvicornServerRunner


class BridgeUnavailableError(Exception):
    pass


class BridgeTimeoutError(Exception):
    pass


class BridgeJobError(Exception):
    pass


class JsonConnection(Protocol):
    async def send_json(self, payload: dict[str, Any]) -> None: ...


@dataclass
class PendingJob:
    future: asyncio.Future[str]
    connection_id: str


class BridgeServer:
    def __init__(self, host: str, port: int, timeout_seconds: float):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.app = FastAPI()
        self._connections: dict[str, JsonConnection] = {}
        self._connection_job_counts: dict[str, int] = {}
        self._connection_lock = asyncio.Lock()
        self._pending: dict[str, PendingJob] = {}
        self._runner: UvicornServerRunner | None = None
        self.app.websocket("/ws")(self.websocket_endpoint)

    @property
    def pending_job_count(self) -> int:
        return len(self._pending)

    async def start(self) -> None:
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
        runner = UvicornServerRunner(
            config,
            startup_error=lambda message, cause: BridgeUnavailableError(
                "bridge server startup timed out" if "timed out" in message else "bridge server failed to start"
            ),
            startup_attempts=50,
        )
        self._runner = runner
        try:
            await runner.start()
        except Exception:
            self._runner = None
            raise

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.stop()
        self._runner = None
        for pending in list(self._pending.values()):
            if not pending.future.done():
                pending.future.set_exception(BridgeUnavailableError("bridge server stopped"))
        self._pending.clear()
        self._connections.clear()
        self._connection_job_counts.clear()

    async def websocket_endpoint(self, websocket: WebSocket) -> None:
        await websocket.accept()
        connection_id = await self.register_connection(websocket)
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
            await self.unregister_connection(connection_id, websocket)

    async def register_connection(self, connection: JsonConnection) -> str:
        connection_id = str(uuid.uuid4())
        async with self._connection_lock:
            self._connections[connection_id] = connection
            self._connection_job_counts[connection_id] = 0
        return connection_id

    async def unregister_connection(self, connection_id: str, connection: JsonConnection) -> None:
        async with self._connection_lock:
            if self._connections.get(connection_id) is not connection:
                return
            del self._connections[connection_id]
            self._connection_job_counts.pop(connection_id, None)
            for job_id, pending in list(self._pending.items()):
                if pending.connection_id == connection_id and not pending.future.done():
                    pending.future.set_exception(BridgeUnavailableError("sillytavern extension disconnected"))

    async def handle_client_message(self, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("jobId") or "")
        pending = self._pending.get(job_id)
        if pending is None or pending.future.done():
            return

        message_type = payload.get("type")
        if message_type == "generate_result":
            reply = payload.get("reply")
            if not isinstance(reply, str) or not reply.strip():
                pending.future.set_exception(BridgeJobError("missing reply"))
                return
            pending.future.set_result(reply)
            return

        if message_type == "generate_error":
            code = str(payload.get("code") or "generate_error")
            message = str(payload.get("message") or code)
            pending.future.set_exception(BridgeJobError(f"{code}: {message}"))

    async def generate(self, payload: dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        async with self._connection_lock:
            if not self._connections:
                raise BridgeUnavailableError("sillytavern extension is not connected")

            connection_id, connection = min(
                self._connections.items(),
                key=lambda item: self._connection_job_counts.get(item[0], 0),
            )
            self._pending[job_id] = PendingJob(future=future, connection_id=connection_id)
            self._connection_job_counts[connection_id] = self._connection_job_counts.get(connection_id, 0) + 1

        job = {"type": "generate", "jobId": job_id, **payload}
        try:
            await connection.send_json(job)
            return await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except TimeoutError as exc:
            raise BridgeTimeoutError("sillytavern generation timed out") from exc
        finally:
            self._pending.pop(job_id, None)
            async with self._connection_lock:
                if connection_id in self._connection_job_counts:
                    self._connection_job_counts[connection_id] = max(0, self._connection_job_counts[connection_id] - 1)
