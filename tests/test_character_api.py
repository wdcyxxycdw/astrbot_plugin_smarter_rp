from pathlib import Path

from fastapi.testclient import TestClient

from smarter_rp.models import Character
from smarter_rp.services.character_service import CharacterService
from smarter_rp.storage import Storage
from smarter_rp.web.app import create_app


CHARACTER_FIELDS = {
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
}


def make_storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    return storage


def test_characters_get_requires_token(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    response = client.get("/api/characters")

    assert response.status_code == 401


def test_characters_get_returns_serialized_characters(tmp_path: Path):
    storage = make_storage(tmp_path)
    character = CharacterService(storage).save_character(
        Character(
            id="character_alice",
            name="Alice",
            aliases=["Al"],
            description="A traveler",
            personality="Curious",
            scenario="At the gate",
            first_message="Hello.",
            alternate_greetings=["Hi."],
            example_dialogues=[{"role": "user", "content": "Hello"}],
            speaking_style="Warm",
            system_prompt="You are Alice.",
            post_history_prompt="Remember the gate.",
            author_note="Stay gentle.",
            linked_lorebook_ids=["lore_1"],
            metadata={"tags": ["hero"]},
        )
    )
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.get("/api/characters?token=secret-token")

    assert response.status_code == 200
    assert response.json() == {"characters": [serialized_character(character)]}


def test_characters_post_creates_character_with_generated_id(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = CharacterService(storage)
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.post(
        "/api/characters?token=secret-token",
        json={
            "name": "Alice",
            "aliases": ["Al"],
            "description": "A traveler",
            "personality": "Curious",
            "scenario": "At the gate",
            "first_message": "Hello.",
            "alternate_greetings": ["Hi."],
            "example_dialogues": [{"role": "user", "content": "Hello"}],
            "speaking_style": "Warm",
            "system_prompt": "You are Alice.",
            "post_history_prompt": "Remember the gate.",
            "author_note": "Stay gentle.",
            "linked_lorebook_ids": ["lore_1"],
            "metadata": {"tags": ["hero"]},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data) == CHARACTER_FIELDS
    assert data["id"].startswith("character_")
    assert data["name"] == "Alice"
    assert data["aliases"] == ["Al"]
    assert service.get_character(data["id"]) is not None


def test_characters_get_patch_and_delete_character(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = CharacterService(storage)
    character = service.save_character(Character(id="character_alice", name="Alice"))
    client = TestClient(create_app(token="secret-token", storage=storage))

    get_response = client.get(f"/api/characters/{character.id}?token=secret-token")
    patch_response = client.patch(
        f"/api/characters/{character.id}?token=secret-token",
        json={"name": "Alicia", "aliases": ["Ace"], "metadata": {"updated": True}},
    )
    missing_get_response = client.get("/api/characters/missing?token=secret-token")
    delete_response = client.delete(f"/api/characters/{character.id}?token=secret-token")
    second_delete_response = client.delete(f"/api/characters/{character.id}?token=secret-token")

    assert get_response.status_code == 200
    assert get_response.json()["id"] == character.id
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Alicia"
    assert patch_response.json()["aliases"] == ["Ace"]
    assert patch_response.json()["metadata"] == {"updated": True}
    assert missing_get_response.status_code == 404
    assert delete_response.status_code == 200
    assert delete_response.json() == {"ok": True}
    assert second_delete_response.status_code == 200
    assert second_delete_response.json() == {"ok": True}
    assert service.get_character(character.id) is None


def test_characters_patch_missing_returns_404(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    response = client.patch(
        "/api/characters/missing?token=secret-token",
        json={"name": "Nobody"},
    )

    assert response.status_code == 404


def test_characters_reject_invalid_bodies_without_update(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = CharacterService(storage)
    character = service.save_character(Character(id="character_alice", name="Alice"))
    client = TestClient(create_app(token="secret-token", storage=storage))

    responses = [
        client.post("/api/characters?token=secret-token", json=["name", "Alice"]),
        client.post("/api/characters?token=secret-token", content="{bad json", headers={"content-type": "application/json"}),
        client.post("/api/characters?token=secret-token", json={"name": 123}),
        client.post("/api/characters?token=secret-token", json={"aliases": ["Al", 1]}),
        client.post("/api/characters?token=secret-token", json={"example_dialogues": ["hello"]}),
        client.post("/api/characters?token=secret-token", json={"metadata": []}),
        client.patch(f"/api/characters/{character.id}?token=secret-token", json="name"),
        client.patch(f"/api/characters/{character.id}?token=secret-token", json={"system_prompt": 1}),
        client.patch(f"/api/characters/{character.id}?token=secret-token", json={"linked_lorebook_ids": "lore_1"}),
    ]

    assert [response.status_code for response in responses] == [422] * len(responses)
    assert service.get_character(character.id).name == "Alice"


def test_persona_preview_serializes_temporary_character(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    response = client.get(
        "/api/characters/persona-preview?token=secret-token&name=Narrator&prompt=Guide%20the%20scene"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"].startswith("temporary_persona_")
    assert data["name"] == "Narrator"
    assert data["system_prompt"] == "Guide the scene"
    assert data["metadata"] == {"temporary": True, "source": "astrbot_persona"}


def test_import_persona_persists_character_with_import_metadata(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = CharacterService(storage)
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.post(
        "/api/characters/import-persona?token=secret-token",
        json={"name": "Narrator", "prompt": "Guide the scene"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"].startswith("character_")
    assert data["name"] == "Narrator"
    assert data["system_prompt"] == "Guide the scene"
    assert data["metadata"] == {"source": "astrbot_persona", "imported": True}
    assert service.get_character(data["id"]) is not None


def test_import_persona_rejects_invalid_body(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    responses = [
        client.post("/api/characters/import-persona?token=secret-token", json=["Narrator"]),
        client.post("/api/characters/import-persona?token=secret-token", json={"name": 1, "prompt": "Prompt"}),
        client.post("/api/characters/import-persona?token=secret-token", json={"name": "Narrator", "prompt": 1}),
    ]

    assert [response.status_code for response in responses] == [422, 422, 422]


def serialized_character(character: Character) -> dict:
    return {
        "id": character.id,
        "name": character.name,
        "aliases": character.aliases,
        "description": character.description,
        "personality": character.personality,
        "scenario": character.scenario,
        "first_message": character.first_message,
        "alternate_greetings": character.alternate_greetings,
        "example_dialogues": character.example_dialogues,
        "speaking_style": character.speaking_style,
        "system_prompt": character.system_prompt,
        "post_history_prompt": character.post_history_prompt,
        "author_note": character.author_note,
        "linked_lorebook_ids": character.linked_lorebook_ids,
        "metadata": character.metadata,
        "created_at": character.created_at,
        "updated_at": character.updated_at,
    }
