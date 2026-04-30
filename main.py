from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register

from smarter_rp.config import SmarterRpConfig
from smarter_rp.services.account_service import AccountService
from smarter_rp.services.character_service import CharacterService
from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.lorebook_matcher import LorebookMatcher
from smarter_rp.services.lorebook_service import LorebookService
from smarter_rp.services.prompt_builder import PromptBuilder
from smarter_rp.services.request_rewriter import RequestRewriter
from smarter_rp.services.session_service import SessionService
from smarter_rp.services.webui_service import WebuiService
from smarter_rp.storage import Storage


@register("smarter_rp", "smarter-rp", "WebUI-first roleplay prompt orchestration", "0.1.0")
class SmarterRpPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        super().__init__(context)
        self.config_model = SmarterRpConfig.from_mapping(config or {})
        data_dir = self._resolve_data_dir()

        self.storage = Storage(data_dir / "smarter_rp.db")
        self.storage.initialize()
        self.accounts = AccountService(self.storage)
        self.sessions = SessionService(self.storage)
        self.characters = CharacterService(self.storage)
        self.characters.ensure_default_character()
        self.history = HistoryService(
            self.storage,
            self.sessions,
            max_history_messages=self.config_model.history.get("max_history_messages", 40),
        )
        self.lorebooks = LorebookService(self.storage)
        self.lorebook_matcher = LorebookMatcher(
            max_hits=int(self.config_model.lorebook.get("max_hits", 12)),
            max_chars=int(self.config_model.prompt.get("max_lore_chars", 6000)),
            max_recursive_depth=int(self.config_model.lorebook.get("max_recursive_depth", 2)),
        )
        self.prompt_builder = PromptBuilder(
            max_prompt_chars=int(self.config_model.prompt.get("max_prompt_chars", 4000))
        )
        self.debug = DebugService(self.storage)
        self.rewriter = RequestRewriter(
            accounts=self.accounts,
            sessions=self.sessions,
            characters=self.characters,
            prompt_builder=self.prompt_builder,
            debug=self.debug,
            history=self.history,
            lorebooks=self.lorebooks,
            lorebook_matcher=self.lorebook_matcher,
        )
        self.webui = WebuiService(
            token_path=data_dir / "webui_token",
            host=str(self.config_model.webui["host"]),
            port=int(self.config_model.webui["port"]),
            storage=self.storage,
        )
        self._webui_task: asyncio.Task | None = None

    async def initialize(self):
        if self.config_model.webui["enabled"]:
            self.webui.ensure_token()
            self._webui_task = asyncio.create_task(self.webui.start())

    async def terminate(self):
        self.webui.request_stop()
        if self._webui_task is not None:
            self._webui_task.cancel()
            try:
                await self._webui_task
            except asyncio.CancelledError:
                pass

    async def on_llm_request(self, event, req):
        self.rewriter.rewrite(event, req)

    async def on_agent_done(self, event, response):
        session = self.sessions.get_or_create(self._origin(event), None)
        user_text = self._extract_user_text(event)
        assistant_text = self._extract_assistant_text(response)
        if user_text:
            self.history.append_message(session.id, role="user", speaker="User", content=user_text)
        if assistant_text:
            self.history.append_message(session.id, role="assistant", speaker="Assistant", content=assistant_text)

    def _origin(self, event) -> str:
        origin = self._string_or_empty(self._safe_get(event, "unified_msg_origin"))
        return origin or "unknown"

    def _extract_user_text(self, event) -> str:
        for name in ("message_str", "message", "raw_message"):
            text = self._string_or_empty(self._safe_get(event, name))
            if text:
                return text
        return ""

    def _extract_assistant_text(self, response) -> str:
        if isinstance(response, str):
            return self._string_or_empty(response)
        for name in ("completion_text", "result", "content", "text"):
            text = self._string_or_empty(self._safe_get(response, name))
            if text:
                return text
        return ""

    def _string_or_empty(self, value) -> str:
        if isinstance(value, str):
            return value.strip()
        return ""

    @filter.command("rp")
    async def rp_root(self, event, subcommand: str | None = None):
        command = (subcommand or "status").strip().lower()

        if command == "status":
            yield event.plain_result(
                "smarter_rp installed. RP rewrite is default-on in configuration; use /rp webui to open WebUI."
            )
            return
        if command == "webui":
            if not self.config_model.webui["enabled"]:
                yield event.plain_result("Smarter RP WebUI is disabled.")
                return
            if self.webui.port == 0:
                yield event.plain_result(
                    "Smarter RP WebUI is using a random port. Phase 0 requires configuring a fixed port before this command can show an accessible link."
                )
                return
            if not self._is_private_event(event):
                yield event.plain_result("请在私聊中使用 /rp webui 获取 WebUI 管理链接。")
                return
            yield event.plain_result(f"Smarter RP WebUI: {self.webui.url_for_display()}")
            return
        if command == "pause":
            session = self.sessions.get_or_create(event.unified_msg_origin, None)
            self.sessions.set_paused(session.id, True)
            yield event.plain_result("Smarter RP paused for this conversation.")
            return
        if command == "resume":
            session = self.sessions.get_or_create(event.unified_msg_origin, None)
            self.sessions.set_paused(session.id, False)
            yield event.plain_result("Smarter RP resumed for this conversation.")
            return
        if command == "debug":
            session = self.sessions.get_or_create(event.unified_msg_origin, None)
            latest = self.debug.list_snapshots(
                limit=1,
                session_id=session.id,
                snapshot_type="prompt",
            )
            latest_id = latest[0].id if latest else "none"
            paused = "yes" if session.paused else "no"
            yield event.plain_result(
                f"Smarter RP debug: paused={paused}; latest prompt snapshot={latest_id}. Open WebUI Debug page for details."
            )
            return

        yield event.plain_result("Available commands: /rp status, /rp webui, /rp pause, /rp resume, /rp debug")
        return

    def _is_private_event(self, event) -> bool:
        markers = self._collect_event_markers(event)
        group_markers = ("group", "channel", "guild", "room", "discuss")
        if any(marker in group_markers or any(group_marker in marker for group_marker in group_markers) for marker in markers):
            return False

        private_markers = ("private", "friend", "direct", "dm")
        return any(marker in private_markers or any(private_marker in marker for private_marker in private_markers) for marker in markers)

    def _collect_event_markers(self, event) -> list[str]:
        markers: list[str] = []
        self._append_event_marker(markers, self._safe_get(event, "is_private"))
        self._append_event_marker(markers, self._safe_get(event, "unified_msg_origin"))

        message_obj = self._safe_get(event, "message_obj")
        self._append_event_marker(markers, message_obj)
        for attr in ("message_type", "chat_type", "type", "scene", "source", "origin", "session_type"):
            self._append_event_marker(markers, self._safe_get(message_obj, attr))

        return markers

    def _append_event_marker(self, markers: list[str], value) -> None:
        try:
            if callable(value):
                value = value()
        except Exception:
            return

        if isinstance(value, bool):
            markers.append("private" if value else "group")
            return
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized:
                markers.append(normalized)

    def _safe_get(self, obj, attr: str):
        if obj is None:
            return None
        try:
            return getattr(obj, attr, None)
        except Exception:
            return None

    def _resolve_data_dir(self) -> Path:
        data_dir = Path("data/plugin_data/astrbot_plugin_smarter_rp")
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
