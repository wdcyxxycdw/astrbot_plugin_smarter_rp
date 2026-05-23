from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any

from smarter_rp.tavern_bindings import TavernBindingService


class TavernWorkerError(Exception):
    """Base error for TavernWorker operations."""


class InvalidTavernPayloadError(TavernWorkerError):
    """Raised when an AstrBot payload is missing required data."""


class MissingTavernBindingError(TavernWorkerError):
    """Raised when no account binding exists for an AstrBot account."""


class TavernCharacterNotFoundError(TavernWorkerError):
    """Raised when a bound SillyTavern character cannot be found."""


class EmptyTavernReplyError(TavernWorkerError):
    """Raised when SillyTavern generation returns an empty reply."""


@dataclass(frozen=True)
class _RequestContext:
    adapter: str
    platform: str
    account_id: str
    session_id: str
    session_display_name: str
    user_name: str
    message_text: str


@dataclass(frozen=True)
class _Character:
    id: str
    name: str
    avatar_url: str
    raw: dict[str, Any]


@dataclass
class _LockEntry:
    lock: asyncio.Lock
    ref_count: int = 0


def make_chat_name(platform: object, session_display_name: object, session_id: object) -> str:
    normalized_platform = _required_text(platform, "adapter.platform")
    normalized_display_name = _required_text(session_display_name, "session.displayName")
    normalized_session_id = _required_text(session_id, "session.id")
    short_id = normalized_session_id
    if len(normalized_session_id) > 10:
        short_id = f"{normalized_session_id[:6]}{normalized_session_id[-4:]}"
    return f"[AstrBot] {normalized_platform}-{normalized_display_name}-{short_id}"


