from json import JSONDecodeError
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from smarter_rp.ids import make_stable_id
from smarter_rp.models import Character
from smarter_rp.services.character_service import CharacterService


STRING_FIELDS = {
    "name",
    "system_prompt",
    "description",
    "personality",
    "scenario",
    "first_message",
    "speaking_style",
    "post_history_prompt",
    "author_note",
}
LIST_STRING_FIELDS = {"aliases", "alternate_greetings", "linked_lorebook_ids"}
CHARACTER_FIELDS = (
    "id",
    "name",
    "aliases",
    "description",
    "personality",
    "scenario",
    "first_message",
    "alternate_greetings",
    "example_dialogues",
    "speaking_style",
    "system_prompt",
    "post_history_prompt",
    "author_note",
    "linked_lorebook_ids",
    "metadata",
    "created_at",
    "updated_at",
)


async def _read_json_object(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except JSONDecodeError:
        raise HTTPException(status_code=422, detail="invalid JSON body") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="JSON body must be an object")
    return body


def _validate_character_body(body: dict[str, Any]) -> dict[str, Any]:
    values = {}
    for field, value in body.items():
        if field in STRING_FIELDS:
            if not isinstance(value, str):
                raise HTTPException(status_code=422, detail=f"{field} must be a string")
            values[field] = value
        elif field in LIST_STRING_FIELDS:
            values[field] = _validate_list_of_strings(field, value)
        elif field == "example_dialogues":
            values[field] = _validate_list_of_dicts(field, value)
        elif field == "metadata":
            if not isinstance(value, dict):
                raise HTTPException(status_code=422, detail="metadata must be a dict")
            values[field] = value
    return values


def _validate_list_of_strings(field: str, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(status_code=422, detail=f"{field} must be a list of strings")
    return value


def _validate_list_of_dicts(field: str, value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise HTTPException(status_code=422, detail=f"{field} must be a list of dicts")
    return value


def _require_string(body: dict[str, Any], field: str) -> str:
    value = body.get(field, "")
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail=f"{field} must be a string")
    return value


def serialize_character(character: Character) -> dict[str, Any]:
    return {field: getattr(character, field) for field in CHARACTER_FIELDS}


def create_characters_router(
    auth_dependency,
    character_service: CharacterService | None,
) -> APIRouter:
    router = APIRouter(prefix="/api/characters")

    @router.get("", dependencies=[Depends(auth_dependency)])
    async def list_characters():
        if character_service is None:
            return {"characters": []}
        return {
            "characters": [
                serialize_character(character)
                for character in character_service.list_characters()
            ]
        }

    @router.post("", dependencies=[Depends(auth_dependency)])
    async def create_character(request: Request):
        body = await _read_json_object(request)
        fields = _validate_character_body(body)
        fields["id"] = make_stable_id(
            "character",
            fields.get("name", ""),
            fields.get("aliases", []),
            fields.get("system_prompt", ""),
            fields.get("description", ""),
            fields.get("personality", ""),
            fields.get("scenario", ""),
        )
        character = Character(**fields)
        if character_service is None:
            return serialize_character(character)
        return serialize_character(character_service.create_character(character))

    @router.get("/persona-preview", dependencies=[Depends(auth_dependency)])
    async def persona_preview(name: str = "", prompt: str = ""):
        service = character_service
        if service is None:
            raise HTTPException(status_code=404, detail="character service not found")
        persona = SimpleNamespace(name=name, prompt=prompt)
        return serialize_character(service.character_from_persona(persona))

    @router.post("/import-persona", dependencies=[Depends(auth_dependency)])
    async def import_persona(request: Request):
        body = await _read_json_object(request)
        name = _require_string(body, "name")
        prompt = _require_string(body, "prompt")
        service = character_service
        if service is None:
            raise HTTPException(status_code=404, detail="character service not found")
        character = service.character_from_persona(SimpleNamespace(name=name, prompt=prompt))
        character.id = make_stable_id("character", character.name, character.system_prompt)
        character.metadata = {"source": "astrbot_persona", "imported": True}
        return serialize_character(service.create_character(character))

    @router.get("/{character_id}", dependencies=[Depends(auth_dependency)])
    async def get_character(character_id: str):
        if character_service is None:
            raise HTTPException(status_code=404, detail="character not found")
        character = character_service.get_character(character_id)
        if character is None:
            raise HTTPException(status_code=404, detail="character not found")
        return serialize_character(character)

    @router.patch("/{character_id}", dependencies=[Depends(auth_dependency)])
    async def update_character(character_id: str, request: Request):
        if character_service is None:
            raise HTTPException(status_code=404, detail="character not found")
        body = await _read_json_object(request)
        fields = _validate_character_body(body)
        try:
            return serialize_character(character_service.update_character(character_id, **fields))
        except KeyError:
            raise HTTPException(status_code=404, detail="character not found") from None

    @router.delete("/{character_id}", dependencies=[Depends(auth_dependency)])
    async def delete_character(character_id: str):
        if character_service is not None:
            character_service.delete_character(character_id)
        return {"ok": True}

    return router
