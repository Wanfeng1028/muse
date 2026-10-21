"""Manual conversation import keeps original text, role, fences, and unknown time.

The contract (`manual-conversation-import.md`) forbids guessing an author or a
message time. These tests pin the observable shape: time stays null, role markers
drive authorship, code fences survive verbatim, and an unsupported marker is a
located rejection rather than a silent rewrite.
"""

import json

import pytest

from one_memory.imports.chat_exports import parse_chat_export
from one_memory.imports.manual_transcript import (
    ManualTranscriptError,
    parse_manual_json,
    parse_marked_text,
)


def test_unknown_time_stays_null_and_is_never_guessed_from_text():
    payload = json.dumps(
        [{"role": "user", "content": "昨天下午我们定的预算是 5 万。", "time": None}]
    ).encode()
    export = parse_chat_export(payload, "chat.json")
    assert len(export.messages) == 1
    assert export.messages[0].created_at is None
    assert export.messages[0].verbatim == "昨天下午我们定的预算是 5 万。"


def test_natural_language_time_is_rejected_not_inferred():
    payload = json.dumps([{"role": "user", "content": "保留原文。", "time": "昨天下午"}]).encode()
    with pytest.raises(ManualTranscriptError) as caught:
        parse_chat_export(payload, "chat.json")
    assert caught.value.issue["code"] == "invalid_time"
    assert caught.value.issue["location"] == "message:1"


def test_naive_time_without_timezone_is_rejected_not_defaulted():
    payload = json.dumps(
        [{"role": "user", "content": "保留原文。", "time": "2026-09-12T09:00:00"}]
    ).encode()
    with pytest.raises(ManualTranscriptError) as caught:
        parse_chat_export(payload, "chat.json")
    assert caught.value.issue["code"] == "invalid_time"


def test_role_markers_drive_authorship_and_unsupported_markers_are_located():
    text = (
        "# 会话名称\n"
        "User: 项目发布前要保留原文引用。\n"
        "\n"
        "Assistant: 建议增加逐条检查。\n"
        "```python\n"
        "User: 这不是新的角色分段\n"
        "```\n"
    )
    parsed = parse_marked_text(text)
    assert [message.role for message in parsed] == ["user", "assistant"]
    assert parsed[0].project == "会话名称"
    assert "```python" in parsed[1].verbatim
    assert parsed[1].verbatim.endswith("```")
    assert "这不是新的角色分段" in parsed[1].verbatim
    assert all(message.created_at is None for message in parsed)

    with pytest.raises(ManualTranscriptError) as caught:
        parse_marked_text("User: 可读\nTool: 待处理")
    assert caught.value.issue["code"] == "unknown_role"
    assert caught.value.issue["location"] == "line:2"


def test_unclosed_code_fence_is_rejected_with_its_starting_line():
    with pytest.raises(ManualTranscriptError) as caught:
        parse_marked_text("User: 看这段代码\n```python\nx = 1\n")
    assert caught.value.issue["code"] == "unclosed_code"
    assert caught.value.issue["location"] == "line:1"


def test_the_same_snapshot_twice_stays_one_conversation_identity():
    payload = json.dumps(
        [
            {"role": "user", "content": "保留原文。"},
            {"role": "assistant", "content": "建议逐条检查。"},
        ]
    ).encode()
    first = parse_chat_export(payload, "chat.json").messages
    second = parse_chat_export(payload, "chat.json").messages
    assert [message.message_id for message in first] == ["1", "2"]
    assert [message.conversation_id for message in first] == [
        message.conversation_id for message in second
    ]
    assert [message.verbatim for message in first] == [message.verbatim for message in second]


def test_manual_json_rejects_unknown_fields_and_empty_messages():
    with pytest.raises(ManualTranscriptError) as caught:
        parse_manual_json([{"role": "user", "content": "x", "author": "person"}], "manual:1")
    assert caught.value.issue["code"] == "invalid_record"

    with pytest.raises(ManualTranscriptError) as caught:
        parse_manual_json([{"role": "user", "content": "   "}], "manual:1")
    assert caught.value.issue["code"] == "empty_message"
