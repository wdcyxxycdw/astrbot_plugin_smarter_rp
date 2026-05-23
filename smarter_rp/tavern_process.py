from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from smarter_rp.config import ensure_local_host

from .tavern_client import SillyTavernClient


class TavernProcessError(Exception):
    """Raised when SillyTavern cannot be started or stopped safely."""


ProcessFactory = Callable[..., Awaitable[Any]]
SleepFunc = Callable[[float], Awaitable[None]]
ClientFactory = Callable[[], Any]


def _ensure_localhost(base_url: str) -> None:
    host = urlparse(base_url).hostname
    ensure_local_host(host or "", "SillyTavern base_url must use localhost/127.0.0.1/::1")


class TavernProcessManager:
    def __init__(
        self,
        *,
        install_dir: str | Path,
        base_url: str,
        startup_timeout_seconds: float = 60,
        request_timeout_seconds: float = 120,
        auth: dict[str, Any] | None = None,
        node_executable: str = "node",
        client_factory: ClientFactory | None = None,
        process_factory: ProcessFactory | None = None,
        sleep: SleepFunc = asyncio.sleep,
    ) -> None:
        _ensure_localhost(base_url)
        self.install_dir = Path(install_dir).expanduser()
        self.base_url = base_url
        self.startup_timeout_seconds = startup_timeout_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.auth = auth or {}
        self.node_executable = node_executable
        self.client_factory = client_factory or self._default_client_factory
        self.process_factory = process_factory or asyncio.create_subprocess_exec
        self.sleep = sleep
        self.managed_process: Any | None = None
        self.externally_managed = False

    def _default_client_factory(self) -> SillyTavernClient:
        return SillyTavernClient(
            self.base_url,
            timeout_seconds=self.request_timeout_seconds,
            auth=self.auth,
        )

    async def start(self) -> None:
        process = self.managed_process
        if process is not None:
            if getattr(process, "returncode", None) is None:
                return
            self.managed_process = None
            await process.wait()

        client = self.client_factory()
        try:
            if await self._is_ready(client):
                self.externally_managed = True
                return

            self._validate_installation()
            self.managed_process = await self.process_factory(
                self.node_executable,
                "server.js",
                cwd=str(self.install_dir),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )

            try:
                if await self._wait_until_ready(client):
                    self.externally_managed = False
                    return
            except Exception:
                process = self.managed_process
                if process is not None and getattr(process, "returncode", None) is not None:
                    self.managed_process = None
                    await process.wait()
                raise

            await self._terminate_managed_process()
            raise TavernProcessError(f"SillyTavern did not become ready at {self.base_url}")
        finally:
            close = getattr(client, "aclose", None)
            if close is not None:
                await close()

    async def stop(self) -> None:
        if self.externally_managed:
            return
        await self._terminate_managed_process()

    def _validate_installation(self) -> None:
        if not self.install_dir.exists() or not self.install_dir.is_dir():
            raise TavernProcessError(f"SillyTavern install directory does not exist: {self.install_dir}")
        server_js = self.install_dir / "server.js"
        if not server_js.is_file():
            raise TavernProcessError(f"SillyTavern server.js not found in install directory: {server_js}")
        if shutil.which(self.node_executable) is None:
            raise TavernProcessError(f"Node.js executable not found: {self.node_executable}")

    async def _is_ready(self, client: Any) -> bool:
        try:
            return bool(await client.health())
        except Exception:
            return False

    async def _wait_until_ready(self, client: Any) -> bool:
        deadline = time.monotonic() + self.startup_timeout_seconds
        while time.monotonic() < deadline:
            if await self._is_ready(client):
                return True
            process = self.managed_process
            if process is not None and getattr(process, "returncode", None) is not None:
                raise TavernProcessError("SillyTavern process exited before becoming ready")
            await self.sleep(0.5)
        return False

    async def _terminate_managed_process(self) -> None:
        process = self.managed_process
        if process is None:
            return
        self.managed_process = None
        if getattr(process, "returncode", None) is not None:
            await process.wait()
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
