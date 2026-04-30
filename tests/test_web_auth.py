import pytest
from fastapi.testclient import TestClient

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


@pytest.mark.parametrize("token", ["", "   "])
def test_create_app_rejects_empty_token(token):
    with pytest.raises(ValueError):
        create_app(token=token)
