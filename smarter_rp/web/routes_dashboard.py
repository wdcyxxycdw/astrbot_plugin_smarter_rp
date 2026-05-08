import json

from fastapi import APIRouter, Depends, HTTPException, Request

from smarter_rp.services.prompt_builder import DEFAULT_GLOBAL_PROMPT, GLOBAL_PROMPT_SETTING_KEY
from smarter_rp.storage import Storage


def create_dashboard_router(auth_dependency, storage: Storage | None = None):
    router = APIRouter(prefix="/api/dashboard")

    @router.get("/status", dependencies=[Depends(auth_dependency)])
    async def status():
        return {
            "webui": "running",
            "rewrite_enabled_by_default": True,
            "accounts_default_enabled": True,
        }

    @router.get("/config", dependencies=[Depends(auth_dependency)])
    async def get_config():
        return {"global_prompt": _get_global_prompt(storage)}

    @router.patch("/config", dependencies=[Depends(auth_dependency)])
    async def update_config(request: Request):
        try:
            body = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        prompt = body.get("global_prompt")
        if not isinstance(prompt, str):
            raise HTTPException(status_code=400, detail="global_prompt must be a string")
        if storage is not None:
            storage.set_setting(GLOBAL_PROMPT_SETTING_KEY, prompt)
        return {"global_prompt": prompt}

    return router


def _get_global_prompt(storage: Storage | None) -> str:
    if storage is None:
        return DEFAULT_GLOBAL_PROMPT
    return storage.get_setting(GLOBAL_PROMPT_SETTING_KEY, DEFAULT_GLOBAL_PROMPT) or ""
