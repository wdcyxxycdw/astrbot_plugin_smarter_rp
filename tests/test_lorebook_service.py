from pathlib import Path

import pytest

from smarter_rp.models import Lorebook, LorebookEntry
from smarter_rp.services.account_service import AccountIdentity, AccountService
from smarter_rp.services.lorebook_service import LorebookService
from smarter_rp.services.session_service import SessionService
from smarter_rp.storage import Storage


def make_services(tmp_path: Path):
    storage = Storage(tmp_path / "smarter_rp.db")
    storage.initialize()
    return storage, LorebookService(storage), AccountService(storage), SessionService(storage)


def test_lorebook_crud_round_trips_global_and_session_scope(tmp_path: Path):
    _, lorebooks, _, _ = make_services(tmp_path)
    global_book = lorebooks.create_lorebook(
        Lorebook(id="", name="World", description="Shared", scope="global")
    )
    session_book = lorebooks.create_lorebook(
        Lorebook(id="", name="Scene", description="Local", scope="session", session_id="session_1")
    )

    assert global_book.id.startswith("lorebook_")
    assert session_book.session_id == "session_1"
    assert [book.id for book in lorebooks.list_lorebooks()] == [global_book.id, session_book.id]

    updated = lorebooks.update_lorebook(global_book.id, name="World Prime", metadata={"tag": "core"})
    assert updated.name == "World Prime"
    assert updated.metadata == {"tag": "core"}
    assert lorebooks.get_lorebook(global_book.id) == updated

    lorebooks.delete_lorebook(global_book.id)
    assert lorebooks.get_lorebook(global_book.id) is None


def test_lorebook_scope_validation(tmp_path: Path):
    _, lorebooks, _, _ = make_services(tmp_path)

    with pytest.raises(ValueError):
        lorebooks.create_lorebook(Lorebook(id="", name="Bad", scope="bad"))
    with pytest.raises(ValueError):
        lorebooks.create_lorebook(Lorebook(id="", name="Missing Session", scope="session"))

    book = lorebooks.create_lorebook(Lorebook(id="", name="World", scope="global"))
    with pytest.raises(ValueError):
        lorebooks.update_lorebook(book.id, id="changed")
    with pytest.raises(ValueError):
        lorebooks.update_lorebook(book.id, created_at=1)
    with pytest.raises(KeyError):
        lorebooks.update_lorebook("lorebook_missing", name="Missing")


def test_entry_crud_round_trips_rules(tmp_path: Path):
    _, lorebooks, _, _ = make_services(tmp_path)
    book = lorebooks.create_lorebook(Lorebook(id="", name="World", scope="global"))
    entry = lorebooks.create_entry(
        LorebookEntry(
            id="",
            lorebook_id=book.id,
            title="Dragon",
            content="The dragon sleeps under the city.",
            keys=["dragon"],
            secondary_keys=["city"],
            selective=True,
            regex=False,
            case_sensitive=False,
            position="before_history",
            depth=3,
            priority=10,
            order=2,
            probability=0.75,
            cooldown_turns=1,
            sticky_turns=2,
            recursive=True,
            group="myth",
            character_filter=["character_alice"],
            max_injections_per_chat=3,
            metadata={"source": "test"},
        )
    )

    loaded = lorebooks.get_entry(entry.id)
    assert entry.id.startswith("entry_")
    assert loaded == entry
    assert lorebooks.list_entries(book.id) == [entry]

    updated = lorebooks.update_entry(entry.id, enabled=False, keys=["wyrm"])
    assert updated.enabled is False
    assert updated.keys == ["wyrm"]

    with pytest.raises(ValueError):
        lorebooks.update_entry(entry.id, id="changed")
    with pytest.raises(ValueError):
        lorebooks.update_entry(entry.id, probability=1.5)
    with pytest.raises(ValueError):
        lorebooks.create_entry(
            LorebookEntry(id="", lorebook_id=book.id, title="Bad", content="Bad", position="bad")
        )
    with pytest.raises(KeyError):
        lorebooks.update_entry("entry_missing", title="Missing")
    with pytest.raises(KeyError):
        lorebooks.create_entry(
            LorebookEntry(id="", lorebook_id="lorebook_missing", title="Orphan", content="Orphan")
        )
    with pytest.raises(ValueError):
        lorebooks.update_entry(entry.id, lorebook_id="lorebook_missing")
    assert lorebooks.get_entry(entry.id).lorebook_id == book.id
    assert lorebooks.list_entries(book.id) == [lorebooks.get_entry(entry.id)]
    assert lorebooks.list_entries("lorebook_missing") == []

    lorebooks.delete_entry(entry.id)
    assert lorebooks.get_entry(entry.id) is None


