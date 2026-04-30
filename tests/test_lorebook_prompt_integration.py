from pathlib import Path
from types import SimpleNamespace

from smarter_rp.models import Lorebook, LorebookEntry
from smarter_rp.services.account_service import AccountService
from smarter_rp.services.character_service import CharacterService
from smarter_rp.services.debug_service import DebugService
from smarter_rp.services.history_service import HistoryService
from smarter_rp.services.lorebook_matcher import LorebookMatcher
from smarter_rp.services.lorebook_service import LorebookService
from smarter_rp.services.prompt_builder import PromptBuilder
from smarter_rp.services.request_rewriter import RequestRewriter
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage


def test_rewrite_injects_active_lorebook_before_history_and_saves_hits(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    accounts = AccountService(storage)
    sessions = SessionService(storage)
    history = HistoryService(storage, sessions)
    lorebooks = LorebookService(storage)
    matcher = LorebookMatcher()
    characters = CharacterService(storage)

    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:lorebook",
    )
    profile = accounts.get_or_create(accounts.extract_identity(event))
    session = sessions.get_or_create("origin:lorebook", profile.id)
    book = lorebooks.create_lorebook(Lorebook(id="book_gate", name="Gate Book", scope="global"))
    entry = lorebooks.create_entry(
        LorebookEntry(
            id="entry_gate",
            lorebook_id=book.id,
            title="Gate",
            content="The gate opens only for a named traveler.",
            keys=["gate"],
            position="before_history",
        )
    )
    sessions.update_session_controls(session.id, active_lorebook_ids=[book.id])
    rewriter = RequestRewriter(
        accounts,
        sessions,
        characters,
        PromptBuilder(max_prompt_chars=4000),
        DebugService(storage),
        history,
        lorebooks,
        matcher,
    )
    request = SimpleNamespace(prompt="Open the gate", system_prompt="old", contexts=[])

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert "[Lorebook: before_history]" in request.system_prompt
    assert entry.content in request.system_prompt
    saved_session = sessions.get_by_id(session.id)
    assert saved_session.last_lore_hits
    assert saved_session.last_lore_hits[0]["entry_id"] == entry.id


def test_rewrite_clears_stale_lore_hits_when_no_lorebooks_are_selected(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    accounts = AccountService(storage)
    sessions = SessionService(storage)
    history = HistoryService(storage, sessions)
    characters = CharacterService(storage)
    lorebooks = LorebookService(storage)

    event = SimpleNamespace(
        adapter_name="adapter",
        platform="platform",
        account_id="bot",
        unified_msg_origin="origin:no-lorebook",
    )
    profile = accounts.get_or_create(accounts.extract_identity(event))
    session = sessions.get_or_create("origin:no-lorebook", profile.id)
    session.last_lore_hits = [{"entry_id": "entry_old", "reason": "keyword"}]
    sessions.save_session_state(session)
    rewriter = RequestRewriter(
        accounts,
        sessions,
        characters,
        PromptBuilder(max_prompt_chars=4000),
        DebugService(storage),
        history,
        lorebooks,
        LorebookMatcher(),
    )
    request = SimpleNamespace(prompt="No lore here", system_prompt="old", contexts=[])

    result = rewriter.rewrite(event, request)

    assert result.rewritten is True
    assert sessions.get_by_id(session.id).last_lore_hits == []
