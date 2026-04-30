from __future__ import annotations

from dataclasses import asdict
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from smarter_rp.models import Character, Lorebook, LorebookEntry, LorebookHit, RpSession
from smarter_rp.services.account_service import AccountService
from smarter_rp.services.lorebook_matcher import LorebookMatcher
from smarter_rp.services.lorebook_service import LorebookService
from smarter_rp.services.session_service import SessionService
from smarter_rp.web.routes_accounts import serialize_account
from smarter_rp.web.routes_sessions import serialize_session


LOREBOOK_STRING_FIELDS = {"name", "description", "scope"}
LOREBOOK_NULLABLE_STRING_FIELDS = {"session_id"}
ENTRY_STRING_FIELDS = {"title", "content", "position"}
ENTRY_BOOL_FIELDS = {
    "enabled",
    "constant",
    "selective",
    "regex",
    "case_sensitive",
    "recursive",
}
ENTRY_INT_FIELDS = {"depth", "priority", "order", "cooldown_turns", "sticky_turns"}
ENTRY_FLOAT_FIELDS = {"probability"}
ENTRY_LIST_STRING_FIELDS = {"keys", "secondary_keys", "character_filter"}
ENTRY_NULLABLE_STRING_FIELDS = {"group"}
ENTRY_NULLABLE_INT_FIELDS = {"max_injections_per_chat"}


async def _read_json_object(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON body") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")
    return body


def _service_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="lorebook service unavailable")


