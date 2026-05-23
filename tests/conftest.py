import sys
import types
from types import SimpleNamespace

import pytest


@pytest.fixture()
def astrbot_stubs(monkeypatch):
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    event_module = types.ModuleType("astrbot.api.event")
    star_module = types.ModuleType("astrbot.api.star")

    command_calls = []
    message_decorator_calls = []
    event_message_type = SimpleNamespace(ALL="all")

    def fake_command(*args, **kwargs):
        command_calls.append((args, kwargs))
        return lambda func: func

    def fake_event_message_type(*args, **kwargs):
        message_decorator_calls.append((args, kwargs))
        return lambda func: func

    filter_module = SimpleNamespace(
        command=fake_command,
        event_message_type=fake_event_message_type,
        EventMessageType=event_message_type,
    )

    class FakeStar:
        def __init__(self, context):
            self.context = context

    def fake_register(*_args, **_kwargs):
        return lambda cls: cls

    event_module.filter = filter_module
    star_module.Context = object
    star_module.Star = FakeStar
    star_module.register = fake_register

    monkeypatch.setitem(sys.modules, "astrbot", astrbot_module)
    monkeypatch.setitem(sys.modules, "astrbot.api", api_module)
    monkeypatch.setitem(sys.modules, "astrbot.api.event", event_module)
    monkeypatch.setitem(sys.modules, "astrbot.api.star", star_module)

    return SimpleNamespace(
        command_calls=command_calls,
        message_decorator_calls=message_decorator_calls,
        event_message_type=event_message_type,
    )
