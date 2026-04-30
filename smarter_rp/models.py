from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class AccountProfile:
    id: str
    adapter_name: str
    platform: str
    account_id: str
    display_name: str = ""
    default_character_id: str | None = None
    default_lorebook_ids: list[str] = field(default_factory=list)
    default_enabled: bool = True
    prompt_overrides: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: int = 0
    updated_at: int = 0


@dataclass(slots=True)
class Character:
    id: str
    name: str = ""
    system_prompt: str = ""
    description: str = ""
    personality: str = ""
    scenario: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: int = 0
    updated_at: int = 0


@dataclass(slots=True)
class RpSession:
    id: str
    unified_msg_origin: str
    account_profile_id: str | None
    paused: bool = False
    active_character_id: str | None = None
    active_lorebook_ids: list[str] = field(default_factory=list)
    summary: str = ""
    state: dict[str, Any] = field(default_factory=dict)
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    last_lore_hits: list[dict[str, Any]] = field(default_factory=list)
    last_memory_hits: list[dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
    created_at: int = 0
    updated_at: int = 0


@dataclass(slots=True)
class DebugSnapshot:
    id: str
    session_id: str | None
    type: Literal["prompt", "raw_request", "memory", "lore", "tools", "system"]
    content: str
    created_at: int = 0