def _validate_lorebook_body(body: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, value in body.items():
        if field in LOREBOOK_STRING_FIELDS:
            if not isinstance(value, str):
                raise HTTPException(status_code=400, detail=f"{field} must be a string")
            values[field] = value
        elif field in LOREBOOK_NULLABLE_STRING_FIELDS:
            values[field] = _validate_nullable_string(field, value)
        elif field == "metadata":
            values[field] = _validate_dict(field, value)
    return values


def _validate_entry_body(body: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, value in body.items():
        if field in ENTRY_STRING_FIELDS:
            if not isinstance(value, str):
                raise HTTPException(status_code=400, detail=f"{field} must be a string")
            values[field] = value
        elif field in ENTRY_BOOL_FIELDS:
            if not isinstance(value, bool):
                raise HTTPException(status_code=400, detail=f"{field} must be a boolean")
            values[field] = value
        elif field in ENTRY_INT_FIELDS:
            values[field] = _validate_int(field, value)
        elif field in ENTRY_FLOAT_FIELDS:
            values[field] = _validate_float(field, value)
        elif field in ENTRY_LIST_STRING_FIELDS:
            values[field] = _validate_list_of_strings(field, value)
        elif field in ENTRY_NULLABLE_STRING_FIELDS:
            values[field] = _validate_nullable_string(field, value)
        elif field in ENTRY_NULLABLE_INT_FIELDS:
            values[field] = _validate_nullable_int(field, value)
        elif field == "metadata":
            values[field] = _validate_dict(field, value)
    return values


def _validate_assignment_body(body: dict[str, Any]) -> list[str]:
    if "lorebook_ids" not in body:
        raise HTTPException(status_code=400, detail="lorebook_ids is required")
    return _validate_list_of_strings("lorebook_ids", body["lorebook_ids"])


def _validate_hit_test_body(body: dict[str, Any]) -> dict[str, Any]:
    if "lorebook_ids" not in body:
        raise HTTPException(status_code=400, detail="lorebook_ids is required")
    if "input" not in body:
        raise HTTPException(status_code=400, detail="input is required")
    lorebook_ids = _validate_list_of_strings("lorebook_ids", body["lorebook_ids"])
    current_input = body["input"]
    if not isinstance(current_input, str):
        raise HTTPException(status_code=400, detail="input must be a string")
    session_id = body.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        raise HTTPException(status_code=400, detail="session_id must be a string or null")
    return {"lorebook_ids": lorebook_ids, "input": current_input, "session_id": session_id}


def _ensure_lorebooks_exist(lorebook_service: LorebookService, lorebook_ids: list[str]) -> None:
    for lorebook_id in lorebook_ids:
        if lorebook_service.get_lorebook(lorebook_id) is None:
            raise HTTPException(status_code=404, detail="lorebook not found")


def _validate_list_of_strings(field: str, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(status_code=400, detail=f"{field} must be a list of strings")
    return value


def _validate_nullable_string(field: str, value: Any) -> str | None:
    if value is not None and not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field} must be a string or null")
    return value


def _validate_int(field: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise HTTPException(status_code=400, detail=f"{field} must be an integer")
    return value


def _validate_nullable_int(field: str, value: Any) -> int | None:
    if value is None:
        return None
    return _validate_int(field, value)


def _validate_float(field: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise HTTPException(status_code=400, detail=f"{field} must be a number")
    return float(value)


def _validate_dict(field: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail=f"{field} must be a dict")
    return value


def serialize_lorebook(lorebook: Lorebook) -> dict[str, Any]:
    return asdict(lorebook)


def serialize_entry(entry: LorebookEntry) -> dict[str, Any]:
    return asdict(entry)


def serialize_hit(hit: LorebookHit) -> dict[str, Any]:
    return asdict(hit)


def _temporary_session(session_id: str | None = None) -> RpSession:
    return RpSession(
        id=session_id or "temporary_hit_test_session",
        unified_msg_origin="temporary:hit-test",
        account_profile_id=None,
    )


def _load_hit_test_session(session_service: SessionService | None, session_id: str | None) -> RpSession:
    if session_id is None or session_service is None:
        return _temporary_session(session_id)
    try:
        return session_service.get_by_id(session_id)
    except KeyError:
        return _temporary_session(session_id)


def _fallback_character() -> Character:
    return Character(id="temporary_hit_test_character", name="")


def create_lorebooks_router(
    auth_dependency,
    lorebook_service: LorebookService | None,
    account_service: AccountService | None,
    session_service: SessionService | None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/lorebooks", dependencies=[Depends(auth_dependency)])
    async def list_lorebooks():
        if lorebook_service is None:
            return {"lorebooks": []}
        return {"lorebooks": [serialize_lorebook(book) for book in lorebook_service.list_lorebooks()]}

    @router.post("/api/lorebooks", dependencies=[Depends(auth_dependency)])
    async def create_lorebook(request: Request):
        body = await _read_json_object(request)
        if lorebook_service is None:
            raise _service_unavailable()
        fields = _validate_lorebook_body(body)
        try:
            book = Lorebook(id="", name=fields.pop("name", ""), **fields)
            return serialize_lorebook(lorebook_service.create_lorebook(book))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @router.post("/api/lorebooks/import", dependencies=[Depends(auth_dependency)])
    async def import_lorebook(request: Request):
        body = await _read_json_object(request)
        if lorebook_service is None:
            raise _service_unavailable()
        try:
            return serialize_lorebook(lorebook_service.import_lorebook(body))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @router.post("/api/lorebooks/hit-test", dependencies=[Depends(auth_dependency)])
    async def hit_test(request: Request):
        body = await _read_json_object(request)
        if lorebook_service is None:
            raise _service_unavailable()
        fields = _validate_hit_test_body(body)
        _ensure_lorebooks_exist(lorebook_service, fields["lorebook_ids"])
        entries: list[LorebookEntry] = []
        for book_id in fields["lorebook_ids"]:
            entries.extend(lorebook_service.list_entries(book_id))
        session = _load_hit_test_session(session_service, fields["session_id"])
        result = LorebookMatcher().match(
            entries,
            fields["input"],
            [],
            session,
            _fallback_character(),
        )
        return {
            "hits": [serialize_hit(hit) for hit in result.hits],
            "filtered": [serialize_hit(hit) for hit in result.filtered],
            "buckets": result.buckets,
        }

    @router.get("/api/lorebooks/{book_id}", dependencies=[Depends(auth_dependency)])
    async def get_lorebook(book_id: str):
        if lorebook_service is None:
            raise HTTPException(status_code=404, detail="lorebook not found")
        book = lorebook_service.get_lorebook(book_id)
        if book is None:
            raise HTTPException(status_code=404, detail="lorebook not found")
        return serialize_lorebook(book)

    @router.patch("/api/lorebooks/{book_id}", dependencies=[Depends(auth_dependency)])
    async def update_lorebook(book_id: str, request: Request):
        body = await _read_json_object(request)
        if lorebook_service is None:
            raise _service_unavailable()
        fields = _validate_lorebook_body(body)
        try:
            return serialize_lorebook(lorebook_service.update_lorebook(book_id, **fields))
        except KeyError:
            raise HTTPException(status_code=404, detail="lorebook not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @router.delete("/api/lorebooks/{book_id}", dependencies=[Depends(auth_dependency)])
    async def delete_lorebook(book_id: str):
        if lorebook_service is None:
            raise _service_unavailable()
        if lorebook_service.get_lorebook(book_id) is None:
            raise HTTPException(status_code=404, detail="lorebook not found")
        lorebook_service.delete_lorebook(book_id)
        return {"ok": True}

    @router.get("/api/lorebooks/{book_id}/entries", dependencies=[Depends(auth_dependency)])
    async def list_entries(book_id: str):
        if lorebook_service is None:
            raise HTTPException(status_code=404, detail="lorebook not found")
        if lorebook_service.get_lorebook(book_id) is None:
            raise HTTPException(status_code=404, detail="lorebook not found")
        return {"entries": [serialize_entry(entry) for entry in lorebook_service.list_entries(book_id)]}

    @router.post("/api/lorebooks/{book_id}/entries", dependencies=[Depends(auth_dependency)])
    async def create_entry(book_id: str, request: Request):
        body = await _read_json_object(request)
        if lorebook_service is None:
            raise _service_unavailable()
        fields = _validate_entry_body(body)
        try:
            entry = LorebookEntry(
                id="",
                lorebook_id=book_id,
                title=fields.pop("title", ""),
                content=fields.pop("content", ""),
                **fields,
            )
            return serialize_entry(lorebook_service.create_entry(entry))
        except KeyError:
            raise HTTPException(status_code=404, detail="lorebook not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @router.patch("/api/lorebooks/{book_id}/entries/{entry_id}", dependencies=[Depends(auth_dependency)])
    async def update_entry(book_id: str, entry_id: str, request: Request):
        body = await _read_json_object(request)
        if lorebook_service is None:
            raise _service_unavailable()
        fields = _validate_entry_body(body)
        current = lorebook_service.get_entry(entry_id)
        if current is None or current.lorebook_id != book_id:
            raise HTTPException(status_code=404, detail="lorebook entry not found")
        try:
            return serialize_entry(lorebook_service.update_entry(entry_id, **fields))
        except KeyError:
            raise HTTPException(status_code=404, detail="lorebook entry not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @router.delete("/api/lorebooks/{book_id}/entries/{entry_id}", dependencies=[Depends(auth_dependency)])
    async def delete_entry(book_id: str, entry_id: str):
        if lorebook_service is None:
            raise _service_unavailable()
        current = lorebook_service.get_entry(entry_id)
        if current is None or current.lorebook_id != book_id:
            raise HTTPException(status_code=404, detail="lorebook entry not found")
        lorebook_service.delete_entry(entry_id)
        return {"ok": True}

    @router.get("/api/lorebooks/{book_id}/export", dependencies=[Depends(auth_dependency)])
    async def export_lorebook(book_id: str):
        if lorebook_service is None:
            raise HTTPException(status_code=404, detail="lorebook not found")
        try:
            return lorebook_service.export_lorebook(book_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="lorebook not found") from None

    @router.patch("/api/accounts/{account_id}/lorebooks", dependencies=[Depends(auth_dependency)])
    async def set_account_lorebooks(account_id: str, request: Request):
        body = await _read_json_object(request)
        if lorebook_service is None or account_service is None:
            raise _service_unavailable()
        lorebook_ids = _validate_assignment_body(body)
        _ensure_lorebooks_exist(lorebook_service, lorebook_ids)
        try:
            lorebook_service.set_account_lorebooks(account_id, lorebook_ids)
            return serialize_account(account_service.get_by_id(account_id))
        except KeyError:
            raise HTTPException(status_code=404, detail="account not found") from None

    @router.patch("/api/sessions/{session_id}/lorebooks", dependencies=[Depends(auth_dependency)])
    async def set_session_lorebooks(session_id: str, request: Request):
        body = await _read_json_object(request)
        if lorebook_service is None or session_service is None:
            raise _service_unavailable()
        lorebook_ids = _validate_assignment_body(body)
        _ensure_lorebooks_exist(lorebook_service, lorebook_ids)
        try:
            lorebook_service.set_session_lorebooks(session_id, lorebook_ids)
            return serialize_session(session_service.get_by_id(session_id))
        except KeyError:
            raise HTTPException(status_code=404, detail="session not found") from None

    return router
