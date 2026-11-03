"""What a probe may say about a stranger's chat history, and what it may not.

The point of the probe is to make a parser writable without the archive
changing hands. That only works if its output is safe to paste into a chat,
so the line it draws is the whole design: shapes and key names are structure
and go out; message text is content and does not. These tests hold it to
that line, because a probe that leaks is worse than no probe -- it would be
pasted somewhere on the assumption that it was safe.
"""

from __future__ import annotations

import json
from pathlib import Path

from one_memory.imports.probe import describe_json, render_report


def test_reports_keys_and_shapes_without_any_message_text() -> None:
    secret = "某位同事说这个季度先不做 Windows,等模型额度下来再说"
    payload = [
        {
            "title": "内部排期",
            "mapping": {
                "abc-123": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": [secret]},
                    }
                }
            },
        }
    ]

    report = render_report(describe_json(payload))

    assert "mapping" in report
    assert "author" in report
    # Nothing of the conversation itself, not even a fragment of it.
    assert secret not in report
    assert "某位同事" not in report
    assert "模型额度" not in report
    assert "内部排期" not in report


def test_keeps_short_enumerations_because_they_are_the_shape() -> None:
    # Six rows over three roles, not three rows over three roles. A
    # vocabulary is recognised by repeating, and a sample where every value
    # is distinct is exactly the case the probe must not treat as one.
    payload = [
        {"author": {"role": "user"}},
        {"author": {"role": "assistant"}},
        {"author": {"role": "system"}},
        {"author": {"role": "user"}},
        {"author": {"role": "assistant"}},
        {"author": {"role": "user"}},
    ]

    report = render_report(describe_json(payload))

    # Roles decide whose sentence a memory is attributed to. A parser cannot
    # be written without knowing the exact spelling of these three, and they
    # carry nothing about the person.
    assert "user" in report
    assert "assistant" in report
    assert "system" in report


def test_holds_back_a_small_sample_where_every_value_differs() -> None:
    """The case that a distinct-value count alone gets wrong.

    Someone testing this with a throwaway account will have four messages,
    all different, all short. Counting distinct values makes that a
    four-value enumeration and prints the entire conversation.
    """
    payload = [
        {"text": "在吗"},
        {"text": "帮我看下这个"},
        {"text": "好的谢谢"},
        {"text": "明天再说"},
    ]

    report = render_report(describe_json(payload))

    for line in ("在吗", "帮我看下这个", "好的谢谢", "明天再说"):
        assert line not in report
    assert "free text" in report


def test_treats_a_field_with_many_distinct_values_as_content() -> None:
    payload = [{"title": f"关于 {n} 的讨论"} for n in range(30)]

    report = render_report(describe_json(payload))

    # Titles look enumerable in a three-row sample and are not. The rule has
    # to be about how the field behaves across the file, not how it looks in
    # the first row.
    assert "关于 0 的讨论" not in report
    assert "str" in report


def test_holds_back_a_value_seen_only_a_couple_of_times() -> None:
    """Two sightings of the same short string is not evidence of a vocabulary.

    The ratio rule alone lets this through: one distinct value over two
    sightings repeats perfectly. But "好的" said twice in a two-message
    sample is someone's message, not a label.
    """
    payload = [{"text": "好的"}, {"text": "好的"}]

    report = render_report(describe_json(payload))

    assert "好的" not in report


def test_holds_back_a_field_with_many_values_however_often_it_repeats() -> None:
    """A wide field is content even when every value repeats plenty.

    Twenty tags over a hundred rows repeats five times each and sails past
    the ratio rule. Twenty distinct free-form values is not a vocabulary we
    need spelled out to write a parser; knowing the field is a string is
    enough, and printing them is printing the user's data.
    """
    payload = [{"tag": f"话题{n % 20}"} for n in range(100)]

    report = render_report(describe_json(payload))

    assert "话题0" not in report
    assert "话题19" not in report
    assert "free text" in report


def test_holds_back_a_long_value_however_often_it_repeats() -> None:
    """Length wins over repetition. A boilerplate paragraph is still content.

    System prompts and canned disclaimers repeat identically across an entire
    export, so repetition cannot be the only test -- a single distinct value
    over fifty sightings is the strongest possible ratio.
    """
    boilerplate = "你是一个乐于助人的助手,请用简体中文回答用户的所有问题,并保持礼貌"
    payload = [{"system": boilerplate} for _ in range(50)]

    report = render_report(describe_json(payload))

    assert boilerplate not in report
    assert "乐于助人" not in report
    assert "free text" in report


def test_collapses_a_mapping_keyed_by_id() -> None:
    """Conversation ids are data wearing the costume of field names.

    A ChatGPT export keys its message map by uuid. Printing those as paths
    turns a report meant to be a page long into thousands of lines, and puts
    identifiers into it for no gain: nothing about a parser depends on which
    uuids this particular person happens to have.
    """
    payload = {"mapping": {f"id-{n}": {"role": "user"} for n in range(40)}}

    report = render_report(describe_json(payload))

    assert "{}" in report
    assert "id-39" not in report
    # The shape underneath the ids still has to come through.
    assert "role" in report


def test_counts_repetition_so_the_parser_knows_what_is_a_list() -> None:
    payload = {"conversations": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}

    report = render_report(describe_json(payload))

    # Whether an export holds one conversation or thousands changes both the
    # parser and the import's batching, and it cannot be read off a schema.
    assert "3" in report


def test_collapses_a_small_map_whose_keys_are_still_ids() -> None:
    """A count alone misses the common case, and a real export is the proof.

    A ChatGPT conversation with six messages has six uuid keys. That is
    fewer than any threshold worth setting on a record's field count, so
    counting keys leaves those uuids in the report as literal paths -- one
    branch of the report per message, with the ids in it. Found by running
    the probe on a synthetic export rather than by reading the code.
    """
    payload = {
        "mapping": {f"aaa-{n}-bbb-{n}": {"message": {"author": {"role": "user"}}} for n in range(6)}
    }

    report = render_report(describe_json(payload))

    assert "{}" in report
    assert "aaa-0-bbb-0" not in report
    assert "role" in report


def test_keeps_a_record_whose_field_names_are_long() -> None:
    # The other side of the same rule. Collapsing a genuine record loses the
    # field names, which are the one thing a parser is written from.
    payload = {"conversation": {"conversation_title": "x", "created_at_ms": 1, "model_slug": "y"}}

    report = render_report(describe_json(payload))

    for key in ("conversation_title", "created_at_ms", "model_slug"):
        assert key in report


def test_names_every_path_it_saw_so_nothing_is_silently_dropped() -> None:
    payload = {"a": {"b": {"c": {"d": 1}}}}

    report = render_report(describe_json(payload))

    for key in ("a", "b", "c", "d"):
        assert key in report


def test_survives_a_file_it_does_not_understand(tmp_path: Path) -> None:
    # Being handed something unexpected is the normal case for this tool. It
    # has to say so rather than raise, or the person running it learns only
    # that we crashed on their file.
    report = render_report(describe_json("just a string"))
    assert "str" in report

    mixed = json.loads('[1, "two", {"three": 3}, null, true]')
    report = render_report(describe_json(mixed))
    assert "int" in report
    assert "null" in report
