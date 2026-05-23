from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

import uvicorn


def _default_error(message: str, cause: BaseException | None = None) -> Exception:
    return RuntimeError(message)


class UvicornServerRunner:
    def __init__(
        self,
        config: uvicorn.Config,
        *,
        startup_error: Callable[[str, BaseException | None], Exception] = _default_error,
        startup_attempts: int = 250,
    ) -> None:
        self.server = uvicorn.Server(config)
        self.task: asyncio.Task[None] | None = None
        self.startup_error = startup_error
        self.startup_attempts = startup_attempts

    async def start(self) -> None:
        self.task = asyncio.create_task(self.server.serve())
        try:
            await self._wait_until_started()
        except Exception:
            self.server.should_exit = True
            if self.task is not None and not self.task.done():
                self.task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.task
            raise

    async def stop(self, *, timeout_seconds: float | None = None) -> None:
        self.server.should_exit = True
        if self.task is None:
            return
        with contextlib.suppress(asyncio.CancelledError):
            if timeout_seconds is None:
                await self.task
            else:
                await asyncio.wait_for(self.task, timeout=timeout_seconds)
        self.task = None

    async def _wait_until_started(self) -> None:
        assert self.task is not None
        for _ in range(self.startup_attempts):
            if self.server.started:
                return
            if self.task.done():
                exc = self.task.exception()
                if exc is not None:
                    raise self.startup_error("server failed to start", exc) from exc
                raise self.startup_error("server failed to start", None)
            await asyncio.sleep(0.02)
        self.server.should_exit = True
        raise self.startup_error("server startup timed out", None)
