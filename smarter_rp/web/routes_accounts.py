from json import JSONDecodeError

from fastapi import APIRouter, Depends, HTTPException, Request

from smarter_rp.models import AccountProfile
from smarter_rp.services.account_service import AccountService


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


def serialize_account(profile: AccountProfile) -> dict:
    return {
        "id": profile.id,
        "adapter_name": profile.adapter_name,
        "platform": profile.platform,
        "account_id": profile.account_id,
        "display_name": profile.display_name,
        "default_enabled": profile.default_enabled,
        "default_character_id": profile.default_character_id,
        "default_lorebook_ids": profile.default_lorebook_ids,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def create_accounts_router(
    auth_dependency,
    account_service: AccountService | None,
) -> APIRouter:
    router = APIRouter(prefix="/api/accounts")

    @router.get("", dependencies=[Depends(auth_dependency)])
    async def list_accounts():
        if account_service is None:
            return []
        return [serialize_account(profile) for profile in account_service.list_profiles()]

    @router.patch("/{profile_id}", dependencies=[Depends(auth_dependency)])
    async def update_account(profile_id: str, request: Request):
        if account_service is None:
            raise HTTPException(status_code=404, detail="account not found")

        body = await _read_patch_body(request)
        updates = {}
        if "default_enabled" in body:
            if not isinstance(body["default_enabled"], bool):
                raise HTTPException(status_code=422, detail="default_enabled must be a boolean")
            updates["default_enabled"] = body["default_enabled"]
        if "default_character_id" in body:
            updates["default_character_id"] = _validate_nullable_string(
                "default_character_id", body["default_character_id"]
            )
        if "default_lorebook_ids" in body:
            updates["default_lorebook_ids"] = _validate_list_of_strings(
                "default_lorebook_ids", body["default_lorebook_ids"]
            )
        if "display_name" in body:
            if not isinstance(body["display_name"], str):
                raise HTTPException(status_code=422, detail="display_name must be a string")
            updates["display_name"] = body["display_name"]

        try:
            profile = account_service.update_profile(profile_id, **updates)
        except KeyError:
            raise HTTPException(status_code=404, detail="account not found") from None
        return serialize_account(profile)

    return router
