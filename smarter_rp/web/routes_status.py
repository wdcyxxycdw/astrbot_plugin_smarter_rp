from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from smarter_rp.web.auth import require_token

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


@router.get("/status")
async def get_status(request: Request) -> dict[str, object]:
    config = request.app.state.config
    client = request.app.state.tavern_client
    online = await client.health()
    return {
        "webui": {
            "enabled": bool(config.webui.get("enabled", False)),
            "host": str(config.webui.get("host", "")),
            "port": int(config.webui.get("port", 0) or 0),
        },
        "tavern": {
            "online": online,
            "baseUrl": str(config.tavern.get("base_url", "")),
            "installDir": str(config.tavern.get("install_dir", "") or ""),
            "version": str(config.tavern.get("version", "") or ""),
        },
    }
