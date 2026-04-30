from smarter_rp.models import Character, LorebookEntry, RpMessage, RpSession
from smarter_rp.services.lorebook_matcher import LorebookMatcher


def make_session(**kwargs):
    values = {
        "id": "session_1",
        "unified_msg_origin": "origin",
        "account_profile_id": None,
        "turn_count": 10,
    }
    values.update(kwargs)
    return RpSession(**values)


def make_character(**kwargs):
    values = {"id": "char_1", "name": "Alice"}
    values.update(kwargs)
    return Character(**values)


def entry(entry_id, title=None, content=None, **kwargs):
    values = {
        "id": entry_id,
        "lorebook_id": "book_1",
        "title": title or entry_id,
        "content": content or f"{entry_id} content",
    }
    values.update(kwargs)
    return LorebookEntry(**values)


def hit_ids(result):
    return [hit.entry_id for hit in result.hits]


def filtered_reasons(result):
    return {hit.entry_id: hit.filter_reason for hit in result.filtered}


def test_constant_and_keyword_entries_hit_and_bucket_content_by_position():
    entries = [
        entry("constant", "Always", "Always injected", constant=True, position="before_character"),
        entry("keyword", "Gate", "Gate lore", keys=["silver gate"], position="post_history"),
        entry("state", "Mood", "Mood lore", keys=["tense"], position="after_history"),
    ]
    session = make_session(summary="Summary mentions nothing", state={"mood": "tense"})
    result = LorebookMatcher().match(entries, "We approach the SILVER GATE.", [], session, make_character())

    assert hit_ids(result) == ["constant", "keyword", "state"]
    assert result.buckets == {
        "before_character": "Always injected",
        "post_history": "Gate lore",
        "after_history": "Mood lore",
    }
    assert result.hits[1].matched_key == "silver gate"
    assert result.hits[1].source == "searchable_text"


def test_regex_and_case_sensitivity():
    entries = [
        entry("regex", "Regex", "Regex lore", keys=[r"dragon\s+\d+"], regex=True),
        entry("case_hit", "Case Hit", "Case hit lore", keys=["ExactName"], case_sensitive=True),
        entry("case_miss", "Case Miss", "Case miss lore", keys=["exactname"], case_sensitive=True),
        entry("bad_regex", "Bad Regex", "Bad regex lore", keys=["["], regex=True),
    ]
    result = LorebookMatcher().match(entries, "Meet dragon 42 and ExactName.", [], make_session(), make_character())

    assert hit_ids(result) == ["case_hit", "regex"]
    assert filtered_reasons(result) == {"case_miss": "no_match", "bad_regex": "invalid_regex"}
    assert result.hits[1].matched_key == r"dragon\s+\d+"


def test_selective_entries_require_primary_and_secondary_keys():
    entries = [
        entry("both", "Both", "Both lore", keys=["castle"], secondary_keys=["queen"], selective=True),
        entry("primary_only", "Primary", "Primary lore", keys=["castle"], secondary_keys=["king"], selective=True),
        entry("secondary_only", "Secondary", "Secondary lore", keys=["forest"], secondary_keys=["queen"], selective=True),
    ]
    result = LorebookMatcher().match(entries, "The queen enters the castle.", [], make_session(), make_character())

    assert hit_ids(result) == ["both"]
    assert filtered_reasons(result) == {
        "primary_only": "selective_secondary_missing",
        "secondary_only": "selective_primary_missing",
    }


def test_priority_order_sorting_group_filtering_max_hits_and_max_chars_budget_trimming():
    entries = [
        entry("low", "Low", "Low lore", constant=True, priority=1, order=0),
        entry("group_b", "Group B", "Group B lore", constant=True, priority=5, order=2, group="guild"),
        entry("group_a", "Group A", "Group A lore", constant=True, priority=5, order=1, group="guild"),
        entry("alpha", "Alpha", "Alpha lore", constant=True, priority=5, order=1),
        entry("budget", "Budget", "Budget lore is too long", constant=True, priority=4, order=0),
    ]
    result = LorebookMatcher(max_hits=3, max_chars=len("Alpha lore\n\nGroup A lore")).match(
        entries, "", [], make_session(), make_character()
    )

    assert hit_ids(result) == ["alpha", "group_a"]
    reasons = filtered_reasons(result)
    assert reasons["group_b"] == "group_already_selected"
    assert reasons["budget"] == "budget"
    assert reasons["low"] == "max_hits"
    assert next(hit for hit in result.filtered if hit.entry_id == "budget").trimmed is True
    assert result.buckets == {"before_history": "Alpha lore\n\nGroup A lore"}


