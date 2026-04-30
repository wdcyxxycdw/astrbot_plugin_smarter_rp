from fastapi import APIRouter, Depends, HTTPException

from smarter_rp.models import RpMessage
from smarter_rp.services.history_service import HistoryService


def serialize_message(message: RpMessage) -> dict:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "speaker": message.speaker,
        "content": message.content,
        "visible": message.visible,
        "turn_number": message.turn_number,
        "metadata": message.metadata,
        "created_at": message.created_at,
    }


def create_history_router(
    auth_dependency,
    history_service: HistoryService | None,
) -> APIRouter:
    router = APIRouter(prefix="/api/sessions")

    @router.get("/{session_id}/history", dependencies=[Depends(auth_dependency)])
    async def list_history(session_id: str, limit: int = 50):
        if history_service is None:
            return {"messages": []}
        try:
            messages = history_service.list_messages(session_id, limit=limit)
        except KeyError:
            raise HTTPException(status_code=404, detail="session not found") from None
        return {"messages": [serialize_message(message) for message in messages]}

    @router.delete("/{session_id}/history", dependencies=[Depends(auth_dependency)])
    async def clear_history(session_id: str):
        if history_service is None:
            raise HTTPException(status_code=503, detail="history service unavailable")
        try:
            history_service.clear_history(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="session not found") from None
        return {"ok": True}

    @router.post("/{session_id}/history/undo", dependencies=[Depends(auth_dependency)])
    async def undo_history(session_id: str):
        if history_service is None:
            raise HTTPException(status_code=503, detail="history service unavailable")
        try:
            removed = history_service.undo_latest_turn(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="session not found") from None
        return {"removed": [serialize_message(message) for message in removed]}

    return router
