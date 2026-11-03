# -*- coding: utf-8 -*-
"""preproc 工具测试"""

import pytest

from hy_memory.coding.preproc import (
    has_any_tool_message,
    strip_tool_messages,
    truncate_tool_result_text,
    truncate_tool_message,
    truncate_messages,
    prepare_extractor_messages,
    extract_files,
    extract_tool_summary,
    DEFAULT_MAX_TOOL_RESULT_BYTES,
)
from hy_memory.pipelines.base import ChatMessage, ToolCall


class TestHasAnyToolMessage:
    def test_no_tools(self):
        msgs = [ChatMessage(role="user", content="hi"),
                ChatMessage(role="assistant", content="ok")]
        assert not has_any_tool_message(msgs)

    def test_role_tool(self):
        msgs = [ChatMessage(role="user", content="hi"),
                ChatMessage(role="tool", content="r", tool_call_id="x")]
        assert has_any_tool_message(msgs)

    def test_assistant_tool_calls(self):
        msgs = [ChatMessage(role="assistant", content="",
                            tool_calls=[ToolCall(id="x", name="Read", arguments={})])]
        assert has_any_tool_message(msgs)

    def test_empty(self):
        assert not has_any_tool_message([])


class TestStripToolMessages:
    def test_drops_tool_role_messages(self):
        msgs = [
            ChatMessage(role="user", content="hi"),
            ChatMessage(role="tool", content="r", tool_call_id="x"),
            ChatMessage(role="assistant", content="bye"),
        ]
        out = strip_tool_messages(msgs)
        assert len(out) == 2
        assert out[0].role == "user" and out[1].role == "assistant"
        assert all(not m.is_tool_message() for m in out)

    def test_strips_tool_calls_keep_text(self):
        msgs = [
            ChatMessage(role="assistant", content="text only"),
            ChatMessage(role="assistant", content="some text",
                        tool_calls=[ToolCall(id="x", name="Read", arguments={})]),
            ChatMessage(role="assistant", content="",
                        tool_calls=[ToolCall(id="x", name="Read", arguments={})]),
        ]
        out = strip_tool_messages(msgs)
        # 第 1 条保留，第 2 条保留（content 非空，但 tool_calls drop），第 3 条整条丢
        assert len(out) == 2
        assert all(not m.has_tool_calls() for m in out)
        assert out[0].content == "text only"
        assert out[1].content == "some text"

    def test_unchanged_for_pure_chat(self):
        msgs = [ChatMessage(role="user", content="a"),
                ChatMessage(role="assistant", content="b")]
        out = strip_tool_messages(msgs)
        assert len(out) == 2
        assert out[0].content == "a" and out[1].content == "b"


