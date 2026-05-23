from smarter_rp.session_state import SessionStateService
from smarter_rp.storage import Storage


def test_session_defaults_to_enabled(tmp_path):
    storage = Storage(tmp_path / "state.db")
    storage.initialize()
    service = SessionStateService(storage, default_enabled=True)

    assert service.is_enabled("session-1") is True


def test_session_defaults_to_disabled_when_configured(tmp_path):
    storage = Storage(tmp_path / "state.db")
    storage.initialize()
    service = SessionStateService(storage, default_enabled=False)

    assert service.is_enabled("session-1") is False


def test_disable_and_enable_session(tmp_path):
    storage = Storage(tmp_path / "state.db")
    storage.initialize()
    service = SessionStateService(storage, default_enabled=True)

    service.disable("session-1")
    assert service.is_enabled("session-1") is False

    service.enable("session-1")
    assert service.is_enabled("session-1") is True
