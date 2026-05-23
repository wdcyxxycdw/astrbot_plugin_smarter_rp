from __future__ import annotations

import json
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from smarter_rp.web.auth import require_token
from smarter_rp.web.upload import read_limited_upload

router = APIRouter(prefix="/api/worldbooks", dependencies=[Depends(require_token)])


@router.get("")
async def list_worldbooks(request: Request) -> dict[str, object]:
    return {"worldbooks": await request.app.state.tavern_client.list_worldbooks()}


@router.post("/import")
async def import_worldbook(request: Request, file: UploadFile = File(...)) -> dict[str, object]:
    content = await read_limited_upload(file)
    try:
        worldbook = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid worldbook JSON") from error
    result = await request.app.state.tavern_client.import_worldbook(file.filename or "worldbook.json", worldbook)
    return {"result": result}
