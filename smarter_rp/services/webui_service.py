from __future__ import annotations

import secrets
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from smarter_rp.storage import Storage
from smarter_rp.web.app import create_app


class WebuiService:
    def __init__(self, token_path: Path, host: str, port: int, storage: Storage | None = None):
        self.token_path = token_path
        self.host = host
        self.port = port
        self.storage = storage
        self.token: str | None = None
        self.server: uvicorn.Server | None = None

    def ensure_token(self) -> str:
        if self.token is not None:
            return self.token

        if self.token_path.exists():
            token = self.token_path.read_text(encoding="utf-8").strip()
            if token:
                self.token = token
                return token

        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.token_path.write_text(self.token, encoding="utf-8")
        return self.token

    def build_app(self) -> FastAPI:
        return create_app(self.ensure_token(), storage=self.storage)

    def url_for_display(self) -> str:
        return f"http://{self.host}:{self.port}/?token={self.ensure_token()}"

    async def start(self) -> None:
        config = uvicorn.Config(
            create_app(self.ensure_token(), storage=self.storage),
            host=self.host,
            port=self.port,
            log_level="info",
        )
        self.server = uvicorn.Server(config)
        await self.server.serve()

    def request_stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
