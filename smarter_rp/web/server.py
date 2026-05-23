from __future__ import annotations

import asyncio

import uvicorn

from smarter_rp.config import SmarterRpConfig, ensure_local_host
from smarter_rp.uvicorn_runner import UvicornServerRunner
from smarter_rp.tavern_bindings import TavernBindingService
from smarter_rp.web.app import create_web_app


class WebUiServer:
    def __init__(
        self,
        *,
        client: object,
        bindings: TavernBindingService,
        config: SmarterRpConfig,
        webui_token: str | None = None,
    ) -> None:
        self.client = client
        self.bindings = bindings
        self.config = config
        self.webui_token = webui_token
        self._runner: UvicornServerRunner | None = None
        self._lifecycle_lock = asyncio.Lock()

    @property
    def _server(self) -> uvicorn.Server | None:
        return self._runner.server if self._runner is not None else None

    @property
    def _task(self) -> asyncio.Task[None] | None:
        return self._runner.task if self._runner is not None else None

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._task and not self._task.done():
                return

            host = str(self.config.webui.get("host", "127.0.0.1"))
            ensure_local_host(host, "webui.host must remain local")

            app = create_web_app(
                client=self.client,
                bindings=self.bindings,
                config=self.config,
                webui_token=self.webui_token,
            )
            uvicorn_config = uvicorn.Config(
                app,
                host=host,
                port=int(self.config.webui.get("port", 8010)),
                log_level="warning",
                access_log=False,
            )
            runner = UvicornServerRunner(
                uvicorn_config,
                startup_error=lambda message, cause: RuntimeError(
                    "WebUI server startup timed out" if "timed out" in message else "WebUI server failed to start"
                ),
            )
            self._runner = runner
            try:
                await runner.start()
            except Exception:
                self._runner = None
                raise

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            runner = self._runner
            if runner is None:
                return
            try:
                await runner.stop(timeout_seconds=5)
            finally:
                self._runner = None
