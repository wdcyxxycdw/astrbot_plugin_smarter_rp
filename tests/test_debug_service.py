from pathlib import Path

from smarter_rp.services.debug_service import DebugService, redact_sensitive_text
from smarter_rp.storage import Storage


def test_redact_sensitive_text_removes_common_secret_forms():
    original = "\n".join(
        [
            "token=abc123",
            "token: def456",
            "api_key: sk-test-value",
            "api-key=hyphen-secret",
            "apikey=compact-secret",
            "Authorization: Bearer bearer-secret-value",
            "standalone sk-live-standalone-secret",
        ]
    )

    redacted = redact_sensitive_text(original)

    assert "abc123" not in redacted
    assert "def456" not in redacted
    assert "sk-test-value" not in redacted
    assert "hyphen-secret" not in redacted
    assert "compact-secret" not in redacted
    assert "Bearer bearer-secret-value" not in redacted
    assert "sk-live-standalone-secret" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_sensitive_text_removes_quoted_json_secret_forms():
    original = " ".join(
        [
            '{"token":"plain-secret"}',
            '{"api_key":"plain-secret"}',
            '{"apikey":"plain-secret"}',
            '{"api-key":"plain-secret"}',
        ]
    )

    redacted = redact_sensitive_text(original)

    assert "plain-secret" not in redacted
    assert redacted.count("[REDACTED]") == 4
    assert '"token":"[REDACTED]"' in redacted
    assert '"api_key":"[REDACTED]"' in redacted
    assert '"apikey":"[REDACTED]"' in redacted
    assert '"api-key":"[REDACTED]"' in redacted


def test_redact_sensitive_text_removes_common_json_http_secret_forms():
    original = " ".join(
        [
            '{"Authorization":"Bearer bearer-secret-value"}',
            '{"authorization": "Bearer bearer-secret-value"}',
            '{"access_token":"access-secret-value"}',
            '{"refresh_token":"refresh-secret-value"}',
            '{"id_token":"id-secret-value"}',
            '{"auth_token":"auth-secret-value"}',
        ]
    )

    redacted = redact_sensitive_text(original)

    for secret in [
        "bearer-secret-value",
        "access-secret-value",
        "refresh-secret-value",
        "id-secret-value",
        "auth-secret-value",
    ]:
        assert secret not in redacted
    assert redacted.count("[REDACTED]") == 6
    assert '"Authorization":"[REDACTED]"' in redacted
    assert '"authorization": "[REDACTED]"' in redacted
    assert '"access_token":"[REDACTED]"' in redacted
    assert '"refresh_token":"[REDACTED]"' in redacted
    assert '"id_token":"[REDACTED]"' in redacted
    assert '"auth_token":"[REDACTED]"' in redacted


def test_debug_service_saves_redacted_snapshot_and_reads_it_back(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    service = DebugService(storage)

    snapshot = service.save_snapshot(
        "session_1",
        "raw_request",
        "Authorization: Bearer secret-token\napi_key: sk-test-value\nhello",
    )
    loaded = service.get_snapshot(snapshot.id)

    assert snapshot.session_id == "session_1"
    assert snapshot.type == "raw_request"
    assert "secret-token" not in snapshot.content
    assert "sk-test-value" not in snapshot.content
    assert "[REDACTED]" in snapshot.content

    assert loaded == snapshot
    assert loaded is not None
    assert "secret-token" not in loaded.content
    assert "sk-test-value" not in loaded.content
    assert "hello" in loaded.content


def test_debug_service_allows_duplicate_content_snapshots(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    service = DebugService(storage)

    first = service.save_snapshot("session_1", "prompt", "token=abc123")
    second = service.save_snapshot("session_1", "prompt", "token=abc123")

    assert second.id != first.id
    assert service.get_snapshot(first.id) == first
    assert service.get_snapshot(second.id) == second


def test_debug_service_get_snapshot_returns_none_when_missing(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    service = DebugService(storage)

    assert service.get_snapshot("debug_missing") is None


def test_debug_service_lists_recent_snapshots_with_filters_and_limit_cap(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    service = DebugService(storage)

    first = service.save_snapshot("session_1", "prompt", "old token=first-secret")
    second = service.save_snapshot("session_1", "memory", "middle token=second-secret")
    third = service.save_snapshot("session_2", "prompt", "new token=third-secret")
    storage.execute("UPDATE debug_snapshots SET created_at = ? WHERE id = ?", (1, first.id))
    storage.execute("UPDATE debug_snapshots SET created_at = ? WHERE id = ?", (2, second.id))
    storage.execute("UPDATE debug_snapshots SET created_at = ? WHERE id = ?", (3, third.id))

    recent = service.list_snapshots(limit=2)
    session_prompts = service.list_snapshots(session_id="session_1", snapshot_type="prompt")
    capped = service.list_snapshots(limit=1000)

    assert [snapshot.id for snapshot in recent] == [third.id, second.id]
    assert [snapshot.id for snapshot in session_prompts] == [first.id]
    assert len(capped) == 3
    assert all("secret" not in snapshot.content for snapshot in capped)
