from smarter_rp.models import AccountProfile, Character, RpSession
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
