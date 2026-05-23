from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register

from smarter_rp.config import SmarterRpConfig
from smarter_rp.embedded_bridge import BridgeJobError, BridgeServer, BridgeTimeoutError, BridgeUnavailableError
from smarter_rp.session_state import SessionStateService
from smarter_rp.storage import Storage
from smarter_rp.tavern_bindings import TavernBindingService
from smarter_rp.tavern_client import SillyTavernClient, SillyTavernClientError
from smarter_rp.tavern_process import TavernProcessError, TavernProcessManager
from smarter_rp.tavern_worker import MissingTavernBindingError, TavernWorker, TavernWorkerError
from smarter_rp.web.auth import resolve_token
from smarter_rp.web.server import WebUiServer


def _message_handler_decorator():
    decorator = getattr(filter, "event_message_type", None)
    event_message_type = getattr(filter, "EventMessageType", None)
    all_message_types = getattr(event_message_type, "ALL", None)
    if callable(decorator) and all_message_types is not None:
        return decorator(all_message_types)
    if callable(decorator):
        return decorator()
    return lambda func: func


@register("smarter_rp", "smarter-rp", "AstrBot embedded Tavern adapter", "0.1.0")
class SmarterRpPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        super().__init__(context)
        self.config_model = SmarterRpConfig.from_mapping(config or {})
        data_dir = self._resolve_data_dir()
        self.storage = Storage(data_dir / "smarter_rp.db")
        self.storage.initialize()
        self.webui_token_path = data_dir / "webui_token.txt"
        self.webui_token = ""
        self.session_state = SessionStateService(
            self.storage,
            default_enabled=bool(self.config_model.behavior.get("default_enabled", True)),
        )
        self.bindings: TavernBindingService | None = None
        self.client: SillyTavernClient | None = None
        self.tavern_process: TavernProcessManager | None = None
        self.worker: TavernWorker | None = None
        self.webui_server: WebUiServer | None = None
        self.bridge_server: BridgeServer | None = None
        self._use_legacy_bridge = str(self.config_model.tavern.get("mode", "managed")) == "legacy_ws"

        if self._use_legacy_bridge:
            self.bridge_server = BridgeServer(
                host=str(self.config_model.bridge.get("host", "127.0.0.1")),
                port=int(self.config_model.bridge.get("port", 8008)),
                timeout_seconds=float(self.config_model.bridge.get("timeout_seconds", 120)),
            )
            return

        self.bindings = TavernBindingService(self.storage)
        self.client = SillyTavernClient(
            str(self.config_model.tavern.get("base_url", "http://127.0.0.1:8001")),
            timeout_seconds=float(self.config_model.tavern.get("request_timeout_seconds", 120)),
            auth=dict(self.config_model.tavern.get("auth", {})),
        )
        if self.config_model.tavern.get("auto_start", True) and str(self.config_model.tavern.get("mode", "managed")) == "managed":
            self.tavern_process = TavernProcessManager(
                install_dir=str(self.config_model.tavern.get("install_dir", "~/.local/share/astrbot-smarter-rp/SillyTavern")),
                base_url=str(self.config_model.tavern.get("base_url", "http://127.0.0.1:8001")),
                startup_timeout_seconds=float(self.config_model.tavern.get("startup_timeout_seconds", 60)),
                request_timeout_seconds=float(self.config_model.tavern.get("request_timeout_seconds", 120)),
                auth=dict(self.config_model.tavern.get("auth", {})),
            )
        self.worker = TavernWorker(self.client, self.bindings)
        if self.config_model.webui.get("enabled", True):
            self.webui_token = self._resolve_webui_token()
            self.webui_server = WebUiServer(
                client=self.client,
                bindings=self.bindings,
                config=self.config_model,
                webui_token=self.webui_token,
            )

    async def initialize(self):
        if self._use_legacy_bridge:
            if self.bridge_server is None:
                return
            try:
                await self.bridge_server.start()
            except BridgeUnavailableError:
                return
            return

        if self.tavern_process is not None:
            try:
                await self.tavern_process.start()
            except TavernProcessError:
                pass
        if self.webui_server is not None:
            await self.webui_server.start()

    async def terminate(self):
        if self.webui_server is not None:
            await self.webui_server.stop()
        if self.tavern_process is not None:
            await self.tavern_process.stop()
        if self.client is not None:
            await self.client.aclose()
        if self._use_legacy_bridge and self.bridge_server is not None:
            await self.bridge_server.stop()

    @filter.command("rp")
    async def rp(self, event, subcommand: str = "", argument: str = ""):
        subcommand = self._text_value(subcommand).lower()
        if subcommand == "off":
            self.session_state.disable(self._session_id(event))
            yield self._plain_result(event, "RP disabled for this conversation.")
            return
        if subcommand == "on":
            self.session_state.enable(self._session_id(event))
            yield self._plain_result(event, "RP enabled for this conversation.")
            return
        if subcommand == "webui":
            if self.webui_server is None:
                yield self._plain_result(event, "WebUI is unavailable in legacy mode or disabled.")
                return
            yield self._plain_result(event, self._webui_access_message())
            return
        if subcommand == "bind":
            character_id = self._text_value(argument)
            if not character_id:
                yield self._plain_result(event, "Usage: /rp bind <character_id>")
                return
            if self.bindings is None:
                yield self._plain_result(event, "RP account binding is unavailable in legacy mode.")
                return
            adapter, platform, account_id = self._account_binding_key(event)
            self.bindings.set_account_binding(adapter, platform, account_id, character_id)
            yield self._plain_result(event, f"RP account bound to SillyTavern character {character_id}.")
            return
        if subcommand == "binding":
            if self.bindings is None:
                yield self._plain_result(event, "Current RP binding: unavailable in legacy mode.")
                return
            adapter, platform, account_id = self._account_binding_key(event)
            binding = self.bindings.get_account_binding(adapter, platform, account_id)
            if binding is None:
                yield self._plain_result(event, "Current RP binding: none.")
                return
            yield self._plain_result(event, f"Current RP binding: character {binding.character_id}.")
            return
        if subcommand == "unbind":
            if self.bindings is None:
                yield self._plain_result(event, "RP account binding is unavailable in legacy mode.")
                return
            adapter, platform, account_id = self._account_binding_key(event)
            self.bindings.delete_account_binding(adapter, platform, account_id)
            yield self._plain_result(event, "RP account binding removed.")
            return
        yield self._plain_result(event, "Usage: /rp on|off|webui|bind <character_id>|binding|unbind")

    @_message_handler_decorator()
    async def on_message(self, event):
        text = self._extract_text(event)
        if not text or text.startswith("/"):
            return

        session_id = self._session_id(event)
        if not self.session_state.is_enabled(session_id):
            return

        payload = self._generate_payload(event)
        try:
            if self._use_legacy_bridge:
                if self.bridge_server is None:
                    raise BridgeUnavailableError("legacy bridge is not initialized")
                reply = await self.bridge_server.generate(payload)
            else:
                if self.worker is None:
                    raise MissingTavernBindingError("Tavern worker is not initialized")
                reply = await self.worker.generate(payload)
        except (BridgeUnavailableError, BridgeTimeoutError, BridgeJobError, TavernWorkerError, SillyTavernClientError, TavernProcessError):
            reply = str(self.config_model.behavior.get("fallback_message", "RP 后端暂时不可用。"))

        self._stop_event(event)
        yield self._plain_result(event, reply)

    def _resolve_webui_token(self) -> str:
        configured_token = str(self.config_model.webui.get("token", "") or "").strip()
        if configured_token:
            return configured_token

        if self.webui_token_path.exists():
            stored_token = self.webui_token_path.read_text(encoding="utf-8").strip()
            if stored_token:
                return stored_token

        generated_token = resolve_token("")
        self.webui_token_path.write_text(f"{generated_token}\n", encoding="utf-8")
        self.webui_token_path.chmod(0o600)
        return generated_token

    def _webui_access_message(self) -> str:
        host = str(self.config_model.webui.get("host", "127.0.0.1"))
        port = int(self.config_model.webui.get("port", 8010))
        url = f"http://{host}:{port}"
        if str(self.config_model.webui.get("token", "") or "").strip():
            token_hint = "configured in webui.token"
        else:
            token_hint = f"read {self.webui_token_path} on the server"
        return f"WebUI: {url}\nToken: {token_hint}."

    def _generate_payload(self, event) -> dict[str, dict[str, str]]:
        session_id = self._session_id(event)
        return {
            "adapter": {
                "name": self._text_value(self._safe_get(event, "adapter_name"), default="unknown"),
                "platform": self._text_value(self._safe_get(event, "platform"), default="unknown"),
                "accountId": self._text_value(self._safe_get(event, "self_id")),
            },
            "session": {
                "id": session_id,
                "displayName": self._text_value(self._safe_get(event, "session_name"), default=session_id),
            },
            "user": {
                "id": self._text_value(self._safe_get(event, "sender_id")),
                "name": self._text_value(self._safe_get(event, "sender_name")),
            },
            "message": {"text": self._extract_text(event)},
        }

    def _account_binding_key(self, event) -> tuple[str, str, str]:
        return (
            self._text_value(self._safe_get(event, "adapter_name"), default="unknown"),
            self._text_value(self._safe_get(event, "platform"), default="unknown"),
            self._text_value(self._safe_get(event, "self_id")),
        )

    def _plain_result(self, event, text: str):
        plain_result = self._safe_get(event, "plain_result")
        if callable(plain_result):
            return plain_result(text)
        return text

    def _stop_event(self, event) -> None:
        stop_event = self._safe_get(event, "stop_event")
        if callable(stop_event):
            stop_event()

    def _extract_text(self, event) -> str:
        get_message_str = self._safe_get(event, "get_message_str")
        if callable(get_message_str):
            return self._text_value(get_message_str())
        for name in ("message_str", "message", "raw_message"):
            text = self._text_value(self._safe_get(event, name))
            if text:
                return text
        return ""

    def _session_id(self, event) -> str:
        return self._text_value(self._safe_get(event, "unified_msg_origin"), default="unknown")

    def _resolve_data_dir(self) -> Path:
        for name in ("get_plugin_data_dir", "get_data_dir"):
            resolver = self._safe_get(self.context, name)
            if callable(resolver):
                try:
                    data_dir = Path(resolver())
                    data_dir.mkdir(parents=True, exist_ok=True)
                    return data_dir
                except Exception:
                    pass

        for name in ("plugin_data_dir", "plugin_data_path", "data_dir", "data_path"):
            value = self._safe_get(self.context, name)
            if value:
                try:
                    data_dir = Path(value)
                    data_dir.mkdir(parents=True, exist_ok=True)
                    return data_dir
                except Exception:
                    pass

        data_dir = Path(__file__).resolve().parent / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def _safe_get(self, obj, attr: str):
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(attr)
        try:
            return getattr(obj, attr, None)
        except Exception:
            return None

    def _text_value(self, value, default: str = "") -> str:
        if value is None:
            return default
        text = str(value).strip()
        return text or default
