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
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_message: str = ""
    alternate_greetings: list[str] = field(default_factory=list)
    example_dialogues: list[dict[str, Any]] = field(default_factory=list)
    speaking_style: str = ""
    system_prompt: str = ""
    post_history_prompt: str = ""
    author_note: str = ""
    linked_lorebook_ids: list[str] = field(default_factory=list)
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
class RpMessage:
    id: str
    session_id: str
    role: Literal["user", "assistant", "system"]
    speaker: str
    content: str
    visible: bool = True
    turn_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: int = 0


@dataclass(slots=True)
class Lorebook:
    id: str
    name: str
    description: str = ""
    scope: Literal["global", "session"] = "global"
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: int = 0
    updated_at: int = 0


@dataclass(slots=True)
class LorebookEntry:
    id: str
    lorebook_id: str
    title: str
    content: str
    enabled: bool = True
    constant: bool = False
    keys: list[str] = field(default_factory=list)
    secondary_keys: list[str] = field(default_factory=list)
    selective: bool = False
    regex: bool = False
    case_sensitive: bool = False
    position: Literal[
        "before_character",
        "after_character",
        "before_history",
        "in_history",
        "after_history",
        "post_history",
    ] = "before_history"
    depth: int = 0
    priority: int = 0
    order: int = 0
    probability: float = 1.0
    cooldown_turns: int = 0
    sticky_turns: int = 0
    recursive: bool = False
    group: str | None = None
    character_filter: list[str] = field(default_factory=list)
    max_injections_per_chat: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: int = 0
    updated_at: int = 0


@dataclass(slots=True)
class LorebookHit:
    entry_id: str
    lorebook_id: str
    title: str
    content: str
    position: str
    priority: int
    order: int
    reason: str
    matched_key: str = ""
    source: str = ""
    recursion_parent_id: str | None = None
    trimmed: bool = False
    filter_reason: str = ""


@dataclass(slots=True)
class DebugSnapshot:
    id: str
    session_id: str | None
    type: Literal["prompt", "raw_request", "memory", "lore", "tools", "system"]
    content: str
    created_at: int = 0
