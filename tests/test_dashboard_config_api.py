from pathlib import Path

from fastapi.testclient import TestClient

from smarter_rp.storage import Storage

DEFAULT_GLOBAL_PROMPT = "Stay in character and continue the roleplay naturally."
from smarter_rp.web.app import create_app


def make_storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    return storage


def test_dashboard_config_get_returns_default_global_prompt(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    response = client.get("/api/dashboard/config?token=secret-token")

    assert response.status_code == 200
    assert response.json() == {"global_prompt": DEFAULT_GLOBAL_PROMPT}


def test_dashboard_config_patch_persists_global_prompt(tmp_path: Path):
    storage = make_storage(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.patch(
        "/api/dashboard/config?token=secret-token",
        json={"global_prompt": "Custom global prompt"},
    )

    assert response.status_code == 200
    assert response.json() == {"global_prompt": "Custom global prompt"}
    assert storage.get_setting("global_prompt") == "Custom global prompt"

    get_response = client.get("/api/dashboard/config?token=secret-token")
    assert get_response.json() == {"global_prompt": "Custom global prompt"}


def test_dashboard_config_patch_rejects_non_object_body(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    response = client.patch(
        "/api/dashboard/config?token=secret-token",
        json=["not", "object"],
    )

    assert response.status_code == 400


def test_dashboard_config_patch_rejects_non_string_prompt(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    response = client.patch(
        "/api/dashboard/config?token=secret-token",
        json={"global_prompt": 123},
    )

    assert response.status_code == 400


def test_dashboard_config_patch_rejects_malformed_json(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)), raise_server_exceptions=False)

    response = client.patch(
        "/api/dashboard/config?token=secret-token",
        content="{bad",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
