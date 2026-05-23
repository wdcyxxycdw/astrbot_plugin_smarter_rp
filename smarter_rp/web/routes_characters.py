from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from smarter_rp.web.auth import require_token
from smarter_rp.web.upload import read_limited_upload

router = APIRouter(prefix="/api/characters", dependencies=[Depends(require_token)])


@router.get("")
async def list_characters(request: Request) -> dict[str, object]:
    return {"characters": await request.app.state.tavern_client.list_characters()}


@router.post("/import")
async def import_character(
    request: Request,
    file: UploadFile = File(...),
    file_type: str = Form("png", alias="fileType"),
    preserved_name: str = Form("", alias="preservedName"),
) -> dict[str, object]:
    content = await read_limited_upload(file)
    result = await request.app.state.tavern_client.import_character(
        file.filename or "character",
        content,
        file_type=file_type,
        preserved_name=preserved_name or None,
    )
    return {"result": result}
