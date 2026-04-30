from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "rewrite": {
        "enabled_by_default": True,
        "priority": 100,
        "base_prompt_mode": "replace_all",
        "preserve_subagent_tools": True,
        "tool_mode": "keep_subagents_only",
    },
    "accounts": {
        "default_enabled": True,
    },
    "prompt": {
        "max_prompt_chars": 24000,
        "max_history_messages": 40,
        "max_lore_chars": 6000,
        "max_memory_chars": 4000,
        "max_example_dialogue_chars": 3000,
        "include_example_dialogues": True,
    },
    "lorebook": {
        "scan_recent_messages": 6,
        "max_hits": 12,
        "max_recursive_depth": 2,
        "regex_enabled": True,
        "vector_enabled": False,
    },
    "memory": {
        "auto_enabled": True,
        "every_turns": 6,
        "history_chars_threshold": 12000,
        "summary_provider_id": None,
        "memory_provider_id": None,
        "max_injected_events": 10,
        "min_importance": 2,
        "vector_top_k": 30,
        "rerank_top_k": 10,
        "keyword_fallback_enabled": True,
    },
    "history": {
        "max_history_messages": 40,
    },
    "webui": {
        "enabled": True,
        "host": "0.0.0.0",
        "port": 0,
        "token": None,
        "token_generated_at": None,
    },
    "storage": {
        "backend": "sqlite",
        "debug_snapshots_keep": 20,
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


@dataclass(slots=True)
class SmarterRpConfig:
    rewrite: dict[str, Any]
    accounts: dict[str, Any]
    prompt: dict[str, Any]
    lorebook: dict[str, Any]
    memory: dict[str, Any]
    history: dict[str, Any]
    webui: dict[str, Any]
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
        return cls(
            rewrite=merged["rewrite"],
            accounts=merged["accounts"],
            prompt=merged["prompt"],
            lorebook=merged["lorebook"],
            memory=merged["memory"],
            history=merged["history"],
            webui=merged["webui"],
            storage=merged["storage"],
        )

    def materialized_webui_config(self, token: str) -> dict[str, Any]:
        if not token.strip():
            raise ValueError("webui token must not be empty")

        webui = deepcopy(self.webui)
        webui["token"] = token
        return webui

    def to_dict(self) -> dict[str, Any]:
        return {
            "rewrite": deepcopy(self.rewrite),
            "accounts": deepcopy(self.accounts),
            "prompt": deepcopy(self.prompt),
            "lorebook": deepcopy(self.lorebook),
            "memory": deepcopy(self.memory),
            "history": deepcopy(self.history),
            "webui": deepcopy(self.webui),
            "storage": deepcopy(self.storage),
        }
