# -*- coding: utf-8 -*-
"""
ChatMessage / ToolCall / WriteRequest schema 扩展 + _parse_input 双风格规范化测试

覆盖：
- ChatMessage / ToolCall 基础字段与 to_dict / from_dict round-trip
- WriteRequest 新增 workspace_id / branch 字段
- _parse_input：纯字符串、旧式 plain messages、OpenAI 风格、Anthropic 风格、
                嵌套 tool_result 内容、多 tool_use+tool_result 配对、非法 JSON args、
                空 content 防御
- _parse_input 不变量：所有 ChatMessage.content 永远是 string
"""

from typing import List

import pytest

from hy_memory.client import HyMemoryClient
from hy_memory.pipelines.base import ChatMessage, ToolCall, WriteRequest


# ================================================================
# ToolCall / ChatMessage 基础
# ================================================================

class TestToolCall:
    def test_default_construction(self):
        tc = ToolCall()
        assert tc.id == "" and tc.name == "" and tc.arguments == {}

    def test_to_dict(self):
        tc = ToolCall(id="t1", name="Read", arguments={"path": "a.py"})
        assert tc.to_dict() == {"id": "t1", "name": "Read", "arguments": {"path": "a.py"}}

    def test_from_dict_round_trip(self):
        d = {"id": "x", "name": "Bash", "arguments": {"command": "ls"}}
        assert ToolCall.from_dict(d).to_dict() == d

    def test_from_dict_handles_missing_keys(self):
        tc = ToolCall.from_dict({})
        assert tc.id == "" and tc.name == "" and tc.arguments == {}

    def test_from_dict_handles_none_arguments(self):
        tc = ToolCall.from_dict({"id": "x", "name": "Y", "arguments": None})
        assert tc.arguments == {}


class TestChatMessageBackwardCompat:
    """已有 chat 路径用法不能改变行为"""

    def test_old_construction_still_works(self):
        m = ChatMessage(role="user", content="hi")
        assert m.role == "user" and m.content == "hi"
        assert m.tool_calls == []
        assert m.tool_call_id is None
        assert m.tool_name is None

    def test_old_to_dict_format_unchanged(self):
        # 不带 tool 信息时 to_dict 输出格式与历史完全一致
        m = ChatMessage(role="user", content="hi")
        assert m.to_dict() == {"role": "user", "content": "hi"}

    def test_old_from_dict_unchanged(self):
        m = ChatMessage.from_dict({"role": "assistant", "content": "ok"})
        assert m.role == "assistant" and m.content == "ok"
        assert not m.has_tool_calls() and not m.is_tool_message()


class TestChatMessageNewFields:
    def test_to_dict_includes_tool_calls(self):
        tc = ToolCall(id="t1", name="Read", arguments={"path": "a.py"})
        m = ChatMessage(role="assistant", content="", tool_calls=[tc])
        d = m.to_dict()
        assert d["role"] == "assistant" and d["content"] == ""
        assert d["tool_calls"] == [tc.to_dict()]
        assert "tool_call_id" not in d  # 默认 None 不输出
        assert "tool_name" not in d

    def test_to_dict_includes_tool_result_fields(self):
        m = ChatMessage(role="tool", content="42 lines", tool_call_id="t1", tool_name="Read")
        d = m.to_dict()
        assert d["tool_call_id"] == "t1"
        assert d["tool_name"] == "Read"
        assert "tool_calls" not in d  # 空列表不输出

    def test_helpers(self):
        # has_tool_calls
        assert not ChatMessage(role="user").has_tool_calls()
        assert ChatMessage(role="assistant",
                           tool_calls=[ToolCall(id="x", name="Y")]).has_tool_calls()
        # is_tool_message
        assert ChatMessage(role="tool").is_tool_message()
        assert not ChatMessage(role="user").is_tool_message()

    def test_from_dict_round_trip_with_tool_calls(self):
        d = {
            "role": "assistant",
            "content": "I'll read it",
            "tool_calls": [{"id": "x", "name": "Bash", "arguments": {"cmd": "ls"}}],
        }
        m = ChatMessage.from_dict(d)
        assert m.has_tool_calls()
        assert m.tool_calls[0].arguments == {"cmd": "ls"}


# ================================================================
# WriteRequest 扩展
# ================================================================

