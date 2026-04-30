from smarter_rp.models import AccountProfile, Character, RpMessage, RpSession
from smarter_rp.services.prompt_builder import PromptBuilder


def test_prompt_builder_orders_core_blocks():
    builder = PromptBuilder(max_prompt_chars=4000)
    account = AccountProfile("account_1", "adapter", "platform", "bot", prompt_overrides={"persona": "Account persona"})
    character = Character(id="character_1", name="Alice", system_prompt="Character system", description="Desc", personality="Kind")
    session = RpSession("session_1", "origin", "account_1", summary="Summary", state={"location": "Library"})

    prompt = builder.build(account, session, character, current_input="Hello")

    assert prompt.index("[Global RP System Rules]") < prompt.index("[Account/Profile Persona]")
    assert prompt.index("[Account/Profile Persona]") < prompt.index("[Character]")
    assert "Account persona" in prompt
    assert "Character system" in prompt
    assert "Summary" in prompt
    assert "Library" in prompt
    assert "Hello" in prompt


def test_prompt_builder_truncates_to_budget():
    builder = PromptBuilder(max_prompt_chars=120)
    prompt = builder.build(None, RpSession("s", "origin", None), Character(id="c", name="C", description="x" * 1000), "hello")

    assert len(prompt) <= 120
    assert "hello" in prompt


def test_prompt_builder_includes_recent_rp_history():
    builder = PromptBuilder(max_prompt_chars=4000)
    history_messages = [
        RpMessage(id="m1", session_id="s", role="user", speaker="Hero", content=" Hello there "),
        RpMessage(id="m2", session_id="s", role="assistant", speaker="", content="General Kenobi"),
        RpMessage(id="m3", session_id="s", role="system", speaker="Narrator", content="hidden"),
        RpMessage(id="m4", session_id="s", role="user", speaker="Empty", content="   "),
        RpMessage(id="m5", session_id="s", role="user", speaker="Hidden", content="secret", visible=False),
    ]

    prompt = builder.build(
        None,
        RpSession("s", "origin", None),
        Character(id="c", name="C"),
        current_input="continue",
        history_messages=history_messages,
    )

    assert "[Recent RP History]" in prompt
    assert "Hero: Hello there" in prompt
    assert "assistant: General Kenobi" in prompt
    assert "hidden" not in prompt
    assert "Empty:" not in prompt
    assert "secret" not in prompt
