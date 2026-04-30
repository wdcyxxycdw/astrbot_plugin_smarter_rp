from pathlib import Path

from fastapi.testclient import TestClient

from smarter_rp.services.account_service import AccountIdentity, AccountService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage
from smarter_rp.web.app import create_app


LOREBOOK_FIELDS = {
    "id",
    "name",
    "description",
    "scope",
    "session_id",
    "metadata",
    "created_at",
    "updated_at",
}

ENTRY_FIELDS = {
    "id",
    "lorebook_id",
    "title",
    "content",
    "enabled",
    "constant",
    "keys",
    "secondary_keys",
    "selective",
    "regex",
    "case_sensitive",
    "position",
    "depth",
    "priority",
    "order",
    "probability",
    "cooldown_turns",
    "sticky_turns",
    "recursive",
    "group",
    "character_filter",
    "max_injections_per_chat",
    "metadata",
    "created_at",
    "updated_at",
}


def make_storage(tmp_path: Path) -> Storage:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    return storage


def auth(path: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}token=secret-token"


def create_book(client: TestClient, **overrides) -> dict:
    payload = {"name": "World", "description": "Shared lore", "metadata": {"tag": "core"}}
    payload.update(overrides)
    response = client.post(auth("/api/lorebooks"), json=payload)
    assert response.status_code == 200
    return response.json()


def create_entry(client: TestClient, book_id: str, **overrides) -> dict:
    payload = {
        "title": "Gate",
        "content": "The silver gate is sealed.",
        "keys": ["silver gate"],
        "position": "before_history",
        "priority": 5,
    }
    payload.update(overrides)
    response = client.post(auth(f"/api/lorebooks/{book_id}/entries"), json=payload)
    assert response.status_code == 200
    return response.json()


def test_lorebook_routes_require_auth(tmp_path: Path):
    client = TestClient(create_app(token="secret-token", storage=make_storage(tmp_path)))

    responses = [
        client.get("/api/lorebooks"),
        client.post("/api/lorebooks", json={"name": "World"}),
        client.post("/api/lorebooks/import", json={}),
        client.post("/api/lorebooks/hit-test", json={"lorebook_ids": [], "input": ""}),
        client.get("/api/lorebooks/lorebook_missing"),
        client.patch("/api/lorebooks/lorebook_missing", json={"name": "World"}),
        client.delete("/api/lorebooks/lorebook_missing"),
        client.get("/api/lorebooks/lorebook_missing/entries"),
        client.post("/api/lorebooks/lorebook_missing/entries", json={"title": "Gate"}),
        client.patch("/api/lorebooks/lorebook_missing/entries/entry_missing", json={"title": "Gate"}),
        client.delete("/api/lorebooks/lorebook_missing/entries/entry_missing"),
        client.get("/api/lorebooks/lorebook_missing/export"),
        client.patch("/api/accounts/account_missing/lorebooks", json={"lorebook_ids": []}),
        client.patch("/api/sessions/session_missing/lorebooks", json={"lorebook_ids": []}),
    ]

    assert [response.status_code for response in responses] == [401] * len(responses)


def test_crud_lorebook_and_entry(tmp_path: Path):
    storage = make_storage(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))

    book = create_book(client)
    assert set(book) == LOREBOOK_FIELDS
    assert book["id"].startswith("lorebook_")
    assert book["name"] == "World"
    assert book["description"] == "Shared lore"

    list_response = client.get(auth("/api/lorebooks"))
    get_response = client.get(auth(f"/api/lorebooks/{book['id']}"))
    patch_response = client.patch(
        auth(f"/api/lorebooks/{book['id']}"),
        json={"name": "World Prime", "description": "Updated", "metadata": {"tag": "prime"}},
    )

    assert list_response.status_code == 200
    assert list_response.json()["lorebooks"][0]["id"] == book["id"]
    assert get_response.status_code == 200
    assert get_response.json()["id"] == book["id"]
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "World Prime"
    assert patch_response.json()["metadata"] == {"tag": "prime"}

    entry = create_entry(client, book["id"])
    assert set(entry) == ENTRY_FIELDS
    assert entry["id"].startswith("entry_")
    assert entry["lorebook_id"] == book["id"]
    assert entry["keys"] == ["silver gate"]
    assert entry["priority"] == 5

    entries_response = client.get(auth(f"/api/lorebooks/{book['id']}/entries"))
    entry_patch_response = client.patch(
        auth(f"/api/lorebooks/{book['id']}/entries/{entry['id']}"),
        json={"title": "Gatehouse", "enabled": False, "keys": ["gatehouse"]},
    )
    entry_delete_response = client.delete(auth(f"/api/lorebooks/{book['id']}/entries/{entry['id']}"))
    book_delete_response = client.delete(auth(f"/api/lorebooks/{book['id']}"))
    missing_get_response = client.get(auth(f"/api/lorebooks/{book['id']}"))

    assert entries_response.status_code == 200
    assert entries_response.json()["entries"][0]["id"] == entry["id"]
    assert entry_patch_response.status_code == 200
    assert entry_patch_response.json()["title"] == "Gatehouse"
    assert entry_patch_response.json()["enabled"] is False
    assert entry_patch_response.json()["keys"] == ["gatehouse"]
    assert entry_delete_response.status_code == 200
    assert entry_delete_response.json() == {"ok": True}
    assert book_delete_response.status_code == 200
    assert book_delete_response.json() == {"ok": True}
    assert missing_get_response.status_code == 404


