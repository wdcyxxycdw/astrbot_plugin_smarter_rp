from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from smarter_rp.models import Memory, RpSession
from smarter_rp.services.memory_service import MemoryService
from smarter_rp.services.session_service import SessionService


def serialize_memory(memory: Memory) -> dict:
    return {
        "id": memory.id,
        "session_id": memory.session_id,
        "type": memory.type,
        "content": memory.content,
        "importance": memory.importance,
        "confidence": memory.confidence,
        "source_message_ids": memory.source_message_ids,
        "turn_range": list(memory.turn_range) if memory.turn_range is not None else None,
        "embedding_id": memory.embedding_id,
        "embedding_version": memory.embedding_version,
        "metadata": memory.metadata,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


def serialize_status(session: RpSession, memory_count: int) -> dict:
    return {
        "id": session.id,
        "unified_msg_origin": session.unified_msg_origin,
        "summary": session.summary,
        "state": session.state,
        "memory_count": memory_count,
        "last_memory_hits": session.last_memory_hits,
        "turn_count": session.turn_count,
        "updated_at": session.updated_at,
    }


def _service_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="memory service unavailable")


def _memory_count(memory_service: MemoryService, session_id: str) -> int:
    row = memory_service.storage.fetch_one(
        "SELECT COUNT(*) AS count FROM memories WHERE session_id = ?",
        (session_id,),
    )
    return int(row["count"] if row is not None else 0)


def create_memory_router(
    auth_dependency,
    memory_service: MemoryService | None,
    session_service: SessionService | None,
) -> APIRouter:
    router = APIRouter(prefix="/api/memory")

    @router.get("/sessions", dependencies=[Depends(auth_dependency)])
    async def list_memory_sessions():
        if memory_service is None or session_service is None:
            return []
        return [
            serialize_status(session, _memory_count(memory_service, session.id))
            for session in session_service.list_sessions()
        ]

    @router.get("/sessions/{session_id}", dependencies=[Depends(auth_dependency)])
    async def get_memory_session(
        session_id: str,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        if memory_service is None or session_service is None:
            raise HTTPException(status_code=404, detail="session not found")
        try:
            session = session_service.get_by_id(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="session not found") from None
        count = _memory_count(memory_service, session_id)
        rows = memory_service.storage.fetch_all(
            """
            SELECT * FROM memories
            WHERE session_id = ?
            ORDER BY created_at, id
            LIMIT ? OFFSET ?
            """,
            (session_id, limit, offset),
        )
        return {
            "status": serialize_status(session, count),
            "memories": [serialize_memory(memory_service._from_row(row)) for row in rows],
            "pagination": {"limit": limit, "offset": offset, "total": count},
        }

    @router.delete("/memories/{memory_id}", dependencies=[Depends(auth_dependency)])
    async def delete_memory(memory_id: str):
        if memory_service is None:
            raise _service_unavailable()
        if not memory_service.delete_memory(memory_id):
            raise HTTPException(status_code=404, detail="memory not found")
        return {"ok": True}

    @router.delete("/sessions/{session_id}", dependencies=[Depends(auth_dependency)])
    async def clear_session_memory(session_id: str):
        if memory_service is None:
            raise _service_unavailable()
        try:
            memory_service.clear_session_memory(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="session not found") from None
        return {"ok": True}

    return router
