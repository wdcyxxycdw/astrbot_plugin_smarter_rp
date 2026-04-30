from __future__ import annotations

import random
import re
from dataclasses import asdict, is_dataclass
from typing import Any

from smarter_rp.services.lorebook_matcher import LorebookMatcher


_DICE_RE = re.compile(r"^\s*(?:(\d*)d)?(\d+)(?:\s*([+-])\s*(\d+))?\s*$", re.IGNORECASE)
_RP_TOOL_NAMES = {"sc_query_lorebook", "sc_search_memory", "sc_roll_dice"}
_FILTER_MODES = {"keep_all", "keep_subagents_only", "rp_tools_only", "whitelist"}


class ToolService:
    def __init__(
        self,
        lorebook_service: Any | None = None,
        lorebook_matcher: LorebookMatcher | None = None,
        memory_retriever: Any | None = None,
        whitelist: list[str] | None = None,
        preserve_mcp: bool = False,
        mode: str = "keep_subagents_only",
    ):
        self.lorebook_service = lorebook_service
        self.lorebook_matcher = lorebook_matcher
        self.memory_retriever = memory_retriever
        self.whitelist = list(whitelist or [])
        self.preserve_mcp = bool(preserve_mcp)
        self.mode = mode

    @property
    def rp_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "sc_query_lorebook",
                "description": "Query active Smarter RP lorebooks for relevant roleplay context.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "sc_search_memory",
                "description": "Search Smarter RP memory for relevant prior events.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "sc_roll_dice",
                "description": "Roll dice using expressions like d20, 2d6+3, or 2d6-1.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"},
                        "seed": {"type": ["string", "integer", "null"]},
                    },
                    "required": ["expression"],
                },
            },
        ]

    def filter_tools(
        self,
        existing_tools: list[Any] | None,
        mode: str | None = None,
        whitelist: list[str] | None = None,
        preserve_mcp: bool | None = None,
        include_rp_tools: bool = True,
    ) -> tuple[list[Any], dict[str, Any]]:
        selected_mode = mode or self.mode or "keep_subagents_only"
        if selected_mode not in _FILTER_MODES:
            selected_mode = "keep_subagents_only"
        whitelist_names = set(self.whitelist)
        if whitelist is not None:
            whitelist_names.update(whitelist)
        keep_mcp = self.preserve_mcp if preserve_mcp is None else bool(preserve_mcp)

        tools = list(existing_tools or [])
        original_names = [self.extract_tool_name(tool) for tool in tools]
        final_tools: list[Any] = []
        seen: set[str] = set()
        decisions: list[dict[str, Any]] = []

        for tool, name in zip(tools, original_names):
            keep, reason = self._should_keep_tool(name, selected_mode, whitelist_names, keep_mcp)
            duplicate = bool(name and name in seen)
            if keep and not duplicate:
                final_tools.append(tool)
                if name:
                    seen.add(name)
            decisions.append(
                {
                    "name": name,
                    "kept": keep and not duplicate,
                    "reason": "duplicate" if keep and duplicate else reason,
                }
            )

        rp_tool_names_to_add = self._rp_tool_names_to_add(selected_mode, whitelist_names) if include_rp_tools else set()
        for tool in self.rp_tools:
            name = tool["name"]
            if name not in rp_tool_names_to_add:
                continue
            duplicate = name in seen
            if not duplicate:
                final_tools.append(tool)
                seen.add(name)
            decisions.append({"name": name, "kept": not duplicate, "reason": "rp_tool" if not duplicate else "duplicate"})

        final_names = [self.extract_tool_name(tool) for tool in final_tools]
        debug = {
            "mode": selected_mode,
            "original_names": original_names,
            "final_names": final_names,
            "decisions": decisions,
        }
        return final_tools, debug

    def extract_tool_name(self, tool: Any) -> str:
        if isinstance(tool, dict):
            for key in ("name", "func_name", "tool_name"):
                value = tool.get(key)
                if value:
                    return str(value)
            function = tool.get("function")
            if isinstance(function, dict) and function.get("name"):
                return str(function["name"])
            return ""
        for attr in ("name", "func_name", "tool_name"):
            value = getattr(tool, attr, None)
            if value:
                return str(value)
        function = getattr(tool, "function", None)
        if isinstance(function, dict) and function.get("name"):
            return str(function["name"])
        value = getattr(function, "name", None)
        return str(value) if value else ""

    def roll_dice(self, expression: str, seed: int | str | None = None) -> dict[str, Any]:
        match = _DICE_RE.match(str(expression))
        if not match or "d" not in str(expression).lower():
            raise ValueError("Dice expression must look like d20, 2d6+3, or 2d6-1")
        count_text, sides_text, sign, modifier_text = match.groups()
        count = int(count_text) if count_text else 1
        sides = int(sides_text)
        modifier = int(modifier_text or 0)
        if sign == "-":
            modifier = -modifier
        if count < 1 or count > 100:
            raise ValueError("Dice count must be between 1 and 100")
        if sides < 2 or sides > 1000:
            raise ValueError("Dice sides must be between 2 and 1000")
        if modifier < -100000 or modifier > 100000:
            raise ValueError("Dice modifier is too large")

        rng = random.Random(seed) if seed is not None else random.Random()
        rolls = [rng.randint(1, sides) for _ in range(count)]
        return {
            "expression": expression,
            "count": count,
            "sides": sides,
            "modifier": modifier,
            "rolls": rolls,
            "total": sum(rolls) + modifier,
        }

    def query_lorebook(
        self,
        profile: Any,
        session: Any,
        character: Any,
        current_input: str,
        history_messages: list[Any],
    ) -> dict[str, Any]:
        if self.lorebook_service is None:
            return {"hits": [], "active_lorebook_ids": [], "available": False}
        active_ids = self._active_lorebook_ids(profile, session, character)
        entries = []
        for lorebook_id in active_ids:
            try:
                entries.extend(self.lorebook_service.list_entries(lorebook_id))
            except Exception:
                continue
        matcher = self.lorebook_matcher or LorebookMatcher()
        result = matcher.match(entries, current_input, history_messages or [], session, character)
        return {
            "hits": [
                {
                    "entry_id": hit.entry_id,
                    "title": hit.title,
                    "content": hit.content,
                    "reason": hit.reason,
                    "matched_key": hit.matched_key,
                    "source": hit.source,
                }
                for hit in result.hits
            ],
            "active_lorebook_ids": active_ids,
            "available": True,
        }

    def search_memory(
        self,
        session: Any,
        current_input: str,
        history_messages: list[Any],
        lore_hits: list[Any] | None = None,
    ) -> dict[str, Any]:
        if self.memory_retriever is None:
            return {"hits": [], "available": False}
        result = self.memory_retriever.retrieve(session, current_input, history_messages or [], lore_hits or [])
        return {
            "hits": [
                {
                    "memory_id": hit.memory_id,
                    "content": hit.content,
                    "score": hit.score,
                    "reason": hit.reason,
                    "importance": hit.importance,
                    "confidence": hit.confidence,
                }
                for hit in result.hits
            ],
            "available": True,
        }

    def _should_keep_tool(self, name: str, mode: str, whitelist_names: set[str], preserve_mcp: bool) -> tuple[bool, str]:
        if not name:
            return mode == "keep_all", "unnamed"
        if mode == "keep_all":
            return True, "keep_all"
        if mode == "rp_tools_only":
            return name in _RP_TOOL_NAMES, "rp_tool" if name in _RP_TOOL_NAMES else "filtered"
        if mode == "whitelist":
            keep = name in whitelist_names
            return keep, "whitelist" if keep else "filtered"
        if name.startswith("transfer_to_"):
            return True, "subagent"
        if name in whitelist_names:
            return True, "whitelist"
        if preserve_mcp and self._is_mcp_tool_name(name):
            return True, "mcp"
        return False, "filtered"

    def _active_lorebook_ids(self, profile: Any, session: Any, character: Any) -> list[str]:
        ids = list(getattr(session, "active_lorebook_ids", None) or [])
        if not ids:
            ids.extend(getattr(profile, "default_lorebook_ids", None) or [])
        ids.extend(getattr(character, "linked_lorebook_ids", None) or [])
        return self._dedupe_strings(ids)

    def _dedupe_strings(self, values: list[Any]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value is None:
                continue
            text = str(value)
            if text not in seen:
                seen.add(text)
                result.append(text)
        return result

    def _rp_tool_names_to_add(self, mode: str, whitelist_names: set[str]) -> set[str]:
        if mode in {"keep_all", "rp_tools_only"}:
            return set(_RP_TOOL_NAMES)
        if mode == "whitelist":
            return _RP_TOOL_NAMES.intersection(whitelist_names)
        return set()

    def _is_mcp_tool_name(self, name: str) -> bool:
        return name.startswith("mcp__") or name.startswith("mcp_")

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if is_dataclass(value):
            return asdict(value)
        return dict(getattr(value, "__dict__", {}))