def test_group_filtered_entries_do_not_count_toward_max_hits():
    entries = [
        entry("group_a", "Group A", "Group A lore", constant=True, priority=5, order=1, group="guild"),
        entry("group_b", "Group B", "Group B lore", constant=True, priority=5, order=2, group="guild"),
        entry("later_valid", "Later Valid", "Later valid lore", constant=True, priority=4, order=0),
    ]
    result = LorebookMatcher(max_hits=2).match(entries, "", [], make_session(), make_character())

    assert hit_ids(result) == ["group_a", "later_valid"]
    assert filtered_reasons(result)["group_b"] == "group_already_selected"


def test_recursive_matching_has_depth_limit_and_no_loops():
    entries = [
        entry("root", "Root", "Mentions alpha", keys=["root"], recursive=True),
        entry("alpha", "Alpha", "Mentions beta and root", keys=["alpha"], recursive=True),
        entry("beta", "Beta", "Mentions gamma", keys=["beta"], recursive=True),
        entry("gamma", "Gamma", "Gamma lore", keys=["gamma"], recursive=True),
    ]
    result = LorebookMatcher(max_recursive_depth=2).match(
        entries, "root", [], make_session(), make_character()
    )

    assert hit_ids(result) == ["root", "alpha", "beta"]
    assert "gamma" not in hit_ids(result)
    assert result.hits[1].recursion_parent_id == "root"
    assert result.hits[2].recursion_parent_id == "alpha"
    assert hit_ids(result).count("root") == 1


def test_recursive_hits_reuse_group_selected_in_initial_pass():
    entries = [
        entry("initial", "Initial", "Mentions recursive key", keys=["start"], group="guild", recursive=True),
        entry("recursive", "Recursive", "Recursive lore", keys=["recursive key"], group="guild", recursive=True),
    ]
    result = LorebookMatcher().match(entries, "start", [], make_session(), make_character())

    assert hit_ids(result) == ["initial"]
    assert filtered_reasons(result)["recursive"] == "group_already_selected"


def test_recursive_child_is_not_duplicated_when_multiple_parents_match_it():
    entries = [
        entry("parent_a", "Parent A", "Mentions shared key", keys=["start"], recursive=True),
        entry("parent_b", "Parent B", "Also mentions shared key", keys=["start"], recursive=True),
        entry("child", "Child", "Child lore", keys=["shared key"], recursive=True),
    ]
    result = LorebookMatcher().match(entries, "start", [], make_session(), make_character())

    assert hit_ids(result) == ["parent_a", "parent_b", "child"]
    assert hit_ids(result).count("child") == 1


def test_recursive_pass_scans_non_recursive_parent_but_only_hits_recursive_targets():
    entries = [
        entry("root", "Root", "Mentions secret door", keys=["start"], recursive=False),
        entry("non_recursive", "Non Recursive", "Hidden lore", keys=["secret door"], recursive=False),
        entry("recursive", "Recursive", "Recursive lore", keys=["secret door"], recursive=True),
    ]
    result = LorebookMatcher().match(entries, "start", [], make_session(), make_character())

    assert hit_ids(result) == ["root", "recursive"]
    assert "non_recursive" not in hit_ids(result)


def test_filtered_entries_do_not_overlap_hits_after_recursive_match():
    entries = [
        entry("root", "Root", "Mentions alpha", keys=["root"], recursive=True),
        entry("alpha", "Alpha", "Alpha lore", keys=["alpha"], recursive=True),
    ]
    result = LorebookMatcher().match(entries, "root", [], make_session(), make_character())

    hit_entry_ids = {hit.entry_id for hit in result.hits}
    filtered_entry_ids = {hit.entry_id for hit in result.filtered}
    assert hit_entry_ids.isdisjoint(filtered_entry_ids)


def test_budget_trimming_removes_recursive_children_when_parent_is_trimmed():
    entries = [
        entry("root", "Root", "Mentions alpha with long content", keys=["root"], recursive=True),
        entry("alpha", "Alpha", "short", keys=["alpha"], recursive=True),
    ]
    result = LorebookMatcher(max_chars=len("short")).match(entries, "root", [], make_session(), make_character())

    assert hit_ids(result) == []
    reasons = filtered_reasons(result)
    assert reasons["root"] == "budget"
    assert reasons["alpha"] == "orphan_recursive"


