from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from typing import Any

from smarter_rp.models import Character, LorebookEntry, LorebookHit, RpMessage, RpSession


_MAX_REGEX_KEY_CHARS = 500
_MAX_REGEX_TEXT_CHARS = 20000


@dataclass(slots=True)
class LorebookMatchResult:
    hits: list[LorebookHit] = field(default_factory=list)
    filtered: list[LorebookHit] = field(default_factory=list)
    buckets: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class _Candidate:
    entry: LorebookEntry
    hit: LorebookHit
    depth: int = 0


class LorebookMatcher:
    def __init__(self, max_hits: int = 12, max_chars: int = 6000, max_recursive_depth: int = 2):
        self.max_hits = max_hits
        self.max_chars = max_chars
        self.max_recursive_depth = max_recursive_depth

    def match(
        self,
        entries: list[LorebookEntry],
        current_input: str,
        history_messages: list[RpMessage] | None,
        session: RpSession,
        character: Character,
    ) -> LorebookMatchResult:
        filtered: list[LorebookHit] = []
        hit_ids: set[str] = set()
        used_groups: set[str] = set()
        candidates = self._scan_entries(
            entries,
            self._searchable_text(current_input, history_messages, session),
            session,
            character,
            filtered,
            hit_ids,
            recursion_parent_id=None,
            depth=0,
        )
        selected = self._select_candidates(candidates, filtered, hit_ids, used_groups, selected_count=0)

        depth = 1
        while depth <= self.max_recursive_depth:
            parent_hits = [candidate for candidate in selected if candidate.depth == depth - 1]
            if not parent_hits:
                break
            new_candidates: list[_Candidate] = []
            for parent in parent_hits:
                new_candidates.extend(
                    self._scan_entries(
                        entries,
                        parent.entry.content,
                        session,
                        character,
                        filtered,
                        hit_ids,
                        recursion_parent_id=parent.entry.id,
                        depth=depth,
                    )
                )
            new_selected = self._select_candidates(new_candidates, filtered, hit_ids, used_groups, selected_count=len(selected))
            if not new_selected:
                break
            selected.extend(new_selected)
            depth += 1

        final_hits = self._apply_budget([candidate.hit for candidate in selected], filtered)
        final_hits = self._remove_orphan_recursive_hits(final_hits, filtered)
        final_hit_ids = {hit.entry_id for hit in final_hits}
        filtered = [hit for hit in filtered if hit.entry_id not in final_hit_ids]
        return LorebookMatchResult(hits=final_hits, filtered=filtered, buckets=self._buckets(final_hits))

    def _scan_entries(
        self,
        entries: list[LorebookEntry],
        searchable_text: str,
        session: RpSession,
        character: Character,
        filtered: list[LorebookHit],
        hit_ids: set[str],
        recursion_parent_id: str | None,
        depth: int,
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        for entry in entries:
            if entry.id in hit_ids:
                continue
            if recursion_parent_id is not None and not entry.recursive:
                continue
            filter_reason = self._pre_filter_reason(entry, session, character)
            if filter_reason:
                filtered.append(self._hit(entry, reason="filtered", filter_reason=filter_reason, recursion_parent_id=recursion_parent_id))
                continue
            match = self._match_entry(entry, searchable_text)
            if match["filter_reason"] and match["filter_reason"] != "no_match":
                filtered.append(
                    self._hit(
                        entry,
                        reason="filtered",
                        matched_key=match["matched_key"],
                        source=match["source"],
                        filter_reason=match["filter_reason"],
                        recursion_parent_id=recursion_parent_id,
                    )
                )
                continue
            if not match["matched"]:
                if self._is_sticky_hit(entry, session):
                    candidates.append(
                        _Candidate(
                            entry=entry,
                            hit=self._hit(entry, reason="sticky", source="last_lore_hits", recursion_parent_id=recursion_parent_id),
                            depth=depth,
                        )
                    )
                else:
                    filtered.append(
                        self._hit(
                            entry,
                            reason="filtered",
                            matched_key=match["matched_key"],
                            source=match["source"],
                            filter_reason=match["filter_reason"],
                            recursion_parent_id=recursion_parent_id,
                        )
                    )
                continue
            candidates.append(
                _Candidate(
                    entry=entry,
                    hit=self._hit(
                        entry,
                        reason=match["reason"],
                        matched_key=match["matched_key"],
                        source=match["source"],
                        recursion_parent_id=recursion_parent_id,
                    ),
                    depth=depth,
                )
            )
        return sorted(candidates, key=lambda candidate: self._sort_key(candidate.entry))

    def _select_candidates(
        self,
        candidates: list[_Candidate],
        filtered: list[LorebookHit],
        hit_ids: set[str],
        used_groups: set[str],
        selected_count: int,
    ) -> list[_Candidate]:
        selected: list[_Candidate] = []
        for candidate in sorted(candidates, key=lambda item: self._sort_key(item.entry)):
            entry = candidate.entry
            if entry.id in hit_ids:
                continue
            if entry.group and entry.group in used_groups:
                filtered.append(self._copy_filtered(candidate.hit, "group_already_selected"))
                hit_ids.add(entry.id)
                continue
            if selected_count + len(selected) >= self.max_hits:
                filtered.append(self._copy_filtered(candidate.hit, "max_hits"))
                hit_ids.add(entry.id)
                continue
            hit_ids.add(entry.id)
            if entry.group:
                used_groups.add(entry.group)
            selected.append(candidate)
        return selected

    def _pre_filter_reason(self, entry: LorebookEntry, session: RpSession, character: Character) -> str:
        if not entry.enabled:
            return "disabled"
        if not self._character_allowed(entry, character):
            return "character_filter"
        if not self._probability_allowed(entry, session):
            return "probability"
        if self._in_cooldown(entry, session):
            return "cooldown"
        if self._hit_limit_reached(entry, session):
            return "max_injections_per_chat"
        return ""

    def _match_entry(self, entry: LorebookEntry, searchable_text: str) -> dict[str, Any]:
        if entry.constant:
            return {"matched": True, "reason": "constant", "matched_key": "", "source": "constant", "filter_reason": ""}
        if entry.regex and len(searchable_text) > _MAX_REGEX_TEXT_CHARS:
            return {"matched": False, "reason": "", "matched_key": "", "source": "", "filter_reason": "regex_too_large"}


        primary = self._first_matching_key(entry.keys, searchable_text, entry.regex, entry.case_sensitive)
        if primary["too_large"]:
            return {"matched": False, "reason": "", "matched_key": primary["key"], "source": "", "filter_reason": "regex_too_large"}
        if primary["invalid_regex"]:
            return {"matched": False, "reason": "", "matched_key": primary["key"], "source": "", "filter_reason": "invalid_regex"}

        if entry.selective:
            if not primary["matched"]:
                return {"matched": False, "reason": "", "matched_key": "", "source": "", "filter_reason": "selective_primary_missing"}
            secondary = self._first_matching_key(entry.secondary_keys, searchable_text, entry.regex, entry.case_sensitive)
            if secondary["too_large"]:
                return {"matched": False, "reason": "", "matched_key": secondary["key"], "source": "", "filter_reason": "regex_too_large"}
            if secondary["invalid_regex"]:
                return {"matched": False, "reason": "", "matched_key": secondary["key"], "source": "", "filter_reason": "invalid_regex"}
            if not secondary["matched"]:
                return {"matched": False, "reason": "", "matched_key": primary["key"], "source": "searchable_text", "filter_reason": "selective_secondary_missing"}
            return {"matched": True, "reason": "selective", "matched_key": primary["key"], "source": "searchable_text", "filter_reason": ""}

        if primary["matched"]:
            return {"matched": True, "reason": "regex" if entry.regex else "keyword", "matched_key": primary["key"], "source": "searchable_text", "filter_reason": ""}
        return {"matched": False, "reason": "", "matched_key": "", "source": "", "filter_reason": "no_match"}

    def _first_matching_key(self, keys: list[str], text: str, use_regex: bool, case_sensitive: bool) -> dict[str, Any]:
        haystack = text if case_sensitive else text.lower()
        for key in keys:
            if use_regex:
                if len(key) > _MAX_REGEX_KEY_CHARS:
                    return {"matched": False, "key": key, "invalid_regex": False, "too_large": True}
                flags = 0 if case_sensitive else re.IGNORECASE
                try:
                    if re.search(key, text, flags):
                        return {"matched": True, "key": key, "invalid_regex": False, "too_large": False}
                except re.error:
                    return {"matched": False, "key": key, "invalid_regex": True, "too_large": False}
            elif (key if case_sensitive else key.lower()) in haystack:
                return {"matched": True, "key": key, "invalid_regex": False, "too_large": False}
        return {"matched": False, "key": "", "invalid_regex": False, "too_large": False}

    def _searchable_text(
        self,
        current_input: str,
        history_messages: list[RpMessage] | None,
        session: RpSession,
    ) -> str:
        parts = [current_input]
        for message in history_messages or []:
            if message.visible and message.content:
                parts.append(message.content)
        if session.summary:
            parts.append(session.summary)
        for key in sorted(session.state):
            parts.append(f"{key}: {session.state[key]}")
        return "\n".join(str(part) for part in parts if part is not None)

    def _character_allowed(self, entry: LorebookEntry, character: Character) -> bool:
        if not entry.character_filter:
            return True
        allowed = {value.lower() for value in entry.character_filter}
        names = {character.id.lower(), character.name.lower()}
        return bool(allowed & names)

    def _probability_allowed(self, entry: LorebookEntry, session: RpSession) -> bool:
        probability = float(entry.probability)
        if probability <= 0:
            return False
        if probability >= 1:
            return True
        seed_text = f"{entry.id}:{session.id}:{session.turn_count}"
        seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16], 16)
        return random.Random(seed).random() < probability

    def _in_cooldown(self, entry: LorebookEntry, session: RpSession) -> bool:
        if entry.cooldown_turns <= 0:
            return False
        last_hit_turn = entry.metadata.get("last_hit_turn")
        if last_hit_turn is None:
            return False
        try:
            return session.turn_count - int(last_hit_turn) < entry.cooldown_turns
        except (TypeError, ValueError):
            return False

    def _hit_limit_reached(self, entry: LorebookEntry, session: RpSession) -> bool:
        if entry.max_injections_per_chat is None:
            return False
        count = 0
        for hit in session.last_lore_hits:
            if isinstance(hit, dict) and hit.get("entry_id") == entry.id:
                count += 1
        return count >= entry.max_injections_per_chat

    def _is_sticky_hit(self, entry: LorebookEntry, session: RpSession) -> bool:
        if entry.sticky_turns <= 0:
            return False
        for hit in session.last_lore_hits:
            if not isinstance(hit, dict) or hit.get("entry_id") != entry.id:
                continue
            turn = hit.get("turn_number", hit.get("turn"))
            try:
                if 0 <= session.turn_count - int(turn) <= entry.sticky_turns:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def _apply_budget(self, hits: list[LorebookHit], filtered: list[LorebookHit]) -> list[LorebookHit]:
        max_chars = max(self.max_chars, 0)
        selected: list[LorebookHit] = []
        used = 0
        for hit in hits:
            addition = len(hit.content) + (2 if selected else 0)
            if used + addition > max_chars:
                filtered.append(self._copy_filtered(hit, "budget", trimmed=True))
                continue
            selected.append(hit)
            used += addition
        return selected

    def _remove_orphan_recursive_hits(self, hits: list[LorebookHit], filtered: list[LorebookHit]) -> list[LorebookHit]:
        kept = list(hits)
        while True:
            selected_ids = {hit.entry_id for hit in kept}
            next_kept: list[LorebookHit] = []
            removed = False
            for hit in kept:
                if hit.recursion_parent_id is not None and hit.recursion_parent_id not in selected_ids:
                    filtered.append(self._copy_filtered(hit, "orphan_recursive"))
                    removed = True
                    continue
                next_kept.append(hit)
            kept = next_kept
            if not removed:
                return kept

    def _buckets(self, hits: list[LorebookHit]) -> dict[str, str]:
        grouped: dict[str, list[str]] = {}
        for hit in hits:
            grouped.setdefault(hit.position, []).append(hit.content)
        return {position: "\n\n".join(contents) for position, contents in grouped.items()}

    def _hit(
        self,
        entry: LorebookEntry,
        reason: str,
        matched_key: str = "",
        source: str = "",
        recursion_parent_id: str | None = None,
        trimmed: bool = False,
        filter_reason: str = "",
    ) -> LorebookHit:
        return LorebookHit(
            entry_id=entry.id,
            lorebook_id=entry.lorebook_id,
            title=entry.title,
            content=entry.content,
            position=entry.position,
            priority=entry.priority,
            order=entry.order,
            reason=reason,
            matched_key=matched_key,
            source=source,
            recursion_parent_id=recursion_parent_id,
            trimmed=trimmed,
            filter_reason=filter_reason,
        )

    def _copy_filtered(self, hit: LorebookHit, filter_reason: str, trimmed: bool = False) -> LorebookHit:
        return LorebookHit(
            entry_id=hit.entry_id,
            lorebook_id=hit.lorebook_id,
            title=hit.title,
            content=hit.content,
            position=hit.position,
            priority=hit.priority,
            order=hit.order,
            reason="filtered",
            matched_key=hit.matched_key,
            source=hit.source,
            recursion_parent_id=hit.recursion_parent_id,
            trimmed=trimmed,
            filter_reason=filter_reason,
        )

    def _sort_key(self, entry: LorebookEntry) -> tuple[int, int, str, str]:
        return (-entry.priority, entry.order, entry.title, entry.id)
