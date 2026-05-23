import pytest

from smarter_rp.config import SmarterRpConfig


def test_default_config_uses_managed_tavern_and_local_webui():
    config = SmarterRpConfig.default()

    assert config.bridge == {
        "mode": "legacy_ws",
        "host": "127.0.0.1",
        "port": 8008,
        "timeout_seconds": 120,
    }
    assert config.tavern == {
        "mode": "managed",
        "host": "127.0.0.1",
        "port": 8001,
        "base_url": "http://127.0.0.1:8001",
        "install_dir": "~/.local/share/astrbot-smarter-rp/SillyTavern",
        "auto_start": True,
        "startup_timeout_seconds": 60,
        "request_timeout_seconds": 120,
        "auth": {"enabled": False, "username": "", "password": "", "token": ""},
    }
    assert config.webui == {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8010,
        "token": "",
    }
    assert config.behavior["default_enabled"] is True
    assert config.behavior["fallback_message"] == "RP 后端暂时不可用。"
    assert config.storage["backend"] == "sqlite"


def test_config_merges_bridge_override():
    config = SmarterRpConfig.from_mapping({"bridge": {"port": 8765, "timeout_seconds": 5}})

    assert config.bridge["mode"] == "legacy_ws"
    assert config.bridge["host"] == "127.0.0.1"
    assert config.bridge["port"] == 8765
    assert config.bridge["timeout_seconds"] == 5


def test_config_rejects_public_bridge_host_without_auth():
    with pytest.raises(ValueError, match="bridge.host must remain local"):
        SmarterRpConfig.from_mapping({"bridge": {"host": "0.0.0.0"}})


def test_config_rejects_public_tavern_host():
    with pytest.raises(ValueError, match="tavern.host must remain local"):
        SmarterRpConfig.from_mapping({"tavern": {"host": "0.0.0.0"}})


def test_config_rejects_public_tavern_base_url():
    with pytest.raises(ValueError, match="tavern.base_url must remain local"):
        SmarterRpConfig.from_mapping({"tavern": {"base_url": "http://192.168.1.10:8001"}})


def test_config_rejects_public_webui_host():
    with pytest.raises(ValueError, match="webui.host must remain local"):
        SmarterRpConfig.from_mapping({"webui": {"host": "0.0.0.0"}})


def test_config_merges_tavern_and_webui_overrides():
    config = SmarterRpConfig.from_mapping({
        "tavern": {"port": 8020, "base_url": "http://localhost:8020", "auth": {"enabled": True, "token": "secret"}},
        "webui": {"port": 8030, "token": "web-secret"},
    })

    assert config.tavern["port"] == 8020
    assert config.tavern["base_url"] == "http://localhost:8020"
    assert config.tavern["auth"] == {"enabled": True, "username": "", "password": "", "token": "secret"}
    assert config.webui["port"] == 8030
    assert config.webui["token"] == "web-secret"


def test_config_rejects_unknown_section():
    with pytest.raises(ValueError, match="unknown config section"):
        SmarterRpConfig.from_mapping({"rewrite": {"enabled_by_default": True}})


def test_config_rejects_non_mapping_section():
    with pytest.raises(ValueError, match="config section bridge must be a mapping"):
        SmarterRpConfig.from_mapping({"bridge": "bad"})
