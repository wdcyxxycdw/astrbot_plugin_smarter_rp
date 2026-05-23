import asyncio

import pytest

from smarter_rp.storage import Storage
from smarter_rp.tavern_bindings import TavernBindingService
from smarter_rp.tavern_worker import (
    EmptyTavernReplyError,
    MissingTavernBindingError,
    TavernWorker,
    make_chat_name,
)


def run(coro):
    return asyncio.run(coro)


def make_bindings(tmp_path):
    storage = Storage(tmp_path / "worker.db")
    storage.initialize()
    return TavernBindingService(storage)


def astrbot_payload(session_id="session-e2e-001", text="hello"):
    return {
        "adapter": {"name": "aiocqhttp", "platform": "qq", "accountId": "account-1"},
        "session": {"id": session_id, "displayName": "测试群"},
        "user": {"id": "user-1", "name": "Alice"},
        "message": {"text": text},
    }


class FakeTavernClient:
    def __init__(self, replies=None, *, delay=0, initial_save_delay=0):
        self.characters = [{"name": "角色一", "avatar": "char-1.png"}]
        self.chats = {}
        self.saved = []
        self.generate_payloads = []
        self.replies = list(replies or ["reply"])
        self.delay = delay
        self.initial_save_delay = initial_save_delay
        self.active_generates = 0
        self.max_active_generates = 0

    async def list_characters(self):
        return self.characters

    async def get_chat(self, avatar_url, file_name):
        chat = self.chats.get((avatar_url, file_name))
        return None if chat is None else list(chat)

    async def save_chat(self, avatar_url, file_name, chat, *, force=False):
        if not force and self.initial_save_delay:
            await asyncio.sleep(self.initial_save_delay)
        self.saved.append((avatar_url, file_name, list(chat), force))
        self.chats[(avatar_url, file_name)] = list(chat)

    async def generate(self, payload):
        self.generate_payloads.append(payload)
        self.active_generates += 1
        self.max_active_generates = max(self.max_active_generates, self.active_generates)
        if self.delay:
            await asyncio.sleep(self.delay)
        self.active_generates -= 1
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def test_missing_account_binding_raises_typed_error(tmp_path):
    bindings = make_bindings(tmp_path)
    worker = TavernWorker(FakeTavernClient(), bindings)

    with pytest.raises(MissingTavernBindingError):
        run(worker.generate(astrbot_payload()))


