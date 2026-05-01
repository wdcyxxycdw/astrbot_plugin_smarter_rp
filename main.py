from __future__ import annotations

import asyncio
import json
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
from smarter_rp.services.memory_extractor import AstrBotMemoryProvider, MemoryExtractor, MemoryTriggerPolicy
from smarter_rp.services.memory_retrieval import MemoryRetriever
from smarter_rp.services.memory_service import MemoryService
from smarter_rp.services.prompt_builder import PromptBuilder
from smarter_rp.services.request_rewriter import RequestRewriter
from smarter_rp.services.session_service import SessionService
from smarter_rp.services.tool_service import ToolService
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
        self.memory = MemoryService(self.storage, self.sessions)
        self.memory_retriever = MemoryRetriever(
            self.memory,
            vector_top_k=int(self.config_model.memory.get("vector_top_k", 30)),
            rerank_top_k=int(self.config_model.memory.get("rerank_top_k", 10)),
            min_importance=int(self.config_model.memory.get("min_importance", 2)),
            max_hits=int(self.config_model.memory.get("max_injected_events", 10)),
            max_chars=int(self.config_model.prompt.get("max_memory_chars", 4000)),
            keyword_fallback_enabled=bool(self.config_model.memory.get("keyword_fallback_enabled", True)),
        )
        self.tool_service = ToolService(
            lorebook_service=self.lorebooks,
            lorebook_matcher=self.lorebook_matcher,
            memory_retriever=self.memory_retriever,
            mode=str(self.config_model.rewrite.get("tool_mode", "keep_subagents_only")),
            whitelist=list(self.config_model.rewrite.get("tool_whitelist", [])),
            preserve_mcp=bool(self.config_model.rewrite.get("preserve_mcp_tools", False)),
        )
        self.memory_extractor = MemoryExtractor(self.memory, self.history, self.debug)
        self.memory_trigger_policy = MemoryTriggerPolicy(
            auto_enabled=bool(self.config_model.memory.get("auto_enabled", True)),
            every_turns=int(self.config_model.memory.get("every_turns", 6)),
            history_chars_threshold=int(self.config_model.memory.get("history_chars_threshold", 12000)),
        )
        self.rewriter = RequestRewriter(
            accounts=self.accounts,
            sessions=self.sessions,
            characters=self.characters,
            prompt_builder=self.prompt_builder,
            debug=self.debug,
            history=self.history,
            lorebooks=self.lorebooks,
            lorebook_matcher=self.lorebook_matcher,
            memory_retriever=self.memory_retriever,
            tool_service=self.tool_service,
        )
        self.webui = WebuiService(
            token_path=data_dir / "webui_token",
            host=str(self.config_model.webui["host"]),
            port=int(self.config_model.webui["port"]),
            storage=self.storage,
        )
        self._webui_task: asyncio.Task | None = None
        self._memory_tasks: dict[str, asyncio.Task] = {}
        self._stopping = False

    async def initialize(self):
        self._stopping = False
        if self.config_model.webui["enabled"]:
            self.webui.ensure_token()
            self._webui_task = asyncio.create_task(self.webui.start())

    async def terminate(self):
        self._stopping = True
        self.webui.request_stop()
        memory_tasks = list(self._memory_tasks.values())
        if memory_tasks:
            await asyncio.gather(*memory_tasks, return_exceptions=True)
        self._memory_tasks.clear()
        if self._webui_task is not None:
            self._webui_task.cancel()
            try:
                await self._webui_task
            except asyncio.CancelledError:
                pass

    async def on_llm_request(self, event, req):
        self.rewriter.rewrite(event, req)

    async def on_using_llm_tool(self, event):
        self._save_tool_call_snapshot(event, "started")

    async def on_llm_tool_respond(self, event):
        status = "error" if self._safe_get(event, "error") is not None else "completed"
        self._save_tool_call_snapshot(event, status)

    @filter.llm_tool(name="sc_roll_dice")
    async def sc_roll_dice(self, event, expression: str, seed: str | int | None = None):
        """Roll dice for roleplay scenes.
        Args:
            expression(string): Dice expression like d20, 2d6+3, or 2d6-1
            seed(string): Optional deterministic seed
        """
        yield event.plain_result(json.dumps(self.tool_service.roll_dice(expression, seed), ensure_ascii=False))

    @filter.llm_tool(name="sc_query_lorebook")
    async def sc_query_lorebook(self, event, query: str):
        """Query active Smarter RP lorebooks.
        Args:
            query(string): Search text for lorebook matching
        """
        profile, session, character, history_messages = self._tool_context(event)
        result = self.tool_service.query_lorebook(profile, session, character, query, history_messages)
        yield event.plain_result(json.dumps(result, ensure_ascii=False))

    @filter.llm_tool(name="sc_search_memory")
    async def sc_search_memory(self, event, query: str):
        """Search Smarter RP session memory.
        Args:
            query(string): Search text for memory retrieval
        """
        _profile, session, _character, history_messages = self._tool_context(event)
        result = self.tool_service.search_memory(session, query, history_messages, lore_hits=[])
        yield event.plain_result(json.dumps(result, ensure_ascii=False))

    async def on_agent_done(self, event, response):
        session = self.sessions.get_or_create(self._origin(event), None)
        user_text = self._extract_user_text(event)
        assistant_text = self._extract_assistant_text(response)
        if user_text:
            self.history.append_message(session.id, role="user", speaker="User", content=user_text)
        if assistant_text:
            self.history.append_message(session.id, role="assistant", speaker="Assistant", content=assistant_text)
        if user_text or assistant_text:
            self._schedule_memory_job(session.id)

    def _tool_context(self, event):
        profile = self.accounts.get_or_create(self.accounts.extract_identity(event))
        session = self.sessions.get_or_create(self._origin(event), profile.id)
        character = self.characters.resolve_character(session, profile, self.rewriter._resolve_persona(event))
        history_messages = self.history.list_messages(session.id)
        return profile, session, character, history_messages

    def _schedule_memory_job(self, session_id: str) -> None:
        if not all(hasattr(self, name) for name in ("_memory_tasks", "memory_extractor", "memory_trigger_policy", "debug")):
            return
        if getattr(self, "_stopping", False):
            return
        existing = self._memory_tasks.get(session_id)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(self._run_memory_job(session_id))
        self._memory_tasks[session_id] = task
        task.add_done_callback(lambda done_task: self._forget_memory_task(session_id, done_task))

    def _forget_memory_task(self, session_id: str, done_task: asyncio.Task) -> None:
        if self._memory_tasks.get(session_id) is done_task:
            self._memory_tasks.pop(session_id, None)

    async def _run_memory_job(self, session_id: str) -> None:
        if getattr(self, "_stopping", False):
            return
        try:
            await asyncio.to_thread(
                self.memory_extractor.run_if_needed,
                session_id,
                self.memory_trigger_policy,
                self._resolve_memory_provider(),
            )
        except Exception as exc:
            if not getattr(self, "_stopping", False):
                self.debug.save_snapshot(
                    session_id,
                    "memory",
                    json.dumps(
                        {"kind": "background", "status": "error", "error": str(exc)},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )

    def _save_tool_call_snapshot(self, event, status: str) -> None:
        try:
            session = self.sessions.get_or_create(self._origin(event), None)
            payload = {
                "kind": "tool_call",
                "status": status,
                "tool_name": self._tool_event_name(event),
            }
            if status == "started":
                payload["arguments_preview"] = self._preview(self._first_event_value(event, ("arguments", "args", "params", "input")))
            elif status == "error":
                payload["error_preview"] = self._preview(self._safe_get(event, "error"))
            else:
                payload["result_preview"] = self._preview(self._first_event_value(event, ("result", "response", "content", "output")))
            self.debug.save_snapshot(session.id, "tools", json.dumps(payload, ensure_ascii=False, sort_keys=True))
        except Exception:
            return

    def _tool_event_name(self, event) -> str:
        value = self._first_event_value(event, ("tool_name", "name", "func_name", "function_name"))
        if value is None:
            value = self._first_nested_event_value(
                event,
                ("tool", "func_tool", "tool_call", "function"),
                ("tool_name", "name", "func_name", "function_name"),
            )
        return str(value) if value is not None else ""

    def _first_event_value(self, event, names: tuple[str, ...]):
        for name in names:
            value = self._safe_get(event, name)
            if value is not None:
                return value
        return None

    def _first_nested_event_value(self, event, parent_names: tuple[str, ...], child_names: tuple[str, ...]):
        for parent_name in parent_names:
            parent = self._safe_get(event, parent_name)
            value = self._first_event_value(parent, child_names)
            if value is not None:
                return value
        return None

    def _preview(self, value, limit: int = 500) -> str:
        try:
            text = repr(value)
        except Exception:
            text = f"<{type(value).__name__}>"
        if len(text) > limit:
            return text[:limit] + "...<truncated>"
        return text

    def _resolve_memory_provider(self):
        provider = self._provider_by_id(self.config_model.memory.get("memory_provider_id"))
        if provider is None:
            provider = self._provider_by_id(self.config_model.memory.get("summary_provider_id"))
        if provider is None:
            provider = self._current_provider()
        return AstrBotMemoryProvider(provider) if provider is not None else None

    def _provider_by_id(self, provider_id) -> object | None:
        provider_id = self._string_or_empty(provider_id)
        if not provider_id:
            return None
        provider_manager = self._provider_manager()
        if provider_manager is None:
            return None
        for method_name in ("get_provider_by_id", "get_provider", "get", "find_provider"):
            method = self._safe_get(provider_manager, method_name)
            if callable(method):
                try:
                    provider = method(provider_id)
                except Exception:
                    provider = None
                if provider is not None:
                    return provider
        providers = self._safe_get(provider_manager, "providers")
        if isinstance(providers, dict):
            return providers.get(provider_id)
        return None

    def _current_provider(self) -> object | None:
        provider_manager = self._provider_manager()
        if provider_manager is None:
            return None
        for name in ("curr_provider", "current_provider", "provider"):
            provider = self._safe_get(provider_manager, name)
            if provider is not None:
                return provider
        return None

    def _provider_manager(self) -> object | None:
        context = self._safe_get(self, "context")
        return self._safe_get(context, "provider_manager")

    def _origin(self, event) -> str:
        origin = self._string_or_empty(self._safe_get(event, "unified_msg_origin"))
        if not origin:
            origin = self._string_or_empty(self._first_nested_event_value(event, ("event", "message_obj"), ("unified_msg_origin",)))
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
            message = f"Smarter RP WebUI: {self.webui.url_for_display()}"
            if self.webui.host == "0.0.0.0":
                message += "\n警告：绑定 0.0.0.0 会暴露到可访问网络，请只在可信网络中使用。"
            yield event.plain_result(message)
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
        if isinstance(obj, dict):
            return obj.get(attr)
        try:
            return getattr(obj, attr, None)
        except Exception:
            return None

    def _resolve_data_dir(self) -> Path:
        data_dir = Path("data/plugin_data/astrbot_plugin_smarter_rp")
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
