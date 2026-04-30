from pathlib import Path
from types import SimpleNamespace

from smarter_rp.services.account_service import AccountService
from smarter_rp.services.character_service import CharacterService
from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.prompt_builder import PromptBuilder
from smarter_rp.services.request_rewriter import RequestRewriter
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage


def make_rewriter(tmp_path: Path) -> tuple[RequestRewriter, Storage]:
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    rewriter = RequestRewriter(
        accounts=AccountService(storage),
        sessions=SessionService(storage),
        characters=CharacterService(storage),
        prompt_builder=PromptBuilder(max_prompt_chars=4000),
        debug=DebugService(storage),
    )
    return rewriter, storage


def test_rewrite_default_active_session_mutates_prompt(tmp_path: Path):
    rewriter, _ = make_rewriter(tmp_path)
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:1",
    )
    request = SimpleNamespace(
        prompt="Hello",
        system_prompt="old",
        contexts=["old context"],
        tools=[{"name": "transfer_to_agent"}],
        image_urls=["img"],
    )

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert result.reason == "rewritten"
    assert result.account_profile_id is not None
    assert result.session_id is not None
    assert "Smarter RP" in request.system_prompt
    assert request.contexts == []
    assert request.prompt == "Hello"
    assert request.image_urls == ["img"]
    assert request.tools == [{"name": "transfer_to_agent"}]


def test_account_disabled_passes_request_unchanged(tmp_path: Path):
    rewriter, storage = make_rewriter(tmp_path)
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:1",
    )
    profile = AccountService(storage).get_or_create(AccountService(storage).extract_identity(event))
    AccountService(storage).update_profile(profile.id, default_enabled=False)
    request = SimpleNamespace(
        prompt="Hello",
        system_prompt="old",
        contexts=["old context"],
        tools=[{"name": "transfer_to_agent"}],
        image_urls=["img"],
        attachments=["file"],
    )

    result = rewriter.rewrite(event, request)

    assert result.rewritten is False
    assert result.reason == "account_disabled"
    assert result.account_profile_id == profile.id
    assert result.session_id is not None
    assert request.system_prompt == "old"
    assert request.contexts == ["old context"]
    assert request.prompt == "Hello"
    assert request.tools == [{"name": "transfer_to_agent"}]
    assert request.image_urls == ["img"]
    assert request.attachments == ["file"]


def test_session_paused_passes_request_unchanged(tmp_path: Path):
    rewriter, storage = make_rewriter(tmp_path)
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:1",
    )
    profile = AccountService(storage).get_or_create(AccountService(storage).extract_identity(event))
    session = SessionService(storage).get_or_create("origin:1", profile.id)
    SessionService(storage).set_paused(session.id, True)
    request = SimpleNamespace(
        prompt="Hello",
        system_prompt="old",
        contexts=["old context"],
        tools=[{"name": "transfer_to_agent"}],
        image_urls=["img"],
        attachments=["file"],
    )

    result = rewriter.rewrite(event, request)

    assert result.rewritten is False
    assert result.reason == "session_paused"
    assert result.account_profile_id == profile.id
    assert result.session_id == session.id
    assert request.system_prompt == "old"
    assert request.contexts == ["old context"]
    assert request.prompt == "Hello"
    assert request.tools == [{"name": "transfer_to_agent"}]
    assert request.image_urls == ["img"]
    assert request.attachments == ["file"]


def test_rewrite_populates_contexts_from_plugin_history_and_preserves_prompt(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    accounts = AccountService(storage)
    sessions = SessionService(storage)
    history = HistoryService(storage, sessions)
    rewriter = RequestRewriter(
        accounts=accounts,
        sessions=sessions,
        characters=CharacterService(storage),
        prompt_builder=PromptBuilder(max_prompt_chars=4000),
        debug=DebugService(storage),
        history=history,
    )
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:history",
    )
    profile = accounts.get_or_create(accounts.extract_identity(event))
    session = sessions.get_or_create("origin:history", profile.id)
    history.append_message(session.id, role="user", speaker="Hero", content=" Hello ")
    history.append_message(session.id, role="assistant", speaker="Alice", content="Hi back")
    history.append_message(session.id, role="system", speaker="System", content="skip this")
    request = SimpleNamespace(
        prompt="Current prompt",
        system_prompt="old",
        contexts=["old context"],
        tools=[{"name": "tool"}],
        image_urls=["img"],
        attachments=["file"],
    )

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert request.prompt == "Current prompt"
    assert request.contexts == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi back"},
    ]
    assert "Hero: Hello" in request.system_prompt
    assert "Alice: Hi back" in request.system_prompt
    assert "skip this" not in request.system_prompt
    assert request.tools == [{"name": "tool"}]
    assert request.image_urls == ["img"]
    assert request.attachments == ["file"]


def test_rewrite_saves_redacted_debug_snapshots(tmp_path: Path):
    rewriter, storage = make_rewriter(tmp_path)
    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:1",
    )
    request = SimpleNamespace(
        prompt="Hello token=abc123",
        system_prompt="old Authorization: Bearer secret-token",
        contexts=["old context api_key: sk-test-value"],
        tools=[{"name": "transfer_to_agent"}],
        image_urls=["img"],
    )

    result = rewriter.rewrite(event, request)

    snapshots = storage.fetch_all(
        "SELECT type, content FROM debug_snapshots WHERE session_id = ? ORDER BY type",
        (result.session_id,),
    )
    assert {row["type"] for row in snapshots} == {"prompt", "raw_request"}
    combined = "\n".join(row["content"] for row in snapshots)
    assert "abc123" not in combined
    assert "secret-token" not in combined
    assert "sk-test-value" not in combined
    assert "[REDACTED]" in combined
    assert "prompt" in combined
    assert "system_prompt" in combined


def test_rewrite_uses_safe_unknown_origin_fallback(tmp_path: Path):
    rewriter, _ = make_rewriter(tmp_path)
    event = SimpleNamespace(adapter_name="adapter", platform="platform", account_id="bot")
    request = SimpleNamespace(prompt=None, system_prompt="old", contexts=["old context"])

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert result.session_id is not None
    assert request.contexts == []
    assert "Current Input" in request.system_prompt
