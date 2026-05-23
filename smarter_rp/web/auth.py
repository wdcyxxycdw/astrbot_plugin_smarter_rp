from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status


def resolve_token(configured_token: str | None) -> str:
    token = (configured_token or "").strip()
    if token:
        return token
    return secrets.token_urlsafe(32)


async def require_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_smarter_rp_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = getattr(request.app.state, "webui_token", "")
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    elif x_smarter_rp_token:
        provided = x_smarter_rp_token.strip()

    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
