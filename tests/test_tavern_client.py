import asyncio
import json

import httpx
import pytest

from smarter_rp.tavern_client import (
    SillyTavernClient,
    SillyTavernGenerationError,
    SillyTavernRequestError,
)


def run(coro):
    return asyncio.run(coro)


async def collect_requests(responses, action):
    requests = []

    def handler(request):
        requests.append(request)
        response = responses.pop(0)
        return response(request) if callable(response) else response

    transport = httpx.MockTransport(handler)
    async with SillyTavernClient(
        "http://127.0.0.1:8001",
        timeout_seconds=5,
        auth={"enabled": True, "token": "secret-token"},
        transport=transport,
    ) as client:
        result = await action(client)
    return result, requests


def json_body(request):
    return json.loads(request.content.decode() or "{}")


def test_client_uses_confirmed_endpoint_methods_and_bodies():
    async def scenario(client):
        return {
            "health": await client.health(),
            "settings": await client.get_settings(),
            "save_settings": await client.save_settings({"setting": "value"}),
            "characters": await client.list_characters(),
            "import_character": await client.import_character("Alice.json", b'{"name":"Alice"}', file_type="json", preserved_name="Alice"),
            "worldbooks": await client.list_worldbooks(),
            "import_worldbook": await client.import_worldbook("Lore.json", {"entries": {}}),
            "chat": await client.get_chat("Alice.png", "chat-1"),
            "save_chat": await client.save_chat("Alice.png", "chat-1", [{"mes": "hi"}], force=True),
            "generate": await client.generate({"messages": [{"role": "user", "content": "hi"}]}),
        }

    responses = [
        httpx.Response(200, text="ok"),
        httpx.Response(200, json={"settings": True}),
        httpx.Response(200, json={"result": "ok"}),
        httpx.Response(200, json=[{"name": "Alice"}]),
        httpx.Response(200, json={"file_name": "Alice.png"}),
        httpx.Response(200, json=[{"name": "Lore", "file_id": "Lore"}]),
        httpx.Response(200, json={"name": "Lore"}),
        httpx.Response(200, json=[{"mes": "hi"}]),
        httpx.Response(200, json={"ok": True}),
        httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]}),
    ]

    result, requests = run(collect_requests(responses, scenario))

    assert result["health"] is True
    assert result["generate"] == "hello"
    assert [(r.method, r.url.path) for r in requests] == [
        ("GET", "/"),
        ("POST", "/api/settings/get"),
        ("POST", "/api/settings/save"),
        ("POST", "/api/characters/all"),
        ("POST", "/api/characters/import"),
        ("POST", "/api/worldinfo/list"),
        ("POST", "/api/worldinfo/import"),
        ("POST", "/api/chats/get"),
        ("POST", "/api/chats/save"),
        ("POST", "/api/backends/chat-completions/generate"),
    ]
    assert json_body(requests[2]) == {"setting": "value"}
    assert requests[4].headers["content-type"].startswith("multipart/form-data")
    assert b'name="file_type"' in requests[4].content
    assert b'name="avatar"' in requests[4].content
    assert requests[6].headers["content-type"].startswith("multipart/form-data")
    assert b'name="avatar"' in requests[6].content
    assert json_body(requests[7]) == {"avatar_url": "Alice.png", "file_name": "chat-1"}
    assert json_body(requests[8]) == {
        "avatar_url": "Alice.png",
        "file_name": "chat-1",
        "chat": [{"mes": "hi"}],
        "force": True,
    }
    assert json_body(requests[9]) == {"messages": [{"role": "user", "content": "hi"}]}
    assert all(r.headers.get("authorization") == "Bearer secret-token" for r in requests)


def test_non_2xx_raises_typed_error_and_sanitizes_sensitive_values():
    async def scenario(client):
        with pytest.raises(SillyTavernRequestError) as error_info:
            await client.get_settings()
        return str(error_info.value)

    body = {
        "error": "bad token secret-token password hunter2 api_key abc Authorization Bearer x Cookie y"
    }
    message, _ = run(collect_requests([httpx.Response(500, json=body)], scenario))

    assert "500" in message
    assert "secret-token" not in message
    assert "hunter2" not in message
    assert "abc" not in message
    assert "Authorization" not in message
    assert "Cookie" not in message
    assert "password" not in message.lower()
    assert "token" not in message.lower()
    assert "key" not in message.lower()


def test_generate_empty_reply_raises_generation_error():
    async def scenario(client):
        with pytest.raises(SillyTavernGenerationError):
            await client.generate({"messages": []})

    run(collect_requests([httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})], scenario))


@pytest.mark.parametrize(
    "response_body",
    [
        {"choices": []},
        {"choices": "unexpected"},
        {"choices": ["unexpected"]},
        {"choices": [None]},
    ],
)
def test_generate_unexpected_choices_shape_raises_generation_error(response_body):
    async def scenario(client):
        with pytest.raises(SillyTavernGenerationError):
            await client.generate({"messages": []})

    run(collect_requests([httpx.Response(200, json=response_body)], scenario))


def test_client_rejects_non_localhost_base_url():
    with pytest.raises(ValueError, match="localhost"):
        SillyTavernClient("http://192.168.1.10:8001", timeout_seconds=5)
