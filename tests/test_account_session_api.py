from pathlib import Path

from fastapi.testclient import TestClient

from smarter_rp.services.account_service import AccountIdentity, AccountService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage
from smarter_rp.web.app import create_app


def make_storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    return storage


def test_accounts_get_requires_token(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    response = client.get("/api/accounts")

    assert response.status_code == 401


def test_sessions_get_requires_token(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    response = client.get("/api/sessions")

    assert response.status_code == 401


def test_accounts_get_returns_profiles(tmp_path: Path):
    storage = make_storage(tmp_path)
    profile = AccountService(storage).get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Alice")
    )
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.get("/api/accounts?token=secret-token")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": profile.id,
            "adapter_name": "aiocqhttp",
            "platform": "qq",
            "account_id": "bot-123",
            "display_name": "Bot Alice",
            "default_enabled": True,
            "default_character_id": None,
            "default_lorebook_ids": [],
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }
    ]


def test_accounts_patch_updates_default_enabled(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = AccountService(storage)
    profile = service.get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Alice")
    )
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.patch(
        f"/api/accounts/{profile.id}?token=secret-token",
        json={"default_enabled": False},
    )

    assert response.status_code == 200
    assert response.json()["default_enabled"] is False
    assert service.get_by_id(profile.id).default_enabled is False


def test_accounts_patch_rejects_string_default_enabled_without_update(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = AccountService(storage)
    profile = service.get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Alice")
    )
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.patch(
        f"/api/accounts/{profile.id}?token=secret-token",
        json={"default_enabled": "false"},
    )

    assert response.status_code == 422
    assert service.get_by_id(profile.id).default_enabled is True


def test_accounts_patch_rejects_string_default_lorebook_ids_without_update(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = AccountService(storage)
    profile = service.get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Alice")
    )
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.patch(
        f"/api/accounts/{profile.id}?token=secret-token",
        json={"default_lorebook_ids": "abc"},
    )

    assert response.status_code == 422
    assert service.get_by_id(profile.id).default_lorebook_ids == []


def test_accounts_patch_rejects_non_object_body(tmp_path: Path):
    storage = make_storage(tmp_path)
    profile = AccountService(storage).get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Alice")
    )
    client = TestClient(create_app(token="secret-token", storage=storage))

    array_response = client.patch(
        f"/api/accounts/{profile.id}?token=secret-token",
        json=["default_enabled", False],
    )
    string_response = client.patch(
        f"/api/accounts/{profile.id}?token=secret-token",
        json="default_enabled",
    )

    assert array_response.status_code == 422
    assert string_response.status_code == 422


def test_accounts_patch_rejects_malformed_json(tmp_path: Path):
    storage = make_storage(tmp_path)
    profile = AccountService(storage).get_or_create(
        AccountIdentity("aiocqhttp", "qq", "bot-123", "Bot Alice")
    )
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.patch(
        f"/api/accounts/{profile.id}?token=secret-token",
        content="{bad json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422


def test_sessions_get_returns_sessions(tmp_path: Path):
    storage = make_storage(tmp_path)
    session = SessionService(storage).get_or_create("origin:1", "account_1")
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.get("/api/sessions?token=secret-token")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": session.id,
            "unified_msg_origin": "origin:1",
            "account_profile_id": "account_1",
            "paused": False,
            "active_character_id": None,
            "active_lorebook_ids": [],
            "summary": "",
            "state": {},
            "recent_messages": [],
            "last_lore_hits": [],
            "last_memory_hits": [],
            "turn_count": 0,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
    ]


def test_sessions_patch_updates_paused_and_active_lorebooks(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = SessionService(storage)
    session = service.get_or_create("origin:1", "account_1")
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.patch(
        f"/api/sessions/{session.id}?token=secret-token",
        json={"paused": True, "active_lorebook_ids": ["lore_1"]},
    )

    assert response.status_code == 200
    assert response.json()["paused"] is True
    assert response.json()["active_lorebook_ids"] == ["lore_1"]
    loaded = service.get_by_id(session.id)
    assert loaded.paused is True
    assert loaded.active_lorebook_ids == ["lore_1"]


def test_sessions_patch_rejects_string_paused_without_update(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = SessionService(storage)
    session = service.get_or_create("origin:1", "account_1")
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.patch(
        f"/api/sessions/{session.id}?token=secret-token",
        json={"paused": "true"},
    )

    assert response.status_code == 422
    assert service.get_by_id(session.id).paused is False


def test_sessions_patch_rejects_string_active_lorebook_ids(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = SessionService(storage)
    session = service.get_or_create("origin:1", "account_1")
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.patch(
        f"/api/sessions/{session.id}?token=secret-token",
        json={"active_lorebook_ids": "abc"},
    )

    assert response.status_code == 422
    assert service.get_by_id(session.id).active_lorebook_ids == []


def test_sessions_patch_rejects_non_object_body(tmp_path: Path):
    storage = make_storage(tmp_path)
    session = SessionService(storage).get_or_create("origin:1", "account_1")
    client = TestClient(create_app(token="secret-token", storage=storage))

    array_response = client.patch(
        f"/api/sessions/{session.id}?token=secret-token",
        json=["paused", True],
    )
    string_response = client.patch(
        f"/api/sessions/{session.id}?token=secret-token",
        json="paused",
    )

    assert array_response.status_code == 422
    assert string_response.status_code == 422


def test_create_app_without_storage_keeps_health_and_empty_lists():
    client = TestClient(create_app(token="secret-token"))

    health_response = client.get("/api/health")
    accounts_response = client.get("/api/accounts?token=secret-token")
    sessions_response = client.get("/api/sessions?token=secret-token")

    assert health_response.status_code == 200
    assert health_response.json() == {"ok": True}
    assert accounts_response.status_code == 200
    assert accounts_response.json() == []
    assert sessions_response.status_code == 200
    assert sessions_response.json() == []