class TestTruncate:
    def test_prepare_keeps_all_turns_and_truncates_tool_and_assistant(self):
        msgs = []
        for i in range(10):
            msgs.extend([
                ChatMessage(role="user", content=f"user-{i}"),
                ChatMessage(role="assistant", content="A" * 8000),
                ChatMessage(role="tool", content="T" * 5000, tool_name="Read"),
            ])
        out = prepare_extractor_messages(msgs)
        assert len(out) == len(msgs)
        assert [m.content for m in out if m.role == "user"] == [
            f"user-{i}" for i in range(10)
        ]
        assert all("chars omitted" in m.content for m in out if m.role == "assistant")
        assert all("bytes omitted" in m.content for m in out if m.role == "tool")

    def test_text_short_unchanged(self):
        s = "hello"
        assert truncate_tool_result_text(s) == "hello"

    def test_text_long_truncated(self):
        s = "x" * 10000
        out = truncate_tool_result_text(s, max_bytes=2048, head_bytes=1024, tail_bytes=512)
        assert len(out) < 10000
        assert "omitted" in out
        assert out.startswith("x" * 100)
        assert out.endswith("x" * 100)

    def test_utf8_limit_is_real_bytes(self):
        text = "中" * 1000  # 3000 UTF-8 bytes
        out = truncate_tool_result_text(
            text, max_bytes=1200, head_bytes=600, tail_bytes=300,
        )
        assert "bytes omitted" in out
        assert len(out.encode("utf-8")) < len(text.encode("utf-8"))

    def test_small_configured_limit_still_truncates(self):
        text = "x" * 2000
        out = truncate_tool_result_text(text, max_bytes=512)
        assert "bytes omitted" in out
        assert len(out.encode("utf-8")) <= 512

    def test_tool_message_truncated(self):
        big = ChatMessage(role="tool", content="x" * 5000)
        out = truncate_tool_message(big)
        assert len(out.content) < 5000
        # 原对象不变
        assert len(big.content) == 5000

    def test_non_tool_message_unchanged(self):
        m = ChatMessage(role="user", content="x" * 5000)
        assert truncate_tool_message(m) is m

    def test_truncate_messages_iterates(self):
        msgs = [
            ChatMessage(role="user", content="abc"),
            ChatMessage(role="tool", content="x" * 5000),
        ]
        out = truncate_messages(msgs)
        assert out[0].content == "abc"
        assert "omitted" in out[1].content

    def test_default_threshold(self):
        small = "x" * (DEFAULT_MAX_TOOL_RESULT_BYTES - 1)
        m = ChatMessage(role="tool", content=small)
        assert truncate_tool_message(m).content == small


class TestExtractFiles:
    def test_extract_path_keys(self):
        msgs = [
            ChatMessage(role="assistant", content="", tool_calls=[
                ToolCall(id="1", name="Read", arguments={"path": "src/a.py"}),
                ToolCall(id="2", name="Edit", arguments={"file_path": "src/b.py"}),
                ToolCall(id="3", name="Bash", arguments={"command": "ls"}),  # 无 path 键
            ]),
        ]
        files = extract_files(msgs)
        assert files == ["src/a.py", "src/b.py"]

    def test_dedup_and_sorted(self):
        msgs = [
            ChatMessage(role="assistant", content="", tool_calls=[
                ToolCall(id="1", name="Read", arguments={"path": "z.py"}),
                ToolCall(id="2", name="Read", arguments={"path": "a.py"}),
                ToolCall(id="3", name="Read", arguments={"path": "z.py"}),
            ]),
        ]
        assert extract_files(msgs) == ["a.py", "z.py"]

    def test_empty(self):
        assert extract_files([]) == []
        assert extract_files([ChatMessage(role="user", content="hi")]) == []


class TestExtractToolSummary:
    def test_per_turn_grouping(self):
        msgs = [
            ChatMessage(role="user", content="重构 auth"),
            ChatMessage(role="assistant", content="", tool_calls=[
                ToolCall(id="1", name="Read", arguments={"path": "a"}),
            ]),
            ChatMessage(role="tool", content="ok", tool_call_id="1", tool_name="Read"),
            ChatMessage(role="assistant", content="", tool_calls=[
                ToolCall(id="2", name="Edit", arguments={"path": "a"}),
            ]),
            ChatMessage(role="tool", content="ok", tool_call_id="2", tool_name="Edit"),
            ChatMessage(role="user", content="问个闲话"),
            ChatMessage(role="assistant", content="OK"),
        ]
        summary = extract_tool_summary(msgs)
        assert len(summary) == 2
        assert summary[0]["user"] == "重构 auth"
        assert sorted(summary[0]["tools"]) == ["Edit", "Read"]
        assert summary[0]["has_tool_result"] is True
        assert summary[1]["user"] == "问个闲话"
        assert summary[1]["tools"] == []
        assert summary[1]["has_tool_result"] is False

    def test_no_user_anchor_first(self):
        # tool 消息出现在 user 之前
        msgs = [
            ChatMessage(role="assistant", content="", tool_calls=[
                ToolCall(id="1", name="Read", arguments={}),
            ]),
        ]
        summary = extract_tool_summary(msgs)
        assert len(summary) == 1
        assert summary[0]["user"] == ""
        assert summary[0]["tools"] == ["Read"]