def _required_text(value: object, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise InvalidTavernPayloadError(f"missing required payload field: {field}")
    return text


def _extract_payload(payload: dict[str, Any]) -> _RequestContext:
    if not isinstance(payload, dict):
        raise InvalidTavernPayloadError("payload must be a dict")

    adapter = payload.get("adapter")
    session = payload.get("session")
    user = payload.get("user")
    message = payload.get("message")
    if not isinstance(adapter, dict):
        raise InvalidTavernPayloadError("missing required payload field: adapter")
    if not isinstance(session, dict):
        raise InvalidTavernPayloadError("missing required payload field: session")
    if not isinstance(user, dict):
        raise InvalidTavernPayloadError("missing required payload field: user")
    if not isinstance(message, dict):
        raise InvalidTavernPayloadError("missing required payload field: message")

    return _RequestContext(
        adapter=_required_text(adapter.get("name"), "adapter.name"),
        platform=_required_text(adapter.get("platform"), "adapter.platform"),
        account_id=_required_text(adapter.get("accountId"), "adapter.accountId"),
        session_id=_required_text(session.get("id"), "session.id"),
        session_display_name=_required_text(session.get("displayName"), "session.displayName"),
        user_name=_required_text(user.get("name"), "user.name"),
        message_text=_required_text(message.get("text"), "message.text"),
    )


def _chat_header(character_name: str) -> dict[str, Any]:
    return {"user_name": character_name, "character_name": character_name}


def _user_message(user_name: str, text: str) -> dict[str, Any]:
    return {"name": user_name, "is_user": True, "mes": text}


def _assistant_message(character_name: str, text: str) -> dict[str, Any]:
    return {"name": character_name, "is_user": False, "mes": text}


class TavernWorker:
    def __init__(self, client: Any, bindings: TavernBindingService) -> None:
        self.client = client
        self.bindings = bindings
        self._locks: dict[tuple[str, str, str, str], _LockEntry] = {}
        self._chat_create_lock = asyncio.Lock()

    async def generate(self, payload: dict[str, Any]) -> str:
        context = _extract_payload(payload)
        lock_key = (context.adapter, context.platform, context.account_id, context.session_id)
        entry = self._locks.get(lock_key)
        if entry is None:
            entry = _LockEntry(asyncio.Lock())
            self._locks[lock_key] = entry
        entry.ref_count += 1
        try:
            async with entry.lock:
                return await self._generate_locked(context)
        finally:
            entry.ref_count -= 1
            if entry.ref_count == 0 and self._locks.get(lock_key) is entry:
                del self._locks[lock_key]

    async def _generate_locked(self, context: _RequestContext) -> str:
        account_binding = self.bindings.get_account_binding(context.adapter, context.platform, context.account_id)
        if account_binding is None:
            raise MissingTavernBindingError(
                "missing Tavern account binding for adapter/platform/accountId"
            )

        character = await self._get_character(account_binding.character_id)
        chat_binding = self.bindings.get_chat_binding(
            context.adapter, context.platform, context.account_id, context.session_id
        )
        if chat_binding is None or chat_binding.character_id != character.id:
            async with self._chat_create_lock:
                previous_chat_id = chat_binding.chat_id if chat_binding is not None else None
                chat_id = self._new_chat_id(context, previous_chat_id)
                chat: list[dict[str, Any]] = [_chat_header(character.name)]
                await self.client.save_chat(character.avatar_url, chat_id, chat, force=False)
                self.bindings.set_chat_binding(
                    context.adapter,
                    context.platform,
                    context.account_id,
                    context.session_id,
                    character.id,
                    chat_id,
                )
        else:
            chat_id = chat_binding.chat_id
            loaded_chat = await self.client.get_chat(character.avatar_url, chat_id)
            chat = list(loaded_chat or [_chat_header(character.name)])

        chat.append(_user_message(context.user_name, context.message_text))
        await self.client.save_chat(character.avatar_url, chat_id, chat, force=True)

        reply = await self.client.generate(
            {
                "character": {
                    "id": character.id,
                    "name": character.name,
                    "avatar_url": character.avatar_url,
                },
                "chat": {
                    "id": chat_id,
                    "messages": chat,
                },
                "adapter": {
                    "name": context.adapter,
                    "platform": context.platform,
                    "accountId": context.account_id,
                },
                "session": {
                    "id": context.session_id,
                    "displayName": context.session_display_name,
                },
                "user": {"name": context.user_name},
                "message": {"text": context.message_text},
                "messages": chat,
            }
        )
        reply_text = str(reply).strip() if reply is not None else ""
        if not reply_text:
            raise EmptyTavernReplyError("SillyTavern generation returned an empty reply")

        chat.append(_assistant_message(character.name, reply_text))
        await self.client.save_chat(character.avatar_url, chat_id, chat, force=True)
        return reply_text

    def _new_chat_id(self, context: _RequestContext, previous_chat_id: str | None = None) -> str:
        base_chat_id = make_chat_name(context.platform, context.session_display_name, context.session_id)
        current_key = (context.adapter, context.platform, context.account_id, context.session_id)
        conflicts = previous_chat_id == base_chat_id
        for binding in self.bindings.list_chat_bindings():
            binding_key = (binding.adapter, binding.platform, binding.account_id, binding.session_id)
            if binding_key != current_key and binding.chat_id == base_chat_id:
                conflicts = True
                break
        if not conflicts:
            return base_chat_id
        suffix = hashlib.sha256(context.session_id.encode("utf-8")).hexdigest()[:8]
        return f"{base_chat_id}-{suffix}"

    async def _get_character(self, character_id: str) -> _Character:
        characters = await self.client.list_characters()
        if not isinstance(characters, list):
            raise TavernCharacterNotFoundError("SillyTavern character list is not a list")

        try:
            index = int(character_id)
        except ValueError as error:
            raise TavernCharacterNotFoundError(f"character not found: {character_id}") from error
        if index < 0 or index >= len(characters):
            raise TavernCharacterNotFoundError(f"character not found: {character_id}")

        character = characters[index]
        if not isinstance(character, dict):
            raise TavernCharacterNotFoundError(f"character not found: {character_id}")
        name = _required_text(character.get("name"), "character.name")
        avatar_url = str(character.get("avatar") or character.get("avatar_url") or "").strip()
        if not avatar_url:
            raise TavernCharacterNotFoundError(f"character avatar missing: {character_id}")
        return _Character(id=character_id, name=name, avatar_url=avatar_url, raw=character)
