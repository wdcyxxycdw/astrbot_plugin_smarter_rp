from __future__ import annotations

import asyncio
import inspect
import json
import re
import traceback
from dataclasses import dataclass, field
from typing import Any, Protocol

from smarter_rp.models import Memory, MemoryJobResult, RpMessage, RpSession
from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.memory_service import MemoryService


@dataclass(slots=True)
class MemoryTriggerDecision:
    triggered: bool
    reason: str
    start_turn: int = 0
    end_turn: int = 0


@dataclass(slots=True)
class MemoryExtractionResult:
    ok: bool
    summary: str = ""
    state: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


@dataclass(slots=True)
class MemoryTriggerPolicy:
    auto_enabled: bool = True
    every_turns: int = 6
    history_chars_threshold: int = 12000

    def should_run(
        self,
        session: RpSession,
        messages: list[RpMessage],
        memories: list[Memory],
    ) -> MemoryTriggerDecision:
        if not self.auto_enabled:
            return MemoryTriggerDecision(False, "disabled")
        if not messages:
            return MemoryTriggerDecision(False, "no_messages")

        latest_end = max(0, int(session.memory_processed_turn))
        for memory in memories:
            if memory.turn_range is not None:
                latest_end = max(latest_end, int(memory.turn_range[1]))

        new_messages = [message for message in messages if message.turn_number > latest_end]
        if not new_messages:
            return MemoryTriggerDecision(False, "no_new_turns", latest_end, latest_end)

        start_turn = min(message.turn_number for message in new_messages)
        end_turn = max(message.turn_number for message in new_messages)
        new_turns = end_turn - latest_end
        if new_turns >= max(1, int(self.every_turns)):
            return MemoryTriggerDecision(True, "every_turns", start_turn, end_turn)

        history_chars = sum(len(message.content) for message in new_messages)
        if history_chars >= max(1, int(self.history_chars_threshold)):
            return MemoryTriggerDecision(True, "history_chars_threshold", start_turn, end_turn)

        return MemoryTriggerDecision(False, "not_due", start_turn, end_turn)


class MemoryProvider(Protocol):
    def complete(self, prompt: str) -> str:
        ...


class AstrBotMemoryProvider:
    def __init__(self, provider: object):
        self.provider = provider

    def complete(self, prompt: str) -> str:
        for method_name in ("complete", "text_chat", "chat", "ask"):
            method = getattr(self.provider, method_name, None)
            if method is None or not callable(method):
                continue
            result = method(prompt)
            if inspect.isawaitable(result):
                result = self._await(result)
            return self._text_result(result)
        raise RuntimeError("provider has no supported completion method")

    def _await(self, value: object) -> object:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(value)
        raise RuntimeError("async provider methods are unavailable inside memory worker thread")

    def _text_result(self, value: object) -> str:
        if isinstance(value, str):
            return value
        for name in ("completion_text", "result", "content", "text"):
            text = getattr(value, name, None)
            if isinstance(text, str):
                return text
        return str(value)


def parse_memory_extraction(raw: str) -> MemoryExtractionResult:
    text = _strip_json_fence(raw).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return MemoryExtractionResult(False, error=f"invalid_json: {exc.msg}")

    if not isinstance(payload, dict):
        return MemoryExtractionResult(False, error="expected JSON object")

    events_value = payload.get("events", [])
    if not isinstance(events_value, list):
        return MemoryExtractionResult(False, error="events must be a list")

    events: list[dict[str, Any]] = []
    for index, event in enumerate(events_value):
        if not isinstance(event, dict):
            return MemoryExtractionResult(False, error=f"events[{index}] must be an object")
        content = str(event.get("content", "")).strip()
        if not content:
            return MemoryExtractionResult(False, error=f"events[{index}].content is required")
        source_message_ids = event.get("source_message_ids", [])
        if not isinstance(source_message_ids, list):
            return MemoryExtractionResult(False, error=f"events[{index}].source_message_ids must be a list")
        turn_range = event.get("turn_range")
        if not (isinstance(turn_range, list) and len(turn_range) == 2):
            return MemoryExtractionResult(False, error=f"events[{index}].turn_range must be a list of two numbers")
        try:
            parsed_turn_range = (int(turn_range[0]), int(turn_range[1]))
        except (TypeError, ValueError):
            return MemoryExtractionResult(False, error=f"events[{index}].turn_range must be a list of two numbers")

        try:
            importance = int(event.get("importance", 5))
            confidence = float(event.get("confidence", 1.0))
        except (TypeError, ValueError):
            return MemoryExtractionResult(False, error=f"events[{index}].importance and confidence must be numeric")

        normalized = dict(event)
        normalized["content"] = content
        normalized["importance"] = importance
        normalized["confidence"] = confidence
        normalized["source_message_ids"] = [str(message_id) for message_id in source_message_ids]
        normalized["turn_range"] = parsed_turn_range
        events.append(normalized)

    state = payload.get("state", {})
    if not isinstance(state, dict):
        return MemoryExtractionResult(False, error="state must be an object")

    return MemoryExtractionResult(
        True,
        summary=str(payload.get("summary", "")).strip(),
        state=state,
        events=events,
    )


