from pathlib import Path

from fastapi.testclient import TestClient

from smarter_rp.services.debug_service import DebugService
from smarter_rp.storage import Storage
from smarter_rp.web.app import create_app


def make_storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    return storage


def test_debug_snapshots_get_requires_token(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    response = client.get("/api/debug/snapshots")

    assert response.status_code == 401


def test_debug_snapshots_get_returns_recent_redacted_snapshots(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = DebugService(storage)
    first = service.save_snapshot("session_1", "prompt", "old token=old-secret")
    second = service.save_snapshot("session_1", "raw_request", "new api_key=sk-new-secret")
    storage.execute("UPDATE debug_snapshots SET created_at = ? WHERE id = ?", (1, first.id))
    storage.execute("UPDATE debug_snapshots SET created_at = ? WHERE id = ?", (2, second.id))
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.get("/api/debug/snapshots?token=secret-token")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": second.id,
            "session_id": "session_1",
            "type": "raw_request",
            "content": "new api_key=[REDACTED]",
            "created_at": 2,
        },
        {
            "id": first.id,
            "session_id": "session_1",
            "type": "prompt",
            "content": "old token=[REDACTED]",
            "created_at": 1,
        },
    ]
    assert "old-secret" not in response.text
    assert "sk-new-secret" not in response.text


def test_debug_snapshots_get_supports_filters(tmp_path: Path):
    storage = make_storage(tmp_path)
    service = DebugService(storage)
    service.save_snapshot("session_1", "memory", "memory")
    match = service.save_snapshot("session_1", "prompt", "prompt")
    service.save_snapshot("session_2", "prompt", "other prompt")
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.get(
        "/api/debug/snapshots?token=secret-token&session_id=session_1&snapshot_type=prompt&limit=1"
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": match.id,
            "session_id": "session_1",
            "type": "prompt",
            "content": "prompt",
            "created_at": match.created_at,
        }
    ]


def test_debug_snapshot_get_returns_one_snapshot_or_404(tmp_path: Path):
    storage = make_storage(tmp_path)
    snapshot = DebugService(storage).save_snapshot("session_1", "prompt", "token=secret")
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.get(f"/api/debug/snapshots/{snapshot.id}?token=secret-token")
    missing_response = client.get("/api/debug/snapshots/debug_missing?token=secret-token")

    assert response.status_code == 200
    assert response.json() == {
        "id": snapshot.id,
        "session_id": "session_1",
        "type": "prompt",
        "content": "token=[REDACTED]",
        "created_at": snapshot.created_at,
    }
    assert "secret" not in response.text
    assert missing_response.status_code == 404


def test_debug_snapshots_without_storage_returns_empty_list():
    client = TestClient(create_app(token="secret-token"))

    response = client.get("/api/debug/snapshots?token=secret-token")

    assert response.status_code == 200
    assert response.json() == []
