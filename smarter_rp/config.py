from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


DEFAULT_CONFIG: dict[str, Any] = {
    "bridge": {
        "mode": "legacy_ws",
        "host": "127.0.0.1",
        "port": 8008,
        "timeout_seconds": 120,
    },
    "tavern": {
        "mode": "managed",
        "host": "127.0.0.1",
        "port": 8001,
        "base_url": "http://127.0.0.1:8001",
        "install_dir": "~/.local/share/astrbot-smarter-rp/SillyTavern",
        "auto_start": True,
        "startup_timeout_seconds": 60,
        "request_timeout_seconds": 120,
        "auth": {"enabled": False, "username": "", "password": "", "token": ""},
    },
    "webui": {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8010,
        "token": "",
    },
    "behavior": {
        "default_enabled": True,
        "fallback_message": "RP 后端暂时不可用。",
    },
    "storage": {
        "backend": "sqlite",
    },
}


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_local_host(host: Any) -> bool:
    return str(host).strip() in LOCAL_HOSTS


def ensure_local_host(host: Any, message: str) -> None:
    if not is_local_host(host):
        raise ValueError(message)


@dataclass(slots=True)
class SmarterRpConfig:
    bridge: dict[str, Any]
    tavern: dict[str, Any]
    webui: dict[str, Any]
    behavior: dict[str, Any]
    storage: dict[str, Any]

    @classmethod
    def default(cls) -> "SmarterRpConfig":
        return cls.from_mapping({})

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "SmarterRpConfig":
        overrides = data or {}
        for key, value in overrides.items():
            if key not in DEFAULT_CONFIG:
                raise ValueError(f"unknown config section: {key}")
            if not isinstance(value, Mapping):
                raise ValueError(f"config section {key} must be a mapping")

        merged = _deep_merge(DEFAULT_CONFIG, overrides)
        ensure_local_host(merged["bridge"].get("host", ""), "bridge.host must remain local because authentication is disabled")
        ensure_local_host(merged["tavern"].get("host", ""), "tavern.host must remain local")
        ensure_local_host(merged["webui"].get("host", ""), "webui.host must remain local")

        base_url_host = urlparse(str(merged["tavern"].get("base_url", ""))).hostname
        ensure_local_host(base_url_host or "", "tavern.base_url must remain local")

        return cls(
            bridge=merged["bridge"],
            tavern=merged["tavern"],
            webui=merged["webui"],
            behavior=merged["behavior"],
            storage=merged["storage"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bridge": deepcopy(self.bridge),
            "tavern": deepcopy(self.tavern),
            "webui": deepcopy(self.webui),
            "behavior": deepcopy(self.behavior),
            "storage": deepcopy(self.storage),
        }