def _strip_json_fence(raw: str) -> str:
    text = str(raw or "").strip()
    match = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text


class MemoryExtractor:
    def __init__(
        self,
        memory: MemoryService,
        history: HistoryService,
        debug: DebugService,
        min_state_confidence: float = 0.65,
    ):
        self.memory = memory
        self.history = history
        self.debug = debug
        self.min_state_confidence = float(min_state_confidence)

    def merge_state(self, current: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current or {})
        for key, value in (extracted or {}).items():
            if isinstance(value, dict) and "value" in value and "confidence" in value:
                try:
                    confidence = float(value["confidence"])
                except (TypeError, ValueError):
                    continue
                if confidence >= self.min_state_confidence:
                    merged[key] = value["value"]
            else:
                merged[key] = value
        return merged

    def build_extraction_prompt(
        self,
        session: RpSession,
        messages: list[RpMessage],
        decision: MemoryTriggerDecision,
    ) -> str:
        message_lines = [
            f"[{message.turn_number}] {message.role} {message.speaker} ({message.id}): {message.content}"
            for message in messages
            if decision.start_turn <= message.turn_number <= decision.end_turn
        ]
        return "\n".join(
            [
                "Extract durable roleplay memory from the following messages.",
                "Return only JSON with keys: summary, state, events.",
                "Each event must include content, importance, confidence, source_message_ids, turn_range.",
                f"Existing summary: {session.summary}",
                f"Existing state JSON: {json.dumps(session.state, ensure_ascii=False, sort_keys=True)}",
                "Messages:",
                *message_lines,
            ]
        )

    def run_if_needed(
        self,
        session_id: str,
        policy: MemoryTriggerPolicy,
        provider: MemoryProvider | None,
    ) -> MemoryJobResult:
        session = self.memory.sessions.get_by_id(session_id)
        messages = self.history.list_messages(session_id)
        memories = self.memory.list_memories(session_id, limit=None)
        decision = policy.should_run(session, messages, memories)
        if not decision.triggered:
            return MemoryJobResult(session_id=session_id, triggered=False, reason=decision.reason)

        if provider is None:
            result = MemoryJobResult(
                session_id=session_id,
                triggered=True,
                reason="provider_unavailable",
                debug={"trigger_reason": decision.reason, "turn_range": [decision.start_turn, decision.end_turn]},
            )
            self._debug(session_id, "provider_unavailable", result.debug)
            return result

        prompt = self.build_extraction_prompt(session, messages, decision)
        try:
            raw = provider.complete(prompt)
        except Exception as exc:
            result = MemoryJobResult(
                session_id=session_id,
                triggered=True,
                reason="provider_failed",
                debug={
                    "trigger_reason": decision.reason,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
            self._debug(session_id, "provider_failed", result.debug)
            return result

        parsed = parse_memory_extraction(raw)
        if not parsed.ok:
            result = MemoryJobResult(
                session_id=session_id,
                triggered=True,
                reason="parse_failed",
                debug={"trigger_reason": decision.reason, "error": parsed.error, "raw": raw},
            )
            self._debug(session_id, "parse_failed", result.debug)
            return result

        summary_updated = False
        state_updated = False
        summary = session.summary
        if parsed.summary and parsed.summary != session.summary:
            summary = parsed.summary
            summary_updated = True

        merged_state = self.merge_state(session.state, parsed.state)
        if merged_state != session.state:
            state_updated = True

        memories_created = 0
        for event in parsed.events:
            before_ids = {memory.id for memory in self.memory.list_memories(session_id, limit=None)}
            memory = self.memory.create_event_memory(
                session_id,
                event["content"],
                importance=event.get("importance", 5),
                confidence=event.get("confidence", 1.0),
                source_message_ids=event["source_message_ids"],
                turn_range=event["turn_range"],
                metadata={"memory_extractor": True},
            )
            if memory.id not in before_ids:
                memories_created += 1

        loaded_session = self.memory.sessions.get_by_id(session_id)
        loaded_session.summary = summary
        loaded_session.state = merged_state
        loaded_session.memory_processed_turn = max(loaded_session.memory_processed_turn, decision.end_turn)
        self.memory.sessions.save_session_state(loaded_session)

        result = MemoryJobResult(
            session_id=session_id,
            triggered=True,
            reason="completed",
            summary_updated=summary_updated,
            state_updated=state_updated,
            memories_created=memories_created,
            debug={
                "trigger_reason": decision.reason,
                "turn_range": [decision.start_turn, decision.end_turn],
                "events": memories_created,
            },
        )
        self._debug(session_id, "completed", result.debug)
        return result

    def _debug(self, session_id: str, status: str, content: dict[str, Any]) -> None:
        payload = {"kind": "extraction", "status": status, **content}
        self.debug.save_snapshot(session_id, "memory", json.dumps(payload, ensure_ascii=False, sort_keys=True))
