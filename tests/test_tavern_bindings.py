from smarter_rp.storage import Storage
from smarter_rp.tavern_bindings import TavernBindingService


def make_service(tmp_path):
    storage = Storage(tmp_path / "bindings.db")
    storage.initialize()
    return TavernBindingService(storage)


def test_account_binding_crud_and_update(tmp_path):
    service = make_service(tmp_path)

    created = service.set_account_binding("  aiocqhttp  ", " qq ", 12345, "char-a")

    assert created.adapter == "aiocqhttp"
    assert created.platform == "qq"
    assert created.account_id == "12345"
    assert created.character_id == "char-a"
    assert created.created_at == created.updated_at
    assert service.get_account_binding("aiocqhttp", "qq", "12345") == created
    assert service.list_account_bindings() == [created]

    updated = service.set_account_binding("aiocqhttp", "qq", "12345", "char-b")

    assert updated.character_id == "char-b"
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert service.get_account_binding("aiocqhttp", "qq", "12345") == updated
    assert service.list_account_bindings() == [updated]

    service.delete_account_binding("aiocqhttp", "qq", "12345")

    assert service.get_account_binding("aiocqhttp", "qq", "12345") is None
    assert service.list_account_bindings() == []


def test_chat_binding_crud_and_update(tmp_path):
    service = make_service(tmp_path)

    created = service.set_chat_binding("  aiocqhttp  ", " qq ", 12345, " session-1 ", "char-a", "chat-a")

    assert created.adapter == "aiocqhttp"
    assert created.platform == "qq"
    assert created.account_id == "12345"
    assert created.session_id == "session-1"
    assert created.character_id == "char-a"
    assert created.chat_id == "chat-a"
    assert created.created_at == created.updated_at
    assert service.get_chat_binding("aiocqhttp", "qq", "12345", "session-1") == created
    assert service.list_chat_bindings() == [created]

    updated = service.set_chat_binding("aiocqhttp", "qq", "12345", "session-1", "char-b", "chat-b")

    assert updated.character_id == "char-b"
    assert updated.chat_id == "chat-b"
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert service.get_chat_binding("aiocqhttp", "qq", "12345", "session-1") == updated
    assert service.list_chat_bindings() == [updated]

    service.delete_chat_binding("aiocqhttp", "qq", "12345", "session-1")

    assert service.get_chat_binding("aiocqhttp", "qq", "12345", "session-1") is None
    assert service.list_chat_bindings() == []


def test_chat_bindings_for_different_sessions_are_isolated(tmp_path):
    service = make_service(tmp_path)

    first = service.set_chat_binding("aiocqhttp", "qq", "12345", "session-1", "char-a", "chat-a")
    second = service.set_chat_binding("aiocqhttp", "qq", "12345", "session-2", "char-b", "chat-b")

    assert service.get_chat_binding("aiocqhttp", "qq", "12345", "session-1") == first
    assert service.get_chat_binding("aiocqhttp", "qq", "12345", "session-2") == second
    assert service.list_chat_bindings() == [first, second]


def test_different_adapter_and_account_bindings_do_not_collide(tmp_path):
    service = make_service(tmp_path)

    first_account = service.set_account_binding("aiocqhttp", "qq", "12345", "char-a")
    second_account = service.set_account_binding("telegram", "telegram", "12345", "char-b")
    third_account = service.set_account_binding("aiocqhttp", "qq", "67890", "char-c")
    first_chat = service.set_chat_binding("aiocqhttp", "qq", "12345", "session-1", "char-a", "chat-a")
    second_chat = service.set_chat_binding("telegram", "telegram", "12345", "session-1", "char-b", "chat-b")
    third_chat = service.set_chat_binding("aiocqhttp", "qq", "67890", "session-1", "char-c", "chat-c")

    assert service.get_account_binding("aiocqhttp", "qq", "12345") == first_account
    assert service.get_account_binding("telegram", "telegram", "12345") == second_account
    assert service.get_account_binding("aiocqhttp", "qq", "67890") == third_account
    assert service.list_account_bindings() == [first_account, third_account, second_account]
    assert service.get_chat_binding("aiocqhttp", "qq", "12345", "session-1") == first_chat
    assert service.get_chat_binding("telegram", "telegram", "12345", "session-1") == second_chat
    assert service.get_chat_binding("aiocqhttp", "qq", "67890", "session-1") == third_chat
    assert service.list_chat_bindings() == [first_chat, third_chat, second_chat]


def test_updating_account_binding_does_not_mutate_existing_chat_binding(tmp_path):
    service = make_service(tmp_path)

    service.set_account_binding("aiocqhttp", "qq", "12345", "char-a")
    chat = service.set_chat_binding("aiocqhttp", "qq", "12345", "session-1", "char-a", "chat-a")

    service.set_account_binding("aiocqhttp", "qq", "12345", "char-b")

    assert service.get_chat_binding("aiocqhttp", "qq", "12345", "session-1") == chat
