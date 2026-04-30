from typing import Optional

from fastapi import Header, HTTPException, Query


def verify_token_factory(expected_token: str):
    if not expected_token or not expected_token.strip():
        raise ValueError("webui token must not be empty")

    async def verify_token(
        token: Optional[str] = Query(default=None),
        authorization: Optional[str] = Header(default=None),
    ) -> None:
        provided_token = token
        if authorization and authorization.startswith("Bearer "):
            provided_token = authorization.removeprefix("Bearer ")

        if provided_token != expected_token:
            raise HTTPException(status_code=401, detail="invalid webui token")

    return verify_token
