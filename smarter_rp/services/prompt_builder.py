from __future__ import annotations

from typing import Any

from smarter_rp.models import AccountProfile, Character, RpSession


class PromptBuilder:
    def __init__(self, max_prompt_chars: int = 12000):
        self.max_prompt_chars = max_prompt_chars

    def build(
        self,
        account_profile: AccountProfile | None,
        session: RpSession,
        character: Character,
        current_input: str,
    ) -> str:
        blocks = [
            self._block("Global RP System Rules", "Stay in character and continue the roleplay naturally."),
            self._block("Account/Profile Persona", self._account_persona(account_profile)),
            self._block("Character", self._character_text(character)),
            self._block("Lore", "No lore entries selected in Phase 1."),
            self._block("Memory", "No memory entries selected in Phase 1."),
            self._block("History", "No recent history selected in Phase 1."),
            self._block("Session Summary", session.summary),
            self._block("Session State", self._format_mapping(session.state)),
            self._block("Current Input", current_input),
        ]
        return self._fit_to_budget("\n\n".join(blocks), current_input)

    def _block(self, title: str, content: str) -> str:
        return f"[{title}]\n{content or '(empty)'}"

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
