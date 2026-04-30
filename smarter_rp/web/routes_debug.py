from fastapi import APIRouter, Depends, HTTPException, Query

from smarter_rp.models import DebugSnapshot
from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.session_service import SessionService


def serialize_snapshot(snapshot: DebugSnapshot) -> dict:
    return {
        "id": snapshot.id,
        "session_id": snapshot.session_id,
        "type": snapshot.type,
        "content": snapshot.content,
        "created_at": snapshot.created_at,
    }


def create_debug_router(
    auth_dependency,
    debug_service: DebugService | None,
) -> APIRouter:
    router = APIRouter(prefix="/api/debug")

    @router.get("/snapshots", dependencies=[Depends(auth_dependency)])
    async def list_snapshots(
        limit: int = Query(default=20),
        session_id: str | None = Query(default=None),
        snapshot_type: str | None = Query(default=None),
    ):
        if debug_service is None:
            return []
        return [
            serialize_snapshot(snapshot)
            for snapshot in debug_service.list_snapshots(
                limit=limit,
                session_id=session_id,
                snapshot_type=snapshot_type,
            )
        ]

    @router.get("/snapshots/{snapshot_id}", dependencies=[Depends(auth_dependency)])
    async def get_snapshot(snapshot_id: str):
        if debug_service is None:
            raise HTTPException(status_code=404, detail="snapshot not found")
        snapshot = debug_service.get_snapshot(snapshot_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="snapshot not found")
        return serialize_snapshot(snapshot)

    @router.get("/memory", dependencies=[Depends(auth_dependency)])
    async def list_memory_snapshots(
        session_id: str | None = Query(default=None),
        limit: int = Query(default=20),
    ):
        if debug_service is None:
            return []
        return [
            serialize_snapshot(snapshot)
            for snapshot in debug_service.list_snapshots(
                limit=limit,
                session_id=session_id,
                snapshot_type="memory",
            )
        ]

    @router.get("/tools", dependencies=[Depends(auth_dependency)])
    async def list_tool_snapshots(
        session_id: str | None = Query(default=None),
        limit: int = Query(default=20),
    ):
        if debug_service is None:
            return []
        return [
            serialize_snapshot(snapshot)
            for snapshot in debug_service.list_snapshots(
                limit=limit,
                session_id=session_id,
                snapshot_type="tools",
            )
        ]

    @router.get("/lore-hits", dependencies=[Depends(auth_dependency)])
    async def get_lore_hits(session_id: str | None = Query(default=None)):
        if session_id is None:
            raise HTTPException(status_code=400, detail="session_id is required")
        if debug_service is None:
            return {"hits": []}
        try:
            session = SessionService(debug_service.storage).get_by_id(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="session not found")
        return {"hits": session.last_lore_hits}

    return router
