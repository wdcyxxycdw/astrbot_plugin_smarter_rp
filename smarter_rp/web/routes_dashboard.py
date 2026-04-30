from fastapi import APIRouter, Depends


def create_dashboard_router(auth_dependency):
    router = APIRouter(prefix="/api/dashboard")

    @router.get("/status", dependencies=[Depends(auth_dependency)])
    async def status():
        return {
            "webui": "running",
            "rewrite_enabled_by_default": True,
            "accounts_default_enabled": True,
        }

    return router
