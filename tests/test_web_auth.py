from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from smarter_rp.models import Character, Lorebook, LorebookEntry
from smarter_rp.services.character_service import CharacterService
from smarter_rp.services.lorebook_service import LorebookService
from smarter_rp.services.memory_service import MemoryService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage
from smarter_rp.web.app import create_app


def test_health_does_not_require_token():
    client = TestClient(create_app(token="secret-token"))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_root_serves_webui_or_clear_placeholder():
    client = TestClient(create_app(token="secret-token"))

    response = client.get("/")

    assert response.status_code == 200
    assert "Smarter RP" in response.text


def test_dashboard_status_without_token_returns_401():
    client = TestClient(create_app(token="secret-token"))

    response = client.get("/api/dashboard/status")

    assert response.status_code == 401


def test_dashboard_status_accepts_bearer_token():
    client = TestClient(create_app(token="secret-token"))

    response = client.get(
        "/api/dashboard/status",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    assert response.json()["webui"] == "running"


def test_dashboard_status_accepts_query_token():
    client = TestClient(create_app(token="secret-token"))

    response = client.get("/api/dashboard/status?token=secret-token")

    assert response.status_code == 200
    assert response.json()["webui"] == "running"


def test_dashboard_status_rejects_wrong_token():
    client = TestClient(create_app(token="secret-token"))

    response = client.get(
        "/api/dashboard/status?token=wrong-token",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401


def make_storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    return storage


WRITE_ENDPOINTS = [
    ("patch", "/api/accounts/{profile_id}", {"default_enabled": False}),
    ("patch", "/api/sessions/{session_id}", {"paused": True}),
    ("post", "/api/characters", {"name": "Alice"}),
    ("post", "/api/characters/import-persona", {"name": "Persona", "prompt": "Act"}),
    ("patch", "/api/characters/{character_id}", {"name": "Alice 2"}),
    ("delete", "/api/characters/{character_id}", None),
    ("post", "/api/lorebooks", {"name": "World"}),
    ("post", "/api/lorebooks/import", {"name": "Imported", "entries": []}),
    ("post", "/api/lorebooks/hit-test", {"lorebook_ids": ["lorebook_1"], "input": "gate"}),
    ("patch", "/api/lorebooks/{lorebook_id}", {"name": "World 2"}),
    ("delete", "/api/lorebooks/{lorebook_id}", None),
    ("post", "/api/lorebooks/{lorebook_id}/entries", {"title": "Gate", "content": "Lore"}),
    ("patch", "/api/lorebooks/{lorebook_id}/entries/{entry_id}", {"title": "Gate 2"}),
    ("delete", "/api/lorebooks/{lorebook_id}/entries/{entry_id}", None),
    ("patch", "/api/accounts/{profile_id}/lorebooks", {"lorebook_ids": []}),
    ("patch", "/api/sessions/{session_id}/lorebooks", {"lorebook_ids": []}),
    ("post", "/api/sessions/{session_id}/history/undo", None),
    ("delete", "/api/sessions/{session_id}/history", None),
    ("delete", "/api/memory/memories/{memory_id}", None),
    ("delete", "/api/memory/sessions/{session_id}", None),
]


def make_auth_fixtures(tmp_path: Path):
    storage = make_storage(tmp_path)
    sessions = SessionService(storage)
    session = sessions.get_or_create("origin:auth", "profile_1")
    character = CharacterService(storage).save_character(Character(id="character_1", name="Alice"))
    lorebook_service = LorebookService(storage)
    lorebook = lorebook_service.create_lorebook(Lorebook(id="lorebook_1", name="World"))
    entry = lorebook_service.create_entry(LorebookEntry("entry_1", lorebook.id, "Gate", "Lore"))
    memory = MemoryService(storage, sessions).create_event_memory(session.id, "Alice found a key.", importance=3, confidence=0.8)
    values = {
        "profile_id": "profile_1",
        "session_id": session.id,
        "character_id": character.id,
        "lorebook_id": lorebook.id,
        "entry_id": entry.id,
        "memory_id": memory.id,
    }
    return storage, values


def call_client(client: TestClient, method: str, path: str, json_body):
    client_method = getattr(client, method)
    return client_method(path, json=json_body) if json_body is not None else client_method(path)


@pytest.mark.parametrize(("method", "path", "json_body"), WRITE_ENDPOINTS)
def test_write_endpoints_reject_missing_token(tmp_path: Path, method, path, json_body):
    storage, values = make_auth_fixtures(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))
    resolved_path = path.format(**values)

    response = call_client(client, method, resolved_path, json_body)

    assert response.status_code == 401


def test_write_endpoint_rejects_wrong_token(tmp_path: Path):
    storage, values = make_auth_fixtures(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.patch(
        f"/api/sessions/{values['session_id']}?token=wrong-token",
        json={"paused": True},
    )

    assert response.status_code == 401


def test_write_endpoint_accepts_bearer_token(tmp_path: Path):
    storage, values = make_auth_fixtures(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.patch(
        f"/api/sessions/{values['session_id']}",
        headers={"Authorization": "Bearer secret-token"},
        json={"paused": True},
    )

    assert response.status_code == 200
    assert response.json()["paused"] is True


def test_write_endpoint_accepts_query_token(tmp_path: Path):
    storage, values = make_auth_fixtures(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.patch(
        f"/api/sessions/{values['session_id']}?token=secret-token",
        json={"paused": True},
    )

    assert response.status_code == 200
    assert response.json()["paused"] is True


@pytest.mark.parametrize("token", ["", "   "])
def test_create_app_rejects_empty_token(token):
    with pytest.raises(ValueError):
        create_app(token=token)
