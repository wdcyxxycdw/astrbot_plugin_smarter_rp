from fastapi.testclient import TestClient

from smarter_rp.config import SmarterRpConfig
from smarter_rp.storage import Storage
from smarter_rp.tavern_bindings import TavernBindingService
from smarter_rp.web.app import create_web_app


class FakeTavernClient:
    def __init__(self):
        self.health_calls = 0
        self.character_imports = []
        self.worldbook_imports = []

    async def health(self):
        self.health_calls += 1
        return True

    async def list_characters(self):
        return [{"id": "char-a", "name": "Alice"}]

    async def import_character(self, filename, content, *, file_type, preserved_name=None):
        self.character_imports.append(
            {
                "filename": filename,
                "content": content,
                "file_type": file_type,
                "preserved_name": preserved_name,
            }
        )
        return {"ok": True, "filename": filename}

    async def list_worldbooks(self):
        return [{"name": "Lore"}]

    async def import_worldbook(self, filename, worldbook):
        self.worldbook_imports.append({"filename": filename, "worldbook": worldbook})
        return {"ok": True, "filename": filename}


def make_test_client(tmp_path, token="secret-token"):
    storage = Storage(tmp_path / "webui.db")
    storage.initialize()
    bindings = TavernBindingService(storage)
    tavern = FakeTavernClient()
    config = SmarterRpConfig.from_mapping(
        {
            "webui": {"token": token},
            "tavern": {
                "base_url": "http://127.0.0.1:8001",
                "install_dir": "/tmp/SillyTavern",
            },
        }
    )
    app = create_web_app(client=tavern, bindings=bindings, config=config)
    return TestClient(app), tavern, bindings


def auth_headers(token="secret-token"):
    return {"Authorization": f"Bearer {token}"}


def test_token_auth_rejects_missing_and_wrong_token(tmp_path):
    client, _tavern, _bindings = make_test_client(tmp_path)

    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers=auth_headers("wrong")).status_code == 401
    assert client.get("/api/status", headers=auth_headers()).status_code == 200
    assert client.get("/api/status", headers={"X-Smarter-Rp-Token": "secret-token"}).status_code == 200


def test_status_endpoint_calls_tavern_health(tmp_path):
    client, tavern, _bindings = make_test_client(tmp_path)

    response = client.get("/api/status", headers=auth_headers())

    assert response.status_code == 200
    assert tavern.health_calls == 1
    assert response.json() == {
        "webui": {"enabled": True, "host": "127.0.0.1", "port": 8010},
        "tavern": {
            "online": True,
            "baseUrl": "http://127.0.0.1:8001",
            "installDir": "/tmp/SillyTavern",
            "version": "",
        },
    }


def test_characters_list_and_import_call_client(tmp_path):
    client, tavern, _bindings = make_test_client(tmp_path)

    list_response = client.get("/api/characters", headers=auth_headers())
    import_response = client.post(
        "/api/characters/import",
        headers=auth_headers(),
        data={"fileType": "png", "preservedName": "Alice"},
        files={"file": ("alice.png", b"avatar-bytes", "image/png")},
    )

    assert list_response.status_code == 200
    assert list_response.json() == {"characters": [{"id": "char-a", "name": "Alice"}]}
    assert import_response.status_code == 200
    assert import_response.json() == {"result": {"ok": True, "filename": "alice.png"}}
    assert tavern.character_imports == [
        {
            "filename": "alice.png",
            "content": b"avatar-bytes",
            "file_type": "png",
            "preserved_name": "Alice",
        }
    ]


def test_worldbooks_list_and_import_call_client(tmp_path):
    client, tavern, _bindings = make_test_client(tmp_path)

    list_response = client.get("/api/worldbooks", headers=auth_headers())
    import_response = client.post(
        "/api/worldbooks/import",
        headers=auth_headers(),
        files={"file": ("lore.json", b'{"entries": []}', "application/json")},
    )

    assert list_response.status_code == 200
    assert list_response.json() == {"worldbooks": [{"name": "Lore"}]}
    assert import_response.status_code == 200
    assert import_response.json() == {"result": {"ok": True, "filename": "lore.json"}}
    assert tavern.worldbook_imports == [{"filename": "lore.json", "worldbook": {"entries": []}}]


def test_upload_import_requires_file(tmp_path):
    client, tavern, _bindings = make_test_client(tmp_path)

    character_response = client.post(
        "/api/characters/import",
        headers=auth_headers(),
        data={"fileType": "png"},
    )
    worldbook_response = client.post(
        "/api/worldbooks/import",
        headers=auth_headers(),
    )

    assert character_response.status_code == 400
    assert worldbook_response.status_code == 400
    assert tavern.character_imports == []
    assert tavern.worldbook_imports == []