def test_entry_creation_uses_path_book_id_and_rejects_missing_book(tmp_path: Path):
    storage = make_storage(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))
    book = create_book(client)

    entry = create_entry(client, book["id"], lorebook_id="wrong")
    missing_response = client.post(
        auth("/api/lorebooks/lorebook_missing/entries"),
        json={"title": "Orphan", "content": "No book"},
    )

    assert entry["lorebook_id"] == book["id"]
    assert missing_response.status_code == 404


def test_missing_lorebook_read_and_delete_endpoints_return_404(tmp_path: Path):
    storage = make_storage(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))

    responses = [
        client.get(auth("/api/lorebooks/lorebook_missing")),
        client.delete(auth("/api/lorebooks/lorebook_missing")),
        client.get(auth("/api/lorebooks/lorebook_missing/entries")),
        client.get(auth("/api/lorebooks/lorebook_missing/export")),
    ]

    assert [response.status_code for response in responses] == [404] * len(responses)


def test_entry_delete_rejects_missing_or_wrong_book_entry(tmp_path: Path):
    storage = make_storage(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))
    first_book = create_book(client, name="First")
    second_book = create_book(client, name="Second")
    entry = create_entry(client, first_book["id"])

    missing_response = client.delete(auth(f"/api/lorebooks/{first_book['id']}/entries/entry_missing"))
    wrong_book_response = client.delete(auth(f"/api/lorebooks/{second_book['id']}/entries/{entry['id']}"))
    get_response = client.get(auth(f"/api/lorebooks/{first_book['id']}/entries"))

    assert missing_response.status_code == 404
    assert wrong_book_response.status_code == 404
    assert get_response.status_code == 200
    assert get_response.json()["entries"][0]["id"] == entry["id"]


def test_hit_test_returns_expected_hit(tmp_path: Path):
    storage = make_storage(tmp_path)
    session = SessionService(storage).get_or_create("origin:1", None)
    client = TestClient(create_app(token="secret-token", storage=storage))
    book = create_book(client)
    entry = create_entry(client, book["id"], title="Gate", content="Gate lore", keys=["silver gate"])

    response = client.post(
        auth("/api/lorebooks/hit-test"),
        json={"lorebook_ids": [book["id"]], "input": "We approach the SILVER GATE.", "session_id": session.id},
    )

    assert response.status_code == 200
    data = response.json()
    assert [hit["entry_id"] for hit in data["hits"]] == [entry["id"]]
    assert data["hits"][0]["matched_key"] == "silver gate"
    assert data["filtered"] == []
    assert data["buckets"] == {"before_history": "Gate lore"}


def test_hit_test_rejects_missing_lorebook_id(tmp_path: Path):
    storage = make_storage(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))

    response = client.post(
        auth("/api/lorebooks/hit-test"),
        json={"lorebook_ids": ["lorebook_missing"], "input": "No hit"},
    )

    assert response.status_code == 404


def test_account_and_session_lorebook_assignment_endpoints_update_state(tmp_path: Path):
    storage = make_storage(tmp_path)
    accounts = AccountService(storage)
    sessions = SessionService(storage)
    account = accounts.get_or_create(AccountIdentity("adapter", "platform", "bot", "Bot"))
    session = sessions.get_or_create("origin:1", account.id)
    client = TestClient(create_app(token="secret-token", storage=storage))
    book = create_book(client)

    account_response = client.patch(
        auth(f"/api/accounts/{account.id}/lorebooks"),
        json={"lorebook_ids": [book["id"]]},
    )
    session_response = client.patch(
        auth(f"/api/sessions/{session.id}/lorebooks"),
        json={"lorebook_ids": [book["id"]]},
    )

    assert account_response.status_code == 200
    assert account_response.json()["default_lorebook_ids"] == [book["id"]]
    assert accounts.get_by_id(account.id).default_lorebook_ids == [book["id"]]
    assert session_response.status_code == 200
    assert session_response.json()["active_lorebook_ids"] == [book["id"]]
    assert sessions.get_by_id(session.id).active_lorebook_ids == [book["id"]]