def test_sticky_prior_hit_within_window_is_selected_without_current_key_match():
    entries = [entry("sticky", "Sticky", "Sticky lore", keys=["missing"], sticky_turns=3)]
    session = make_session(turn_count=10, last_lore_hits=[{"entry_id": "sticky", "turn_number": 8}])
    result = LorebookMatcher().match(entries, "no key here", [], session, make_character())

    assert hit_ids(result) == ["sticky"]
    assert result.hits[0].reason == "sticky"


def test_sticky_prior_hit_outside_window_is_not_selected():
    entries = [entry("sticky", "Sticky", "Sticky lore", keys=["missing"], sticky_turns=3)]
    session = make_session(turn_count=10, last_lore_hits=[{"entry_id": "sticky", "turn": 6}])
    result = LorebookMatcher().match(entries, "no key here", [], session, make_character())

    assert hit_ids(result) == []
    assert filtered_reasons(result)["sticky"] == "no_match"


def test_disabled_character_filter_probability_cooldown_and_chat_injection_limits():
    entries = [
        entry("disabled", "Disabled", "Disabled lore", constant=True, enabled=False),
        entry("wrong_char", "Wrong Char", "Wrong char lore", constant=True, character_filter=["Bob"]),
        entry("right_char_id", "Right Id", "Right id lore", constant=True, character_filter=["char_1"]),
        entry("right_char_name", "Right Name", "Right name lore", constant=True, character_filter=["Alice"]),
        entry("prob_zero", "Prob Zero", "Prob zero lore", constant=True, probability=0),
        entry("prob_one", "Prob One", "Prob one lore", constant=True, probability=1),
        entry("cooldown", "Cooldown", "Cooldown lore", constant=True, cooldown_turns=3, metadata={"last_hit_turn": 8}),
        entry("chat_limit", "Chat Limit", "Chat limit lore", constant=True, max_injections_per_chat=2),
    ]
    session = make_session(last_lore_hits=[{"entry_id": "chat_limit"}, {"entry_id": "chat_limit"}])
    metadata_before = dict(entries[6].metadata)
    result = LorebookMatcher().match(entries, "", [], session, make_character())

    assert hit_ids(result) == ["prob_one", "right_char_id", "right_char_name"]
    assert entries[6].metadata == metadata_before
    reasons = filtered_reasons(result)
    assert reasons["disabled"] == "disabled"
    assert reasons["wrong_char"] == "character_filter"
    assert reasons["prob_zero"] == "probability"
    assert reasons["cooldown"] == "cooldown"
    assert reasons["chat_limit"] == "max_injections_per_chat"


def test_negative_max_chars_does_not_mutate_matcher_max_chars():
    matcher = LorebookMatcher(max_chars=-1)
    result = matcher.match([entry("always", "Always", "Always lore", constant=True)], "", [], make_session(), make_character())

    assert result.hits == []
    assert filtered_reasons(result)["always"] == "budget"
    assert matcher.max_chars == -1


def test_regex_too_large_is_filtered_before_search():
    entries = [entry("huge_regex", "Huge Regex", "Huge regex lore", keys=["a" * 501], regex=True)]
    result = LorebookMatcher().match(entries, "a", [], make_session(), make_character())

    assert hit_ids(result) == []
    assert filtered_reasons(result)["huge_regex"] == "regex_too_large"


def test_character_filter_does_not_match_aliases():
    entries = [entry("alias_only", "Alias Only", "Alias lore", constant=True, character_filter=["Ally"])]
    result = LorebookMatcher().match(entries, "", [], make_session(), make_character(aliases=["Ally"]))

    assert hit_ids(result) == []
    assert filtered_reasons(result)["alias_only"] == "character_filter"


def test_searchable_text_uses_visible_history_summary_and_sorted_state():
    entries = [
        entry("history", "History", "History lore", keys=["visible clue"]),
        entry("hidden", "Hidden", "Hidden lore", keys=["secret hidden"]),
        entry("summary", "Summary", "Summary lore", keys=["old treaty"]),
        entry("state", "State", "State lore", keys=["rank: captain"]),
    ]
    history = [
        RpMessage("m1", "session_1", "user", "User", "visible clue", visible=True),
        RpMessage("m2", "session_1", "assistant", "Bot", "secret hidden", visible=False),
    ]
    session = make_session(summary="The old treaty matters.", state={"zone": "north", "rank": "captain"})
    result = LorebookMatcher().match(entries, "", history, session, make_character())

    assert hit_ids(result) == ["history", "state", "summary"]
    assert filtered_reasons(result)["hidden"] == "no_match"
