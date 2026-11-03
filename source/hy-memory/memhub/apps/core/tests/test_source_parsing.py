from collections.abc import Callable
from functools import partial

import pytest
from pydantic import JsonValue

from one_memory.imports.sources.claude_code import parse_claude_code_record
from one_memory.imports.sources.codex import parse_codex_record
from one_memory.imports.sources.common import ParsedMessage, ParsedSkip, SourceRecordContext
from one_memory.imports.sources.cursor_unified import _parse_transcript_record
from one_memory.imports.sources.parsing import strip_host_wrappers
from one_memory.imports.sources.qwen_code import parse_qwen_code_record
from one_memory.imports.sources.qwenwork import parse_qwenwork_record
from one_memory.imports.sources.workbuddy import parse_workbuddy_record

REMINDERS = ("additional_data", "system-reminder", "system_reminder", "working_memory_reminder")
CONTEXT_TAGS = ("user_info", "rules", "agent_transcripts", "system-notification", "pipeline_log")


@pytest.mark.parametrize("tag", REMINDERS)
def test_reminders_are_removed_only_at_message_edges(tag: str) -> None:
    reminder = f"<{tag}>Host context</{tag}>"
    assert strip_host_wrappers(reminder) is None
    assert strip_host_wrappers(reminder + "\nKeep this") == "Keep this"
    assert strip_host_wrappers("Keep this" + reminder) == "Keep this"
    assert strip_host_wrappers("Keep " + reminder + " this") == "Keep " + reminder + " this"
    assert strip_host_wrappers(f"Explain `{reminder}`") == f"Explain `{reminder}`"


@pytest.mark.parametrize("tag", (*REMINDERS, *CONTEXT_TAGS, "system_notification"))
def test_original_supported_outer_context_and_query_envelopes(tag: str) -> None:
    context = f"<{tag}>Host context</{tag}>"
    assert strip_host_wrappers(context) is None
    assert strip_host_wrappers(context + "\n<user_query>Keep this</user_query>") == "Keep this"


def test_attributed_reminder_is_opaque_before_finding_the_outer_query() -> None:
    envelope = (
        '<system-reminder data-role="user-context">\n'
        "<user_info>Host context</user_info>\n"
        "<automation_system_reminder>\n"
        "This is a scheduled automation task. The instructions are in <user_query>.\n"
        "</automation_system_reminder>\n"
        "</system-reminder>\n"
        "<user_query>Keep the complete actual query.</user_query>"
    )
    assert strip_host_wrappers(envelope) == "Keep the complete actual query."


@pytest.mark.parametrize(
    "text",
    [
        "Explain `<user_query>quoted</user_query>` and keep this suffix.",
        "```xml\n<user_query>quoted</user_query>\n```",
        "Transcript assessment:\n<user_query>historical query</user_query>\nEnd assessment.",
        "<unknown><user_query>not an outer query</user_query></unknown>",
        "<user_query>first</user_query><user_query>second</user_query>",
        "<system-reminder>mismatched</additional_data><user_query>query</user_query>",
        "<rules>quoted rules</rules> are the subject of my question.",
        "<user_query>query</user_query> followed by user text",
    ],
)
def test_quoted_embedded_ambiguous_and_malformed_envelopes_are_not_unwrapped(text: str) -> None:
    assert strip_host_wrappers(text) == text


def test_query_body_is_not_recursively_stripped() -> None:
    query = (
        "Keep `<user_query>quoted query</user_query>`, "
        "<system-reminder>quoted reminder</system-reminder> and x < 5."
    )
    assert strip_host_wrappers(f"<user_query>{query}</user_query>") == query


@pytest.mark.parametrize("tag", REMINDERS)
def test_literal_reminder_in_backticks_is_not_a_suffix_wrapper(tag: str) -> None:
    text = f"Explain `<{tag}>literal</{tag}>`"
    assert strip_host_wrappers(text) == text


def test_multiple_suffix_reminders_and_nested_queries_keep_the_message() -> None:
    text = (
        "Actual<system-reminder>Host <user_query>example</user_query></system-reminder>"
        "\n<working_memory_reminder>Other context</working_memory_reminder>"
    )
    assert strip_host_wrappers(text) == "Actual"


def test_observed_image_path_suffix_after_outer_query_is_host_metadata() -> None:
    text = (
        '<system-reminder data-role="user-context">Host context</system-reminder>'
        "<user_query>Inspect the image</user_query>\n"
        "<image_local_path>/fixture/image.png</image_local_path>"
    )
    assert strip_host_wrappers(text) == "Inspect the image"
    assert strip_host_wrappers(text + "\nKeep this explanation") == text + "\nKeep this explanation"


def test_nested_reminder_does_not_expose_its_inner_query() -> None:
    text = (
        '<system-reminder data-role="user-context">'
        "<system-reminder>nested</system-reminder>"
        "<user_query>host example</user_query></system-reminder>"
        "<user_query>Actual request</user_query>"
    )
    assert strip_host_wrappers(text) == "Actual request"


@pytest.fixture(params=["claude-code", "codex", "cursor", "qwen-code", "qwenwork", "workbuddy"])
def parse_user_text(request) -> Callable[[str], ParsedMessage | ParsedSkip]:
    source = request.param
    context = SourceRecordContext(file_key="fixture", relative_path="session.jsonl", ordinal="1")
    parsers = {
        "claude-code": parse_claude_code_record,
        "codex": parse_codex_record,
        "cursor": partial(_parse_transcript_record, subagent_ids=set()),
        "qwen-code": parse_qwen_code_record,
        "qwenwork": parse_qwenwork_record,
        "workbuddy": parse_workbuddy_record,
    }

    def parse(text: str) -> ParsedMessage | ParsedSkip:
        message: dict[str, JsonValue] = {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        }
        record: dict[str, JsonValue] = {"type": "user", "role": "user", "message": message}
        if source == "codex":
            record = {"type": "response_item", "payload": {"type": "message", **message}}
        return parsers[source](record, context)

    return parse


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<user_query>Actual request</user_query>", "Actual request"),
        (
            "<system_reminder>Host context</system_reminder><user_query>Actual</user_query>",
            "Actual",
        ),
        ("<user_info>Host context</user_info><user_query>Actual</user_query>", "Actual"),
        ("Actual<system-reminder>Host context</system-reminder>", "Actual"),
        (
            '<system_reminder data-role="user-context">Literal <user_query> here.'
            "</system_reminder><user_query>Actual</user_query>",
            "Actual",
        ),
        (
            "<user_query>Keep `<user_query>quoted</user_query>` and "
            "<system-reminder>quoted reminder</system-reminder>.</user_query>",
            "Keep `<user_query>quoted</user_query>` and "
            "<system-reminder>quoted reminder</system-reminder>.",
        ),
    ],
)
def test_shared_parser_positive_controls_across_sources(parse_user_text, text, expected) -> None:
    result = parse_user_text(text)
    assert isinstance(result, ParsedMessage)
    assert result.verbatim == expected


@pytest.mark.parametrize(
    "text",
    [
        "Explain `<user_query>quoted</user_query>` and retain this suffix.",
        "```xml\n<user_query>quoted</user_query>\n```",
        "Assessment transcript:\n<user_query>historical</user_query>\nFull assessment.",
        "A <system-reminder>literal</system-reminder> in a human sentence.",
    ],
)
def test_shared_parser_preserves_embedded_tags_across_sources(parse_user_text, text) -> None:
    result = parse_user_text(text)
    assert isinstance(result, ParsedMessage)
    assert result.verbatim == text