def test_account_and_session_lorebook_assignment_rejects_missing_lorebook(tmp_path: Path):
    storage = make_storage(tmp_path)
    accounts = AccountService(storage)
    sessions = SessionService(storage)
    account = accounts.get_or_create(AccountIdentity("adapter", "platform", "bot", "Bot"))
    session = sessions.get_or_create("origin:1", account.id)
    client = TestClient(create_app(token="secret-token", storage=storage))

    account_response = client.patch(
        auth(f"/api/accounts/{account.id}/lorebooks"),
        json={"lorebook_ids": ["lorebook_missing"]},
    )
    session_response = client.patch(
        auth(f"/api/sessions/{session.id}/lorebooks"),
        json={"lorebook_ids": ["lorebook_missing"]},
    )

    assert account_response.status_code == 404
    assert session_response.status_code == 404
    assert accounts.get_by_id(account.id).default_lorebook_ids == []
    assert sessions.get_by_id(session.id).active_lorebook_ids == []


def test_import_export_round_trip(tmp_path: Path):
    storage = make_storage(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))
    book = create_book(client, name="World")
    create_entry(client, book["id"], title="Gate", content="Gate lore", keys=["gate"])

    export_response = client.get(auth(f"/api/lorebooks/{book['id']}/export"))
    import_response = client.post(auth("/api/lorebooks/import"), json=export_response.json())

    assert export_response.status_code == 200
    exported = export_response.json()
    assert exported["format"] == "smarter_rp_lorebook_v1"
    assert exported["lorebook"]["id"] == book["id"]
    assert len(exported["entries"]) == 1
    assert import_response.status_code == 200
    imported = import_response.json()
    assert imported["name"] == "World"
    assert imported["id"] != book["id"]
    imported_entries = client.get(auth(f"/api/lorebooks/{imported['id']}/entries")).json()["entries"]
    assert imported_entries[0]["keys"] == ["gate"]


def test_validation_errors_for_wrong_types_without_update(tmp_path: Path):
    storage = make_storage(tmp_path)
    client = TestClient(create_app(token="secret-token", storage=storage))
    book = create_book(client)
    entry = create_entry(client, book["id"])

    responses = [
        client.post(auth("/api/lorebooks"), json=["name", "World"]),
        client.post(auth("/api/lorebooks"), content="{bad json", headers={"content-type": "application/json"}),
        client.post(auth("/api/lorebooks"), json={"name": 123}),
        client.post(auth("/api/lorebooks"), json={"metadata": []}),
        client.patch(auth(f"/api/lorebooks/{book['id']}"), json={"session_id": 1}),
        client.post(auth(f"/api/lorebooks/{book['id']}/entries"), json={"title": 123}),
        client.post(auth(f"/api/lorebooks/{book['id']}/entries"), json={"keys": "gate"}),
        client.post(auth(f"/api/lorebooks/{book['id']}/entries"), json={"enabled": "true"}),
        client.post(auth(f"/api/lorebooks/{book['id']}/entries"), json={"priority": 1.5}),
        client.post(auth(f"/api/lorebooks/{book['id']}/entries"), json={"probability": "high"}),
        client.patch(auth(f"/api/lorebooks/{book['id']}/entries/{entry['id']}"), json={"metadata": []}),
        client.post(auth("/api/lorebooks/import"), json=[]),
        client.post(
            auth("/api/lorebooks/import"),
            json={"format": "smarter_rp_lorebook_v1", "entries": [{"depth": []}]},
        ),
        client.post(auth("/api/lorebooks/hit-test"), json={"lorebook_ids": "book", "input": "x"}),
        client.post(auth("/api/lorebooks/hit-test"), json={"lorebook_ids": [], "input": 1}),
        client.patch(auth("/api/accounts/missing/lorebooks"), json={"lorebook_ids": "book"}),
        client.patch(auth("/api/sessions/missing/lorebooks"), json={"lorebook_ids": "book"}),
    ]

    assert [response.status_code for response in responses] == [400] * len(responses)
    assert client.get(auth(f"/api/lorebooks/{book['id']}" )).json()["name"] == "World"
    assert client.get(auth(f"/api/lorebooks/{book['id']}/entries" )).json()["entries"][0]["title"] == "Gate"


def test_no_storage_returns_empty_lists_and_503_for_writes():
    client = TestClient(create_app(token="secret-token"))

    list_response = client.get(auth("/api/lorebooks"))
    entries_response = client.get(auth("/api/lorebooks/missing/entries"))
    create_response = client.post(auth("/api/lorebooks"), json={"name": "World"})
    assign_response = client.patch(auth("/api/accounts/account_1/lorebooks"), json={"lorebook_ids": []})

    assert list_response.status_code == 200
    assert list_response.json() == {"lorebooks": []}
    assert entries_response.status_code == 404
    assert create_response.status_code == 503
    assert assign_response.status_code == 503
