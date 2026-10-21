import pytest

from one_memory.imports.sources.parsing import (
    strip_host_wrappers,
    unwrap_host_envelope_with_positions,
)


@pytest.mark.parametrize(
    "value,status,body",
    [
        (
            "  plain \u4e2d\u6587\U0001f680e\u0301  ",
            "identity",
            "plain \u4e2d\u6587\U0001f680e\u0301",
        ),
        ("<user_info>same</user_info>\n<user_query> same </user_query>", "unwrapped", "same"),
        ("<system-reminder>hidden</system-reminder>\nbody", "unwrapped", "body"),
        (" body <system-reminder>hidden</system-reminder> ", "unwrapped", "body"),
        (
            "<user_query> <user_query>quoted</user_query> tail </user_query>",
            "unwrapped",
            "<user_query>quoted</user_query> tail",
        ),
        (
            "<user_query>same</user_query>\n<image_local_path>same</image_local_path>",
            "unwrapped",
            "same",
        ),
        ("<user_info>hidden</user_info>", "unwrapped", None),
        (" \n ", "identity", None),
    ],
)
def test_exact_body_positions_match_legacy_unwrapping(value, status, body):
    result = unwrap_host_envelope_with_positions(value)
    assert result.text == strip_host_wrappers(value) == body
    assert result.status == status
    if body is None:
        assert result.start_cp is None and result.end_cp is None
    else:
        assert value[result.start_cp : result.end_cp] == body


@pytest.mark.parametrize(
    "value",
    [
        "<user_info>not closed",
        "<user_info>hidden</user_info> trailing explanation",
        "<user_query>one</user_query><user_query>two</user_query>",
        "<user_query>one</user_query> trailing explanation",
        "<user_query>not closed",
        "body<system-reminder>not closed",
    ],
)
def test_ambiguous_envelope_retains_legacy_text_but_never_authorizes_a_body(value):
    result = unwrap_host_envelope_with_positions(value)
    assert result.text == strip_host_wrappers(value) == value
    assert result.status == "ambiguous"
    assert result.start_cp is None and result.end_cp is None


def test_repeated_body_uses_actual_tag_position_not_first_match():
    value = "<rules>same</rules>  <user_query>  same  </user_query>"
    result = unwrap_host_envelope_with_positions(value)
    expected_start = len("<rules>same</rules>  <user_query>  ")
    assert result.start_cp == expected_start and result.end_cp == expected_start + 4
    assert value[result.start_cp : result.end_cp] == "same"
    assert result.prefix_blocks == ("<rules>same</rules>",)


def test_literal_middle_reminder_is_not_removed_or_shifted():
    value = "Explain <system-reminder>literal</system-reminder> in this code"
    result = unwrap_host_envelope_with_positions(value)
    assert result.status == "identity" and result.text == value
    assert (result.start_cp, result.end_cp) == (0, len(value))
