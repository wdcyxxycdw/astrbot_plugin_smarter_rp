from pathlib import Path

from fastapi.testclient import TestClient

from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.webui_service import WebuiService
from smarter_rp.storage import Storage


def test_ensure_token_generates_persists_and_reuses_token(tmp_path: Path):
    token_path = tmp_path / "webui" / "token.txt"
    service = WebuiService(token_path, "127.0.0.1", 8000)

    token = service.ensure_token()
    second_token = service.ensure_token()

    assert len(token) >= 32
    assert second_token == token
    assert token_path.read_text(encoding="utf-8") == token


def test_ensure_token_reads_existing_token_file(tmp_path: Path):
    token_path = tmp_path / "token.txt"
    token_path.write_text(" existing-token \n", encoding="utf-8")
    service = WebuiService(token_path, "127.0.0.1", 8000)

    token = service.ensure_token()

    assert token == "existing-token"
    assert service.token == "existing-token"


def test_ensure_token_replaces_blank_token_file(tmp_path: Path):
    token_path = tmp_path / "token.txt"
    token_path.write_text("  \n\t", encoding="utf-8")
    service = WebuiService(token_path, "127.0.0.1", 8000)

    token = service.ensure_token()

    assert len(token) >= 32
    assert token.strip() == token
    assert token_path.read_text(encoding="utf-8") == token


def test_url_for_display_uses_host_port_and_token(tmp_path: Path):
    token_path = tmp_path / "token.txt"
    token_path.write_text("display-token", encoding="utf-8")
    service = WebuiService(token_path, "127.0.0.1", 12345)

    assert service.url_for_display() == "http://127.0.0.1:12345/?token=display-token"


def test_url_for_display_keeps_all_interface_url_parseable(tmp_path: Path):
    token_path = tmp_path / "token.txt"
    token_path.write_text("display-token", encoding="utf-8")
    service = WebuiService(token_path, "0.0.0.0", 12345)

    assert service.url_for_display() == "http://0.0.0.0:12345/?token=display-token"


def test_build_app_returns_app_with_health_endpoint(tmp_path: Path):
    service = WebuiService(tmp_path / "token.txt", "127.0.0.1", 8000)
    client = TestClient(service.build_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_build_app_uses_storage_for_debug_snapshots(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    snapshot = DebugService(storage).save_snapshot("session_1", "prompt", "hello token=secret")
    service = WebuiService(tmp_path / "token.txt", "127.0.0.1", 8000, storage=storage)
    client = TestClient(service.build_app())

    response = client.get(f"/api/debug/snapshots/{snapshot.id}?token={service.ensure_token()}")

    assert response.status_code == 200
    assert response.json()["id"] == snapshot.id
    assert response.json()["content"] == "hello token=[REDACTED]"


def test_request_stop_sets_server_should_exit(tmp_path: Path):
    class FakeServer:
        should_exit = False

    service = WebuiService(tmp_path / "token.txt", "127.0.0.1", 8000)
    fake_server = FakeServer()
    service.server = fake_server

    service.request_stop()

    assert fake_server.should_exit is True
