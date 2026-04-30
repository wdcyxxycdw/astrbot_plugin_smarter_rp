from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from smarter_rp.models import AccountProfile, Character, LorebookHit, RpMessage, RpSession
from smarter_rp.services.account_service import AccountService
from smarter_rp.services.character_service import CharacterService
from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.lorebook_matcher import LorebookMatcher, LorebookMatchResult
from smarter_rp.services.lorebook_service import LorebookService
from smarter_rp.services.prompt_builder import PromptBuilder
from smarter_rp.services.session_service import SessionService


_MISSING = object()


@dataclass(frozen=True, slots=True)
class RewriteResult:
    rewritten: bool
    reason: str
    account_profile_id: str | None
    session_id: str | None


class RequestRewriter:
    def __init__(
        self,
        accounts: AccountService,
        sessions: SessionService,
        characters: CharacterService,
        prompt_builder: PromptBuilder,
        debug: DebugService,
        history: HistoryService | None = None,
        lorebooks: LorebookService | None = None,
        lorebook_matcher: LorebookMatcher | None = None,
    ):
        self.accounts = accounts
        self.sessions = sessions
        self.characters = characters
        self.prompt_builder = prompt_builder
        self.debug = debug
        self.history = history
        self.lorebooks = lorebooks
        self.lorebook_matcher = lorebook_matcher

    def rewrite(self, event: object, request: object) -> RewriteResult:
        identity = self.accounts.extract_identity(event)
        profile = self.accounts.get_or_create(identity)
        session = self.sessions.get_or_create(self._origin(event), profile.id)

        if not profile.default_enabled:
            return RewriteResult(False, "account_disabled", profile.id, session.id)
        if session.paused:
            return RewriteResult(False, "session_paused", profile.id, session.id)

        self.debug.save_snapshot(session.id, "raw_request", self._request_snapshot(request))
        character = self.characters.resolve_character(
            session,
            profile,
            self._resolve_persona(event),
        )
        history_messages = self.history.list_messages(session.id) if self.history is not None else []
        current_input = self._text_or_empty(self._safe_getattr(request, "prompt"))
        match_result = self._match_lorebooks(profile, session, character, current_input, history_messages)
        if match_result is not None:
            session.last_lore_hits = self._serialize_lore_hits(match_result.hits)
            self.sessions.save_session_state(session)
        elif self.lorebooks is not None and self.lorebook_matcher is not None and session.last_lore_hits:
            session.last_lore_hits = []
            self.sessions.save_session_state(session)
        built_prompt = self.prompt_builder.build(
            profile,
            session,
            character,
            current_input=current_input,
            history_messages=history_messages,
            lorebook_buckets=match_result.buckets if match_result is not None else None,
        )
        system_prompt = "[Smarter RP]\n" + built_prompt

        setattr(request, "system_prompt", system_prompt)
        setattr(request, "contexts", self.prompt_builder.contexts_from_history(history_messages))
        self.debug.save_snapshot(session.id, "prompt", system_prompt)
        return RewriteResult(True, "rewritten", profile.id, session.id)

    def _origin(self, event: object) -> str:
        origin = self._text_or_empty(self._safe_getattr(event, "unified_msg_origin"))
        return origin or "unknown"

    def _match_lorebooks(
        self,
        profile: AccountProfile,
        session: RpSession,
        character: Character,
        current_input: str,
        history_messages: list[RpMessage],
    ) -> LorebookMatchResult | None:
        if self.lorebooks is None or self.lorebook_matcher is None:
            return None
        lorebook_ids = self._active_lorebook_ids(profile, session, character)
        if not lorebook_ids:
            return None
        entries = []
        for lorebook_id in lorebook_ids:
            entries.extend(self.lorebooks.list_entries(lorebook_id))
        return self.lorebook_matcher.match(entries, current_input, history_messages, session, character)

    def _active_lorebook_ids(self, profile: AccountProfile, session: RpSession, character: Character) -> list[str]:
        selected: list[str] = []
        base_ids = session.active_lorebook_ids if session.active_lorebook_ids else profile.default_lorebook_ids
        for lorebook_id in [*base_ids, *character.linked_lorebook_ids]:
            if lorebook_id and lorebook_id not in selected:
                selected.append(lorebook_id)
        return selected

    def _serialize_lore_hits(self, hits: list[LorebookHit]) -> list[dict[str, Any]]:
        return [asdict(hit) for hit in hits]

    def _resolve_persona(self, event: object) -> object | None:
        for name in ("persona", "astrbot_persona"):
            value = self._safe_getattr(event, name)
            if value is not _MISSING and value is not None:
                return value

        context = self._safe_getattr(event, "context")
        provider_manager = self._safe_getattr(context, "provider_manager")
        personality = self._safe_getattr(provider_manager, "curr_personality")
        if personality is not _MISSING and personality is not None:
            return personality
        return None

    def _request_snapshot(self, request: object) -> str:
        fields = {
            "prompt": self._preview(self._safe_getattr(request, "prompt")),
            "system_prompt": self._preview(self._safe_getattr(request, "system_prompt")),
            "contexts": self._preview(self._safe_getattr(request, "contexts")),
            "tools": self._preview(self._safe_getattr(request, "tools")),
            "image_urls": self._preview(self._safe_getattr(request, "image_urls")),
            "attachments": self._preview(self._safe_getattr(request, "attachments")),
        }
        return repr(fields)

    def _preview(self, value: object, limit: int = 1000) -> str:
        if value is _MISSING:
            return "<missing>"
        try:
            text = repr(value)
        except Exception:
            text = f"<{type(value).__name__}>"
        if len(text) > limit:
            return text[:limit] + "...<truncated>"
        return text

    def _safe_getattr(self, target: object, name: str) -> Any:
        if target is _MISSING or target is None:
            return _MISSING
        try:
            return getattr(target, name)
        except Exception:
            return _MISSING

    def _text_or_empty(self, value: object) -> str:
        if value is _MISSING or value is None:
            return ""
        return str(value)
