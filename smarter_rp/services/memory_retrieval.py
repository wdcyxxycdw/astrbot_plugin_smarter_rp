from __future__ import annotations

import math
import re
from dataclasses import replace
from typing import Protocol

from smarter_rp.models import LorebookHit, Memory, MemoryHit, MemoryRetrievalResult, RpMessage, RpSession
from smarter_rp.services.memory_service import MemoryService

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-鿿]|[぀-ヿ]|[가-힯]")


class VectorAdapter(Protocol):
    available: bool

    def search(self, session_id: str, query: str, top_k: int) -> list[tuple[str, float]]:
        ...


class RerankAdapter(Protocol):
    available: bool

    def rerank(self, query: str, documents: list[MemoryHit], top_k: int) -> list[tuple[str, float]]:
        ...


class NullVectorAdapter:
    available = False

    def search(self, session_id: str, query: str, top_k: int) -> list[tuple[str, float]]:
        return []


class NullRerankAdapter:
    available = False

    def rerank(self, query: str, documents: list[MemoryHit], top_k: int) -> list[tuple[str, float]]:
        return []


class MemoryRetriever:
    def __init__(
        self,
        memory: MemoryService,
        vector_adapter: VectorAdapter | None = None,
        rerank_adapter: RerankAdapter | None = None,
        vector_top_k: int = 30,
        rerank_top_k: int = 10,
        min_importance: int = 2,
        max_hits: int = 10,
        max_chars: int = 4000,
        keyword_fallback_enabled: bool = True,
    ):
        self.memory = memory
        self.vector_adapter = vector_adapter or NullVectorAdapter()
        self.rerank_adapter = rerank_adapter or NullRerankAdapter()
        self.vector_top_k = max(1, int(vector_top_k))
        self.rerank_top_k = max(1, int(rerank_top_k))
        self.min_importance = max(1, int(min_importance))
        self.max_hits = max(0, int(max_hits))
        self.max_chars = max(0, int(max_chars))
        self.keyword_fallback_enabled = bool(keyword_fallback_enabled)

    def retrieve(
        self,
        session: RpSession,
        current_input: str,
        history_messages: list[RpMessage],
        lore_hits: list[LorebookHit],
    ) -> MemoryRetrievalResult:
        query = self._build_query(current_input, history_messages, lore_hits)
        memories = [memory for memory in self.memory.list_memories(session.id, limit=None) if memory.type == "event"]
        filtered: list[MemoryHit] = []
        candidates: list[tuple[Memory, float, str]] = []
        debug = {"query": query, "mode": "none", "candidate_count": 0}

        low_importance = [memory for memory in memories if memory.importance < self.min_importance]
        filtered.extend(self._hit(memory, 0.0, "min_importance", trimmed=False, filter_reason="min_importance") for memory in low_importance)
        eligible = [memory for memory in memories if memory.importance >= self.min_importance]

        vector_scores = self._vector_scores(session.id, query)
        by_id = {memory.id: memory for memory in eligible}
        if vector_scores:
            for memory_id, score in vector_scores:
                memory = by_id.get(memory_id)
                if memory is not None:
                    candidates.append((memory, float(score), "vector"))
            debug["mode"] = "vector"

        if self.keyword_fallback_enabled and (not vector_scores or len(candidates) < self.max_hits):
            existing_ids = {memory.id for memory, _score, _reason in candidates}
            query_tokens = self._tokens(query)
            keyword_candidates = []
            for memory in eligible:
                if memory.id in existing_ids:
                    continue
                score = self._keyword_score(memory, query_tokens)
                if score > 0:
                    keyword_candidates.append((memory, score, "keyword"))
            keyword_candidates.sort(key=lambda item: (item[1], item[0].importance, item[0].updated_at), reverse=True)
            candidates.extend(keyword_candidates)
            if vector_scores:
                debug["mode"] = "vector+keyword_fallback"
            else:
                debug["mode"] = "keyword"

        ranked = [self._hit(memory, score, reason) for memory, score, reason in candidates]
        ranked.sort(key=lambda hit: (hit.reason != "keyword", hit.score, hit.importance, self._updated_at(hit.memory_id, eligible)), reverse=True)
        ranked = self._rerank(query, ranked, debug)
        hits, budget_filtered = self._trim_to_budget(ranked)
        filtered.extend(budget_filtered)
        debug["candidate_count"] = len(candidates)
        debug["hit_count"] = len(hits)
        debug["filtered_count"] = len(filtered)
        return MemoryRetrievalResult(hits=hits, filtered=filtered, debug=debug)

    def _build_query(self, current_input: str, history_messages: list[RpMessage], lore_hits: list[LorebookHit]) -> str:
        parts = [current_input.strip()]
        visible_history = [
            message.content.strip()
            for message in history_messages
            if message.visible and message.role in ("user", "assistant") and message.content.strip()
        ]
        parts.extend(visible_history[-4:])
        parts.extend(hit.content.strip() for hit in lore_hits if hit.content.strip())
        return "\n".join(part for part in parts if part)

    def _vector_scores(self, session_id: str, query: str) -> list[tuple[str, float]]:
        if not getattr(self.vector_adapter, "available", False):
            return []
        try:
            return list(self.vector_adapter.search(session_id, query, self.vector_top_k))
        except Exception:
            return []

    def _rerank(self, query: str, ranked: list[MemoryHit], debug: dict[str, object]) -> list[MemoryHit]:
        if not ranked or not getattr(self.rerank_adapter, "available", False):
            debug["rerank"] = "none"
            return ranked
        top = ranked[: self.rerank_top_k]
        rest = ranked[self.rerank_top_k :]
        try:
            reranked_scores = self.rerank_adapter.rerank(query, top, self.rerank_top_k)
        except Exception:
            debug["rerank"] = "error"
            return ranked
        by_id = {hit.memory_id: hit for hit in top}
        reranked: list[MemoryHit] = []
        seen: set[str] = set()
        for memory_id, score in reranked_scores:
            hit = by_id.get(memory_id)
            if hit is not None and memory_id not in seen:
                reranked.append(replace(hit, score=float(score), reason="rerank"))
                seen.add(memory_id)
        reranked.extend(hit for hit in top if hit.memory_id not in seen)
        reranked.sort(key=lambda hit: hit.score, reverse=True)
        debug["rerank"] = "adapter" if reranked else "none"
        return reranked + rest

    def _trim_to_budget(self, ranked: list[MemoryHit]) -> tuple[list[MemoryHit], list[MemoryHit]]:
        hits: list[MemoryHit] = []
        filtered: list[MemoryHit] = []
        used = 0
        for hit in ranked:
            if len(hits) >= self.max_hits:
                filtered.append(replace(hit, trimmed=True, filter_reason="max_hits"))
                continue
            size = len(hit.content)
            if used + size <= self.max_chars:
                hits.append(hit)
                used += size
            else:
                filtered.append(replace(hit, trimmed=True, filter_reason="budget"))
        return hits, filtered

    def _keyword_score(self, memory: Memory, query_tokens: set[str]) -> float:
        if not query_tokens:
            return 0.0
        memory_tokens = self._tokens(memory.content)
        overlap = len(query_tokens & memory_tokens)
        if overlap <= 0:
            return 0.0
        return overlap + memory.importance * 0.01 + memory.confidence * 0.001 + self._recency_bonus(memory.updated_at)

    def _recency_bonus(self, updated_at: int) -> float:
        if updated_at <= 0:
            return 0.0
        return min(0.0009, math.log1p(updated_at) / 100000.0)

    def _tokens(self, text: str) -> set[str]:
        return {match.group(0).lower() for match in _TOKEN_RE.finditer(text)}

    def _hit(
        self,
        memory: Memory,
        score: float,
        reason: str,
        trimmed: bool = False,
        filter_reason: str = "",
    ) -> MemoryHit:
        return MemoryHit(
            memory_id=memory.id,
            content=memory.content,
            importance=memory.importance,
            confidence=memory.confidence,
            score=float(score),
            reason=reason,
            source_message_ids=memory.source_message_ids,
            turn_range=memory.turn_range,
            trimmed=trimmed,
            filter_reason=filter_reason,
        )

    def _updated_at(self, memory_id: str, memories: list[Memory]) -> int:
        for memory in memories:
            if memory.id == memory_id:
                return memory.updated_at
        return 0