def test_worldbook_import_rejects_invalid_json(tmp_path):
    client, tavern, _bindings = make_test_client(tmp_path)

    response = client.post(
        "/api/worldbooks/import",
        headers=auth_headers(),
        files={"file": ("bad.json", b"{bad json", "application/json")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid worldbook JSON"
    assert tavern.worldbook_imports == []


def test_upload_import_rejects_oversized_files(tmp_path):
    client, tavern, _bindings = make_test_client(tmp_path)
    too_large = b"x" * (10 * 1024 * 1024 + 1)

    character_response = client.post(
        "/api/characters/import",
        headers=auth_headers(),
        files={"file": ("alice.png", too_large, "image/png")},
    )
    worldbook_response = client.post(
        "/api/worldbooks/import",
        headers=auth_headers(),
        files={"file": ("lore.json", too_large, "application/json")},
    )

    assert character_response.status_code == 413
    assert worldbook_response.status_code == 413
    assert tavern.character_imports == []
    assert tavern.worldbook_imports == []


def test_non_status_api_requires_token(tmp_path):
    client, _tavern, _bindings = make_test_client(tmp_path)

    assert client.get("/api/characters").status_code == 401
    assert client.get("/api/worldbooks").status_code == 401
    assert client.get("/api/bindings/accounts").status_code == 401


def test_status_response_does_not_expose_secrets(tmp_path):
    client, _tavern, _bindings = make_test_client(tmp_path, token="top-secret-token")

    response = client.get("/api/status", headers=auth_headers("top-secret-token"))

    assert response.status_code == 200
    body = response.json()
    serialized = str(body).lower()
    assert "top-secret-token" not in serialized
    assert "token" not in serialized
    assert "password" not in serialized
    assert "auth" not in serialized


def test_account_binding_list_put_delete_uses_sqlite(tmp_path):
    client, _tavern, bindings = make_test_client(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "existing", "char-old")

    put_response = client.put(
        "/api/bindings/accounts/aiocqhttp/qq/12345",
        headers=auth_headers(),
        json={"characterId": "char-a"},
    )
    list_response = client.get("/api/bindings/accounts", headers=auth_headers())
    delete_response = client.delete(
        "/api/bindings/accounts/aiocqhttp/qq/12345",
        headers=auth_headers(),
    )

    assert put_response.status_code == 200
    assert put_response.json()["binding"]["accountId"] == "12345"
    assert put_response.json()["binding"]["characterId"] == "char-a"
    assert [item["accountId"] for item in list_response.json()["bindings"]] == ["12345", "existing"]
    assert delete_response.status_code == 204
    assert bindings.get_account_binding("aiocqhttp", "qq", "12345") is None
    assert bindings.get_account_binding("aiocqhttp", "qq", "existing") is not None


def test_chat_binding_list_delete_uses_sqlite(tmp_path):
    client, _tavern, bindings = make_test_client(tmp_path)
    kept = bindings.set_chat_binding("aiocqhttp", "qq", "12345", "keep", "char-a", "chat-a")
    deleted = bindings.set_chat_binding("aiocqhttp", "qq", "12345", "delete", "char-b", "chat-b")

    list_response = client.get("/api/bindings/chats", headers=auth_headers())
    delete_response = client.delete(
        "/api/bindings/chats/aiocqhttp/qq/12345/delete",
        headers=auth_headers(),
    )

    assert list_response.status_code == 200
    assert list_response.json() == {
        "bindings": [
            {
                "adapter": deleted.adapter,
                "platform": deleted.platform,
                "accountId": deleted.account_id,
                "sessionId": deleted.session_id,
                "characterId": deleted.character_id,
                "chatId": deleted.chat_id,
                "createdAt": deleted.created_at,
                "updatedAt": deleted.updated_at,
            },
            {
                "adapter": kept.adapter,
                "platform": kept.platform,
                "accountId": kept.account_id,
                "sessionId": kept.session_id,
                "characterId": kept.character_id,
                "chatId": kept.chat_id,
                "createdAt": kept.created_at,
                "updatedAt": kept.updated_at,
            },
        ]
    }
    assert delete_response.status_code == 204
    assert bindings.get_chat_binding("aiocqhttp", "qq", "12345", "delete") is None
    assert bindings.get_chat_binding("aiocqhttp", "qq", "12345", "keep") is not None