def test_lorebook_assignment_helpers_update_account_and_session(tmp_path: Path):
    _, lorebooks, accounts, sessions = make_services(tmp_path)
    account = accounts.get_or_create(AccountIdentity("adapter", "platform", "bot", "Bot"))
    session = sessions.get_or_create("origin", account.id)
    book = lorebooks.create_lorebook(Lorebook(id="", name="World", scope="global"))

    lorebooks.set_account_lorebooks(account.id, [book.id])
    lorebooks.set_session_lorebooks(session.id, [book.id])

    assert accounts.get_by_id(account.id).default_lorebook_ids == [book.id]
    assert sessions.get_by_id(session.id).active_lorebook_ids == [book.id]


def test_export_and_import_plugin_format(tmp_path: Path):
    _, lorebooks, _, _ = make_services(tmp_path)
    book = lorebooks.create_lorebook(
        Lorebook(id="", name="World", scope="global", metadata={"format": "plugin"})
    )
    lorebooks.create_entry(
        LorebookEntry(id="", lorebook_id=book.id, title="Gate", content="The gate is locked.", keys=["gate"])
    )

    exported = lorebooks.export_lorebook(book.id)
    imported = lorebooks.import_lorebook(exported)

    assert exported["format"] == "smarter_rp_lorebook_v1"
    assert imported.name == "World"
    assert imported.id != book.id
    imported_entries = lorebooks.list_entries(imported.id)
    assert len(imported_entries) == 1
    assert imported_entries[0].id != exported["entries"][0]["id"]
    assert imported_entries[0].keys == ["gate"]

    silly_book = lorebooks.import_lorebook(
        {
            "name": "Silly World",
            "data": {
                "entries": {
                    "0": {
                        "comment": "Castle",
                        "content": "Castle lore",
                        "key": ["castle"],
                        "keysecondary": ["king"],
                        "selective": True,
                        "disable": False,
                        "constant": False,
                        "position": "before_history",
                        "order": 4,
                        "probability": 50,
                    }
                }
            },
        }
    )

    assert silly_book.name == "Silly World"
    silly_entries = lorebooks.list_entries(silly_book.id)
    assert len(silly_entries) == 1
    assert silly_entries[0].title == "Castle"
    assert silly_entries[0].keys == ["castle"]
    assert silly_entries[0].secondary_keys == ["king"]
    assert silly_entries[0].probability == 0.5

    with pytest.raises(KeyError):
        lorebooks.export_lorebook("lorebook_missing")


def test_import_lorebook_with_invalid_entry_leaves_no_partial_data(tmp_path: Path):
    _, lorebooks, _, _ = make_services(tmp_path)

    with pytest.raises(ValueError):
        lorebooks.import_lorebook(
            {
                "format": "smarter_rp_lorebook_v1",
                "lorebook": {"name": "Broken World", "scope": "global"},
                "entries": [
                    {"title": "Valid", "content": "Valid lore", "probability": 1.0},
                    {"title": "Invalid", "content": "Invalid lore", "probability": 1.5},
                ],
            }
        )

    assert lorebooks.list_lorebooks() == []