class TestWriteRequestExtension:
    def test_default_workspace_branch_none(self):
        wr = WriteRequest(content="x", user_id="u1")
        assert wr.workspace_id is None
        assert wr.branch is None

    def test_set_workspace_and_branch(self):
        wr = WriteRequest(content="x", user_id="u1",
                          workspace_id="github.com/x/y", branch="main")
        assert wr.workspace_id == "github.com/x/y"
        assert wr.branch == "main"

    def test_existing_fields_unaffected(self):
        wr = WriteRequest(content="x", user_id="u1", agent_id="a1",
                          session_id="s1")
        assert wr.user_id == "u1" and wr.agent_id == "a1" and wr.session_id == "s1"


# ================================================================
# _parse_input — 主路径
# ================================================================

class TestParseInputBackwardCompat:
    def test_string_input(self):
        content, msgs, ctype = HyMemoryClient._parse_input("hello")
        assert content == "hello" and msgs == [] and ctype == "text"

    def test_invalid_input_type(self):
        with pytest.raises(TypeError):
            HyMemoryClient._parse_input(42)

    def test_plain_messages(self):
        data = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "我帮你"},
        ]
        _, msgs, ctype = HyMemoryClient._parse_input(data)
        assert ctype == "messages"
        assert len(msgs) == 2
        assert msgs[0].role == "user" and msgs[0].content == "你好"
        assert msgs[1].role == "assistant" and msgs[1].content == "我帮你"
        # 不会因为新字段引入额外消息
        assert all(not m.tool_calls for m in msgs)


class TestParseInputOpenAIStyle:
    def test_assistant_with_tool_calls_and_tool_message(self):
        data = [
            {"role": "user", "content": "读 a.py"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "t1", "type": "function",
                             "function": {"name": "Read",
                                          "arguments": '{"path": "a.py"}'}}]},
            {"role": "tool", "tool_call_id": "t1", "name": "Read",
             "content": "file ok\n42 lines"},
        ]
        _, msgs, _ = HyMemoryClient._parse_input(data)
        assert len(msgs) == 3
        # assistant
        assert msgs[1].role == "assistant"
        assert msgs[1].content == ""  # null → ""
        assert len(msgs[1].tool_calls) == 1
        tc = msgs[1].tool_calls[0]
        assert tc.id == "t1" and tc.name == "Read"
        # arguments 已被 json.loads 成 dict
        assert tc.arguments == {"path": "a.py"}
        # tool message
        assert msgs[2].role == "tool"
        assert msgs[2].tool_call_id == "t1"
        assert msgs[2].tool_name == "Read"
        assert msgs[2].content == "file ok\n42 lines"

    def test_invalid_json_arguments_become_raw(self):
        data = [
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "x",
                             "function": {"name": "Bad",
                                          "arguments": "{not valid"}}]},
        ]
        _, msgs, _ = HyMemoryClient._parse_input(data)
        assert msgs[0].tool_calls[0].arguments == {"_raw": "{not valid"}

    def test_empty_arguments_string(self):
        data = [
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "x",
                             "function": {"name": "F", "arguments": ""}}]},
        ]
        _, msgs, _ = HyMemoryClient._parse_input(data)
        assert msgs[0].tool_calls[0].arguments == {}

    def test_tool_message_with_null_content(self):
        data = [{"role": "tool", "tool_call_id": "t1", "content": None}]
        _, msgs, _ = HyMemoryClient._parse_input(data)
        assert len(msgs) == 1
        assert msgs[0].role == "tool"
        assert msgs[0].content == ""


