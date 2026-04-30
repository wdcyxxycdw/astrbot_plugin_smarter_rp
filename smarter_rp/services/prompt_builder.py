from __future__ import annotations

from typing import Any

from smarter_rp.models import AccountProfile, Character, MemoryHit, RpMessage, RpSession


class PromptBuilder:
    def __init__(self, max_prompt_chars: int = 12000):
        self.max_prompt_chars = max_prompt_chars

    def build(
        self,
        account_profile: AccountProfile | None,
        session: RpSession,
        character: Character,
        current_input: str,
        history_messages: list[RpMessage] | None = None,
        lorebook_buckets: dict[str, str] | None = None,
        memory_events: list[MemoryHit] | None = None,
    ) -> str:
        lorebook_buckets = lorebook_buckets or {}
        blocks = [
            self._block("Global RP System Rules", "Stay in character and continue the roleplay naturally."),
            self._block("Account/Profile Persona", self._account_persona(account_profile)),
        ]
        blocks.extend(self._lorebook_blocks(lorebook_buckets, "before_character"))
        blocks.append(self._block("Character", self._character_text(character)))
        blocks.extend(self._lorebook_blocks(lorebook_buckets, "after_character"))
        blocks.extend(self._memory_blocks(session, memory_events))
        blocks.extend(self._lorebook_blocks(lorebook_buckets, "before_history"))
        blocks.append(self._block("Recent RP History", self._history_text(history_messages)))
        blocks.extend(self._lorebook_blocks(lorebook_buckets, "in_history"))
        blocks.extend(self._lorebook_blocks(lorebook_buckets, "after_history"))
        blocks.extend(self._lorebook_blocks(lorebook_buckets, "post_history"))
        blocks.append(self._block("Current Input", current_input))
        return self._fit_to_budget("\n\n".join(blocks), current_input)

    def contexts_from_history(self, history_messages: list[RpMessage] | None) -> list[dict[str, str]]:
        contexts = []
        for message in history_messages or []:
            content = message.content.strip()
            if message.visible and message.role in ("user", "assistant") and content:
                contexts.append({"role": message.role, "content": content})
        return contexts

    def _block(self, title: str, content: str) -> str:
        return f"[{title}]\n{content or '(empty)'}"

    def _lorebook_blocks(self, lorebook_buckets: dict[str, str], position: str) -> list[str]:
        content = lorebook_buckets.get(position, "")
        if not content:
            return []
        return [self._block(f"Lorebook: {position}", content)]

    def _memory_blocks(self, session: RpSession, memory_events: list[MemoryHit] | None) -> list[str]:
        return [
            self._block("Session Summary", session.summary),
            self._block("Session State", self._format_mapping(session.state)),
            self._block("Relevant Event Memories", self._memory_events_text(memory_events)),
        ]

    def _memory_events_text(self, memory_events: list[MemoryHit] | None) -> str:
        lines = []
        for hit in memory_events or []:
            content = hit.content.strip()
            if content:
                lines.append(f"- {content}")
        return "\n".join(lines) or "No relevant event memories selected."

    def _history_text(self, history_messages: list[RpMessage] | None) -> str:
        lines = []
        for message in history_messages or []:
            content = message.content.strip()
            if message.visible and message.role in ("user", "assistant") and content:
                speaker = message.speaker.strip() or message.role
                lines.append(f"{speaker}: {content}")
        return "\n".join(lines) or "No recent RP history selected."

    def _account_persona(self, account_profile: AccountProfile | None) -> str:
        if account_profile is None:
            return ""
        persona = account_profile.prompt_overrides.get("persona", "")
        return str(persona) if persona is not None else ""

    def _character_text(self, character: Character) -> str:
        parts = [
            ("Name", character.name),
            ("System", character.system_prompt),
            ("Description", character.description),
            ("Personality", character.personality),
            ("Scenario", character.scenario),
        ]
        return "\n".join(f"{label}: {value}" for label, value in parts if value)

    def _format_mapping(self, value: dict[str, Any]) -> str:
        return "\n".join(f"{key}: {value[key]}" for key in sorted(value))

    def _fit_to_budget(self, prompt: str, current_input: str) -> str:
        if len(prompt) <= self.max_prompt_chars:
            return prompt
        if self.max_prompt_chars <= 0:
            return ""

        current_block = self._block("Current Input", current_input)
        if len(current_block) >= self.max_prompt_chars:
            return current_block[-self.max_prompt_chars :]

        remaining = self.max_prompt_chars - len(current_block) - 2
        if remaining <= 0:
            return current_block[-self.max_prompt_chars :]
        return prompt[:remaining].rstrip() + "\n\n" + current_block