def test_first_message_creates_chat_binding_with_astrbot_chat_name(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    client = FakeTavernClient(replies=["你好"])
    worker = TavernWorker(client, bindings)

    reply = run(worker.generate(astrbot_payload(session_id="session-e2e-001")))

    assert reply == "你好"
    chat_binding = bindings.get_chat_binding("aiocqhttp", "qq", "account-1", "session-e2e-001")
    assert chat_binding is not None
    assert chat_binding.chat_id == "[AstrBot] qq-测试群-sessio-001"
    assert make_chat_name("qq", "测试群", "session-e2e-001") == chat_binding.chat_id
    assert client.saved[0] == (
        "char-1.png",
        "[AstrBot] qq-测试群-sessio-001",
        [{"user_name": "角色一", "character_name": "角色一"}],
        False,
    )
    assert client.saved[-1][2][-2:] == [
        {"name": "Alice", "is_user": True, "mes": "hello"},
        {"name": "角色一", "is_user": False, "mes": "你好"},
    ]
    assert client.generate_payloads[0]["character"]["name"] == "角色一"
    assert client.generate_payloads[0]["chat"]["id"] == "[AstrBot] qq-测试群-sessio-001"
    assert client.generate_payloads[0]["message"]["text"] == "hello"


def test_later_messages_reuse_chat_binding_without_recreating_chat(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    bindings.set_chat_binding("aiocqhttp", "qq", "account-1", "session-1", "0", "existing-chat")
    client = FakeTavernClient(replies=["second reply"])
    client.chats[("char-1.png", "existing-chat")] = [
        {"user_name": "角色一", "character_name": "角色一"},
        {"name": "Alice", "is_user": True, "mes": "first"},
        {"name": "角色一", "is_user": False, "mes": "first reply"},
    ]
    worker = TavernWorker(client, bindings)

    reply = run(worker.generate(astrbot_payload(session_id="session-1", text="second")))

    assert reply == "second reply"
    assert len(client.saved) == 2
    assert all(save[3] is True for save in client.saved)
    assert client.saved[0][1] == "existing-chat"
    assert client.saved[-1][2][-2:] == [
        {"name": "Alice", "is_user": True, "mes": "second"},
        {"name": "角色一", "is_user": False, "mes": "second reply"},
    ]


def test_same_session_generation_is_serialized(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    client = FakeTavernClient(replies=["r1", "r2"], delay=0.02)
    worker = TavernWorker(client, bindings)

    async def scenario():
        await asyncio.gather(
            worker.generate(astrbot_payload(session_id="same-session", text="one")),
            worker.generate(astrbot_payload(session_id="same-session", text="two")),
        )

    run(scenario())

    assert client.max_active_generates == 1
    assert len(bindings.list_chat_bindings()) == 1
    binding = bindings.get_chat_binding("aiocqhttp", "qq", "account-1", "same-session")
    assert binding is not None
    assert client.chats[("char-1.png", binding.chat_id)] == [
        {"user_name": "角色一", "character_name": "角色一"},
        {"name": "Alice", "is_user": True, "mes": "one"},
        {"name": "角色一", "is_user": False, "mes": "r1"},
        {"name": "Alice", "is_user": True, "mes": "two"},
        {"name": "角色一", "is_user": False, "mes": "r2"},
    ]


def test_different_sessions_can_generate_in_parallel(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    client = FakeTavernClient(replies=["r1", "r2"], delay=0.02)
    worker = TavernWorker(client, bindings)

    async def scenario():
        await asyncio.gather(
            worker.generate(astrbot_payload(session_id="session-a", text="one")),
            worker.generate(astrbot_payload(session_id="session-b", text="two")),
        )

    run(scenario())

    assert client.max_active_generates == 2
    assert len(bindings.list_chat_bindings()) == 2
    first = bindings.get_chat_binding("aiocqhttp", "qq", "account-1", "session-a")
    second = bindings.get_chat_binding("aiocqhttp", "qq", "account-1", "session-b")
    assert first is not None
    assert second is not None
    assert client.chats[("char-1.png", first.chat_id)][-2:] == [
        {"name": "Alice", "is_user": True, "mes": "one"},
        {"name": "角色一", "is_user": False, "mes": "r1"},
    ]
    assert client.chats[("char-1.png", second.chat_id)][-2:] == [
        {"name": "Alice", "is_user": True, "mes": "two"},
        {"name": "角色一", "is_user": False, "mes": "r2"},
    ]


def test_empty_reply_raises_typed_error(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    worker = TavernWorker(FakeTavernClient(replies=["   "]), bindings)

    with pytest.raises(EmptyTavernReplyError):
        run(worker.generate(astrbot_payload()))


def test_client_generation_error_propagates(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    worker = TavernWorker(FakeTavernClient(replies=[RuntimeError("generate failed")]), bindings)

    with pytest.raises(RuntimeError, match="generate failed"):
        run(worker.generate(astrbot_payload()))


def test_different_sessions_have_isolated_chat_bindings(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    client = FakeTavernClient(replies=["reply a", "reply b"])
    worker = TavernWorker(client, bindings)

    run(worker.generate(astrbot_payload(session_id="session-e2e-001", text="a")))
    run(worker.generate(astrbot_payload(session_id="session-e2e-002", text="b")))

    first = bindings.get_chat_binding("aiocqhttp", "qq", "account-1", "session-e2e-001")
    second = bindings.get_chat_binding("aiocqhttp", "qq", "account-1", "session-e2e-002")
    assert first is not None
    assert second is not None
    assert first.chat_id == "[AstrBot] qq-测试群-sessio-001"
    assert second.chat_id == "[AstrBot] qq-测试群-sessio-002"
    assert first.chat_id != second.chat_id


def test_colliding_short_chat_names_get_stable_unique_chat_ids(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    client = FakeTavernClient(replies=["reply a", "reply b"])
    worker = TavernWorker(client, bindings)
    first_session = "abcdef-middle-one-1234"
    second_session = "abcdef-middle-two-1234"

    assert make_chat_name("qq", "测试群", first_session) == "[AstrBot] qq-测试群-abcdef1234"
    assert make_chat_name("qq", "测试群", second_session) == "[AstrBot] qq-测试群-abcdef1234"

    run(worker.generate(astrbot_payload(session_id=first_session, text="a")))
    run(worker.generate(astrbot_payload(session_id=second_session, text="b")))

    first = bindings.get_chat_binding("aiocqhttp", "qq", "account-1", first_session)
    second = bindings.get_chat_binding("aiocqhttp", "qq", "account-1", second_session)
    assert first is not None
    assert second is not None
    assert first.chat_id == "[AstrBot] qq-测试群-abcdef1234"
    assert second.chat_id.startswith("[AstrBot] qq-测试群-abcdef1234-")
    assert first.chat_id != second.chat_id


def test_concurrent_colliding_short_chat_names_get_unique_isolated_chats(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    client = FakeTavernClient(replies=["reply a", "reply b"], initial_save_delay=0.02)
    worker = TavernWorker(client, bindings)
    first_session = "abcdef-middle-one-1234"
    second_session = "abcdef-middle-two-1234"

    assert make_chat_name("qq", "测试群", first_session) == make_chat_name("qq", "测试群", second_session)

    async def scenario():
        await asyncio.gather(
            worker.generate(astrbot_payload(session_id=first_session, text="a")),
            worker.generate(astrbot_payload(session_id=second_session, text="b")),
        )

    run(scenario())

    first = bindings.get_chat_binding("aiocqhttp", "qq", "account-1", first_session)
    second = bindings.get_chat_binding("aiocqhttp", "qq", "account-1", second_session)
    assert first is not None
    assert second is not None
    assert first.chat_id != second.chat_id
    assert client.chats[("char-1.png", first.chat_id)][-2:] == [
        {"name": "Alice", "is_user": True, "mes": "a"},
        {"name": "角色一", "is_user": False, "mes": "reply a"},
    ]
    assert client.chats[("char-1.png", second.chat_id)][-2:] == [
        {"name": "Alice", "is_user": True, "mes": "b"},
        {"name": "角色一", "is_user": False, "mes": "reply b"},
    ]


def test_locks_are_removed_after_completed_generations(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    client = FakeTavernClient(replies=["r1", "r2", "r3"])
    worker = TavernWorker(client, bindings)

    run(worker.generate(astrbot_payload(session_id="session-lock-1", text="one")))
    run(worker.generate(astrbot_payload(session_id="session-lock-2", text="two")))
    run(worker.generate(astrbot_payload(session_id="session-lock-3", text="three")))

    assert worker._locks == {}


def test_existing_binding_with_missing_chat_starts_with_header(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    bindings.set_chat_binding("aiocqhttp", "qq", "account-1", "session-1", "0", "missing-chat")
    client = FakeTavernClient(replies=["reply"])
    worker = TavernWorker(client, bindings)

    run(worker.generate(astrbot_payload(session_id="session-1", text="hello")))

    assert client.saved[0] == (
        "char-1.png",
        "missing-chat",
        [
            {"user_name": "角色一", "character_name": "角色一"},
            {"name": "Alice", "is_user": True, "mes": "hello"},
        ],
        True,
    )
    assert client.saved[-1][2][0] == {"user_name": "角色一", "character_name": "角色一"}


def test_existing_binding_with_empty_chat_starts_with_header(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "0")
    bindings.set_chat_binding("aiocqhttp", "qq", "account-1", "session-1", "0", "empty-chat")
    client = FakeTavernClient(replies=["reply"])
    client.chats[("char-1.png", "empty-chat")] = []
    worker = TavernWorker(client, bindings)

    run(worker.generate(astrbot_payload(session_id="session-1", text="hello")))

    assert client.saved[0][2] == [
        {"user_name": "角色一", "character_name": "角色一"},
        {"name": "Alice", "is_user": True, "mes": "hello"},
    ]


def test_existing_chat_binding_for_different_character_creates_new_chat(tmp_path):
    bindings = make_bindings(tmp_path)
    bindings.set_account_binding("aiocqhttp", "qq", "account-1", "1")
    bindings.set_chat_binding("aiocqhttp", "qq", "account-1", "session-1", "0", "old-chat")
    client = FakeTavernClient(replies=["new reply"])
    client.characters.append({"name": "角色二", "avatar": "char-2.png"})
    client.chats[("char-1.png", "old-chat")] = [
        {"user_name": "角色一", "character_name": "角色一"},
        {"name": "Alice", "is_user": True, "mes": "old"},
    ]
    worker = TavernWorker(client, bindings)

    run(worker.generate(astrbot_payload(session_id="session-1", text="new")))

    updated = bindings.get_chat_binding("aiocqhttp", "qq", "account-1", "session-1")
    assert updated is not None
    assert updated.character_id == "1"
    assert updated.chat_id == "[AstrBot] qq-测试群-session-1"
    assert updated.chat_id != "old-chat"
    assert client.saved[0] == (
        "char-2.png",
        "[AstrBot] qq-测试群-session-1",
        [{"user_name": "角色二", "character_name": "角色二"}],
        False,
    )
