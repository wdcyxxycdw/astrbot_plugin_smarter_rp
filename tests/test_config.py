import pytest

from smarter_rp.config import SmarterRpConfig


def test_default_rewrite_and_accounts_enabled():
    config = SmarterRpConfig.default()

    assert config.rewrite["enabled_by_default"] is True
    assert config.accounts["default_enabled"] is True


def test_default_webui_binds_all_interfaces_with_generated_token_placeholder():
    config = SmarterRpConfig.default()

    assert config.webui["enabled"] is True
    assert config.webui["host"] == "0.0.0.0"
    assert config.webui["port"] == 0
    assert config.webui["token"] is None


def test_merge_overrides_nested_values_without_losing_defaults():
    config = SmarterRpConfig.from_mapping({
        "webui": {"port": 8848},
        "memory": {"every_turns": 3},
    })

    assert config.webui["host"] == "0.0.0.0"
    assert config.webui["port"] == 8848
    assert config.memory["auto_enabled"] is True
    assert config.memory["every_turns"] == 3


def test_rejects_non_mapping_known_top_level_sections():
    with pytest.raises(ValueError, match="webui.*mapping"):
        SmarterRpConfig.from_mapping({"webui": None})

    with pytest.raises(ValueError, match="prompt.*mapping"):
        SmarterRpConfig.from_mapping({"prompt": "bad"})


def test_rejects_unknown_top_level_sections():
    with pytest.raises(ValueError, match="unknown.*section"):
        SmarterRpConfig.from_mapping({"web_ui": {"port": 8848}})


def test_materialized_webui_config_requires_non_empty_token():
    config = SmarterRpConfig.default()

    with pytest.raises(ValueError, match="token"):
        config.materialized_webui_config("")

    with pytest.raises(ValueError, match="token"):
        config.materialized_webui_config("   ")


def test_materialized_webui_config_returns_copy_with_token():
    config = SmarterRpConfig.default()

    webui = config.materialized_webui_config("secret-token")

    assert webui["token"] == "secret-token"
    assert config.webui["token"] is None


def test_default_config_instances_are_isolated():
    first = SmarterRpConfig.default()
    first.webui["port"] = 9999

    second = SmarterRpConfig.default()

    assert second.webui["port"] == 0


def test_to_dict_returns_isolated_copy():
    config = SmarterRpConfig.default()
    data = config.to_dict()

    data["webui"]["port"] = 9999

    assert config.webui["port"] == 0