class TestParseInputAnthropicStyle:
    def test_text_plus_tool_use_block(self):
        data = [
            {"role": "user", "content": "读 a.py"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "让我读一下"},
                {"type": "tool_use", "id": "t2", "name": "Read",
                 "input": {"path": "a.py"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t2",
                 "content": "42 lines"},
            ]},
        ]
        _, msgs, _ = HyMemoryClient._parse_input(data)
        # user1 + assistant(text+tool_call) + tool(从 user 拆出来的)
        assert len(msgs) == 3
        assert msgs[0].role == "user" and msgs[0].content == "读 a.py"
        assert msgs[1].role == "assistant"
        assert msgs[1].content == "让我读一下"
        assert len(msgs[1].tool_calls) == 1
        assert msgs[1].tool_calls[0].id == "t2"
        assert msgs[1].tool_calls[0].arguments == {"path": "a.py"}
        # tool_result 拆为独立 role=tool 消息
        assert msgs[2].role == "tool"
        assert msgs[2].tool_call_id == "t2"
        assert msgs[2].content == "42 lines"

    def test_nested_tool_result_content_list(self):
        data = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t3",
                 "content": [
                     {"type": "text", "text": "output line 1"},
                     {"type": "text", "text": "line 2"},
                 ]},
            ]},
        ]
        _, msgs, _ = HyMemoryClient._parse_input(data)
        assert len(msgs) == 1
        assert msgs[0].role == "tool"
        assert msgs[0].content == "output line 1\nline 2"

    def test_multiple_tool_use_and_tool_result_pairs(self):
        data = [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "a", "name": "Read",
                 "input": {"path": "x.py"}},
                {"type": "tool_use", "id": "b", "name": "Read",
                 "input": {"path": "y.py"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "X"},
                {"type": "tool_result", "tool_use_id": "b", "content": "Y"},
            ]},
        ]
        _, msgs, _ = HyMemoryClient._parse_input(data)
        # assistant(空 text + 2 tool_calls) + 2 个独立 tool 消息
        assert len(msgs) == 3
        assert msgs[0].role == "assistant"
        assert msgs[0].content == ""
        assert len(msgs[0].tool_calls) == 2
        assert msgs[1].role == "tool" and msgs[1].tool_call_id == "a"
        assert msgs[1].content == "X"
        assert msgs[2].role == "tool" and msgs[2].tool_call_id == "b"
        assert msgs[2].content == "Y"

    def test_assistant_only_text_block(self):
        # 只有 text block 时不应产生空 tool_calls 列表
        data = [
            {"role": "assistant", "content": [
                {"type": "text", "text": "纯文本回复"},
            ]},
        ]
        _, msgs, _ = HyMemoryClient._parse_input(data)
        assert len(msgs) == 1
        assert msgs[0].role == "assistant"
        assert msgs[0].content == "纯文本回复"
        assert msgs[0].tool_calls == []

    def test_empty_content_block_list_drops_message(self):
        # content=[] 且无任何 tool_calls 不应保留这条消息
        data = [{"role": "assistant", "content": []}]
        _, msgs, _ = HyMemoryClient._parse_input(data)
        assert len(msgs) == 0

    def test_unknown_block_type_silently_ignored(self):
        data = [
            {"role": "assistant", "content": [
                {"type": "image", "source": {"data": "..."}},  # 未知 block
                {"type": "text", "text": "看图"},
            ]},
        ]
        _, msgs, _ = HyMemoryClient._parse_input(data)
        assert len(msgs) == 1
        assert msgs[0].content == "看图"


class TestParseInputInvariants:
    """所有路径下 ChatMessage.content 必须是 string"""

    @pytest.mark.parametrize("data", [
        [{"role": "user", "content": "plain"}],
        [{"role": "assistant", "content": None,
          "tool_calls": [{"id": "x", "function":
                          {"name": "F", "arguments": "{}"}}]}],
        [{"role": "assistant", "content":
          [{"type": "text", "text": "a"},
           {"type": "tool_use", "id": "i", "name": "N", "input": {}}]}],
        [{"role": "user", "content":
          [{"type": "tool_result", "tool_use_id": "i", "content": "r"}]}],
        [{"role": "tool", "tool_call_id": "i", "content": None}],
    ])
    def test_content_always_str(self, data):
        _, msgs, _ = HyMemoryClient._parse_input(data)
        for m in msgs:
            assert isinstance(m.content, str), \
                f"role={m.role} content type is {type(m.content).__name__}"

    def test_role_tool_arguments_always_dict(self):
        data = [
            {"role": "assistant", "content": None,
             "tool_calls": [
                 {"id": "1", "function": {"name": "A", "arguments": '{"a": 1}'}},
                 {"id": "2", "function": {"name": "B", "arguments": "bogus"}},
                 {"id": "3", "function": {"name": "C", "arguments": ""}},
                 {"id": "4", "function": {"name": "D", "arguments": None}},
             ]},
        ]
        _, msgs, _ = HyMemoryClient._parse_input(data)
        for tc in msgs[0].tool_calls:
            assert isinstance(tc.arguments, dict)
