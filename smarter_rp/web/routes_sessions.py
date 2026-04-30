from json import JSONDecodeError

from fastapi import APIRouter, Depends, HTTPException, Request

from smarter_rp.models import RpSession
from smarter_rp.services.session_service import SessionService


async def _read_patch_body(request: Request) -> dict:
    try:
        body = await request.json()
    except JSONDecodeError:
        raise HTTPException(status_code=422, detail="invalid JSON body") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="JSON body must be an object")
    return body


def _validate_list_of_strings(field: str, value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(status_code=422, detail=f"{field} must be a list of strings")
    return value


def _validate_nullable_string(field: str, value: object) -> str | None:
    if value is not None and not isinstance(value, str):
        raise HTTPException(status_code=422, detail=f"{field} must be a string or null")
    return value


def serialize_session(session: RpSession) -> dict:
    return {
        "id": session.id,
        "unified_msg_origin": session.unified_msg_origin,
        "account_profile_id": session.account_profile_id,
        "paused": session.paused,
        "active_character_id": session.active_character_id,
        "active_lorebook_ids": session.active_lorebook_ids,
        "summary": session.summary,
        "state": session.state,
        "recent_messages": session.recent_messages,
        "last_lore_hits": session.last_lore_hits,
        "last_memory_hits": session.last_memory_hits,
        "turn_count": session.turn_count,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def create_sessions_router(
    auth_dependency,
    session_service: SessionService | None,
) -> APIRouter:
    router = APIRouter(prefix="/api/sessions")

    @router.get("", dependencies=[Depends(auth_dependency)])
    async def list_sessions():
        if session_service is None:
            return []
        return [serialize_session(session) for session in session_service.list_sessions()]

    @router.patch("/{session_id}", dependencies=[Depends(auth_dependency)])
    async def update_session(session_id: str, request: Request):
        if session_service is None:
            raise HTTPException(status_code=404, detail="session not found")

        body = await _read_patch_body(request)
        updates = {}
        if "paused" in body:
            if not isinstance(body["paused"], bool):
                raise HTTPException(status_code=422, detail="paused must be a boolean")
            updates["paused"] = body["paused"]
        if "active_character_id" in body:
            updates["active_character_id"] = _validate_nullable_string(
                "active_character_id", body["active_character_id"]
            )
        if "active_lorebook_ids" in body:
            updates["active_lorebook_ids"] = _validate_list_of_strings(
                "active_lorebook_ids", body["active_lorebook_ids"]
            )

        try:
            session = session_service.update_session_controls(session_id, **updates)
        except KeyError:
            raise HTTPException(status_code=404, detail="session not found") from None
        return serialize_session(session)

    return router
