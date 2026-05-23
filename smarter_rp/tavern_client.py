from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from smarter_rp.config import ensure_local_host

SENSITIVE_RE = re.compile(
    r"(?i)(authorization|cookie|token|password|api[_-]?key|key)\s*[:=]?\s*([^\s,;}]+)"
)


class SillyTavernClientError(Exception):
    """Base error for SillyTavern client operations."""


class SillyTavernRequestError(SillyTavernClientError):
    """Raised when SillyTavern returns a non-success response or cannot be reached."""


class SillyTavernGenerationError(SillyTavernClientError):
    """Raised when generation succeeds but does not contain a usable reply."""


def _ensure_localhost(base_url: str) -> None:
    host = urlparse(base_url).hostname
    ensure_local_host(host or "", "SillyTavern base_url must use localhost/127.0.0.1/::1")


def _sanitize(value: Any) -> str:
    text = str(value)
    text = SENSITIVE_RE.sub(lambda match: f"{match.group(1)} [REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[^\s,;}]+", "Bearer [REDACTED]", text)
    for word in ("Authorization", "Cookie", "token", "password", "api_key", "apikey", "key"):
        text = re.sub(re.escape(word), "[REDACTED]", text, flags=re.IGNORECASE)
    return text[:1000]


class SillyTavernClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 120,
        auth: dict[str, Any] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        _ensure_localhost(base_url)
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.auth = auth or {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_seconds,
            headers=self._headers(),
            auth=self._basic_auth(),
            transport=transport,
        )

    async def __aenter__(self) -> "SillyTavernClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        if self.auth.get("enabled") and self.auth.get("token"):
            return {"Authorization": f"Bearer {self.auth['token']}"}
        return {}

    def _basic_auth(self) -> httpx.BasicAuth | None:
        if self.auth.get("enabled") and self.auth.get("username"):
            return httpx.BasicAuth(str(self.auth.get("username", "")), str(self.auth.get("password", "")))
        return None

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise SillyTavernRequestError(f"SillyTavern request failed: {_sanitize(error)}") from error

        if response.status_code < 200 or response.status_code >= 300:
            body = response.text
            raise SillyTavernRequestError(
                f"SillyTavern request {method} {path} failed with HTTP {response.status_code}: {_sanitize(body)}"
            )

        if not response.content:
            return None
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            return response.json()
        try:
            return response.json()
        except json.JSONDecodeError:
            return response.text

    async def health(self) -> bool:
        try:
            response = await self._client.get("/")
            return 200 <= response.status_code < 300
        except httpx.HTTPError:
            return False

    async def get_settings(self) -> Any:
        return await self._request("POST", "/api/settings/get", json={})

    async def save_settings(self, settings: dict[str, Any]) -> Any:
        return await self._request("POST", "/api/settings/save", json=settings)

    async def list_characters(self) -> Any:
        return await self._request("POST", "/api/characters/all", json={})

    async def import_character(
        self,
        filename: str,
        content: bytes,
        *,
        file_type: str,
        preserved_name: str | None = None,
    ) -> Any:
        data = {"file_type": file_type}
        if preserved_name:
            data["preserved_name"] = preserved_name
        return await self._request(
            "POST",
            "/api/characters/import",
            data=data,
            files={"avatar": (filename, content, "application/octet-stream")},
        )

    async def list_worldbooks(self) -> Any:
        return await self._request("POST", "/api/worldinfo/list", json={})

    async def import_worldbook(self, filename: str, worldbook: dict[str, Any] | bytes | str) -> Any:
        if isinstance(worldbook, bytes):
            content = worldbook
        elif isinstance(worldbook, str):
            content = worldbook.encode("utf-8")
        else:
            content = json.dumps(worldbook, ensure_ascii=False).encode("utf-8")
        return await self._request(
            "POST",
            "/api/worldinfo/import",
            files={"avatar": (filename, content, "application/json")},
        )

    async def get_chat(self, avatar_url: str, file_name: str) -> Any:
        return await self._request(
            "POST",
            "/api/chats/get",
            json={"avatar_url": avatar_url, "file_name": file_name},
        )

    async def save_chat(self, avatar_url: str, file_name: str, chat: list[dict[str, Any]], *, force: bool = False) -> Any:
        return await self._request(
            "POST",
            "/api/chats/save",
            json={"avatar_url": avatar_url, "file_name": file_name, "chat": chat, "force": force},
        )

    async def generate(self, payload: dict[str, Any]) -> str:
        data = await self._request("POST", "/api/backends/chat-completions/generate", json=payload)
        if isinstance(data, dict) and data.get("error"):
            raise SillyTavernGenerationError(f"SillyTavern generation failed: {_sanitize(data.get('error'))}")

        reply = ""
        if isinstance(data, dict):
            if "choices" in data:
                choices = data["choices"]
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    raise SillyTavernGenerationError("SillyTavern generation returned an unexpected response")
                message = choices[0].get("message", {})
                if not isinstance(message, dict):
                    raise SillyTavernGenerationError("SillyTavern generation returned an unexpected response")
                reply = str(message.get("content") or "")
            if not reply:
                reply = str(data.get("content") or "")
        if not reply.strip():
            raise SillyTavernGenerationError("SillyTavern generation returned an empty reply")
        return reply
