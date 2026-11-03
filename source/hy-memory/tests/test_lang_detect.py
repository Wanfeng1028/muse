"""Language routing for prompts, including code-heavy agent inputs."""

import pytest

from hy_memory.utils.lang_detect import (
    _leading_language_window,
    detect_language,
    is_chinese,
)
from hy_memory.agent.reconciler import build_reconcile_prompt


@pytest.mark.parametrize(
    "text,expected",
    [
        ("你好", "zh"),
        ("用户喜欢科幻电影，尤其是星际穿越。", "zh"),
        ("Hello", "en"),
        ("The user likes science fiction movies.", "en"),
        ("请修复 search_client.py 里的 timeout bug", "zh"),
        ("修复 bug: TypeError in function parse_response(request_id)", "zh"),
        ("执行 pytest tests/test_search.py，然后修复失败用例", "zh"),
        ("[user]: 请检查 api_client.py 的 timeout", "zh"),
        ("user: 请检查 api_client.py 的 timeout", "zh"),
        ("Please update the 中文 README file.", "en"),
        ("def search(query): return client.search(query)", "en"),
        ("Check https://example.com/docs and update config", "en"),
    ],
)
def test_detect_language_uses_leading_instruction(text, expected):
    detected = detect_language(text)
    routed = "zh" if detected == "zh" else "en"
    assert routed == expected


def test_leading_window_ignores_role_prefix_and_punctuation():
    assert _leading_language_window("  [user]: 请修复 api_client.py") == "请修复apiclie"


def test_messages_route_from_message_content_not_role_names():
    messages = [
        {"role": "user", "content": "请修复 search_client.py 的超时问题"},
        {"role": "assistant", "content": "I will inspect the implementation."},
    ]
    assert is_chinese(messages=messages) is True


def test_reconcile_uses_chinese_prompt_for_code_heavy_chinese_instruction():
    memory = (
        "请修复 search_client.py 里的 timeout bug: "
        "TypeError in parse_response(request_id)"
    )
    prompt = build_reconcile_prompt(
        new_memories=[memory],
        new_memories_block=memory,
        existing_memories_block="[]",
        current_date="2026-10-12 16:00",
    )
    assert prompt.startswith("你是一个记忆整合系统")


def test_reconcile_keeps_english_prompt_when_chinese_term_appears_later():
    memory = "Please update the 中文 README file."
    prompt = build_reconcile_prompt(
        new_memories=[memory],
        new_memories_block=memory,
        existing_memories_block="[]",
        current_date="2026-10-12 16:00",
    )
    assert prompt.startswith("You are a memory management system.")
