# -*- coding: utf-8 -*-
"""
覆盖 `HyMemoryClient._normalize_message` 对 `tool_calls` 字段的兼容处理。

背景：部分客户端（如 codebuddy）会把 `tool_calls` 编码成 JSON 字符串而非
list[dict]，直接对字符串做 for 循环会按字符迭代，随后 `tc.get(...)` 抛出
`AttributeError: 'str' object has no attribute 'get'`。

运行方式：
    pytest tests/test_normalize_message_tool_calls.py -v
"""

from hy_memory.client import HyMemoryClient


def test_tool_calls_normal_list():
    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "1", "function": {"name": "f", "arguments": "{}"}},
        ],
    }
    result = HyMemoryClient._normalize_message(msg)
    assert len(result) == 1
    assert len(result[0].tool_calls) == 1
    assert result[0].tool_calls[0].name == "f"
    assert result[0].tool_calls[0].id == "1"


def test_tool_calls_json_string():
    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": '[{"id":"1","function":{"name":"f","arguments":"{}"}}]',
    }
    result = HyMemoryClient._normalize_message(msg)
    assert len(result) == 1
    assert len(result[0].tool_calls) == 1
    assert result[0].tool_calls[0].name == "f"
    assert result[0].tool_calls[0].id == "1"


def test_tool_calls_empty_string():
    msg = {"role": "assistant", "content": "", "tool_calls": ""}
    result = HyMemoryClient._normalize_message(msg)
    assert result[0].tool_calls == []


def test_tool_calls_invalid_json_string():
    msg = {"role": "assistant", "content": "", "tool_calls": "not-json"}
    result = HyMemoryClient._normalize_message(msg)
    assert result[0].tool_calls == []


def test_tool_calls_list_with_non_dict_items():
    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": ["x", {"id": "1", "function": {"name": "f", "arguments": "{}"}}],
    }
    result = HyMemoryClient._normalize_message(msg)
    assert len(result[0].tool_calls) == 1
    assert result[0].tool_calls[0].name == "f"


def test_real_world_codebuddy_case():
    """回归验收现场：assistant 消息 tool_calls 为字符串，read_file 调用需被正确抽出。"""
    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": (
            '[{"id":"toolu_bdrk_013NXmCFJ53CN1uTUuUtz8mH","type":"function",'
            '"function":{"name":"read_file",'
            '"arguments":"{\\"filePath\\":\\"/a/b.java\\"}"}}]'
        ),
        "tool_call_id": "",
    }
    result = HyMemoryClient._normalize_message(msg)
    assert len(result) == 1
    tool_calls = result[0].tool_calls
    assert len(tool_calls) == 1
    assert tool_calls[0].id == "toolu_bdrk_013NXmCFJ53CN1uTUuUtz8mH"
    assert tool_calls[0].name == "read_file"
    assert tool_calls[0].arguments == {"filePath": "/a/b.java"}
