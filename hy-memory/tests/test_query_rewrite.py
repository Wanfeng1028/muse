# -*- coding: utf-8 -*-
"""analyze_queries（合并判类 + 改写 + 时间跨度）单元测试。

用 fake LLM provider 精确控制返回文本，验证解析、时间换算、fail-safe。
"""

import asyncio
from datetime import datetime

import pytest

from hy_memory.coding.judge import analyze_queries, _since_to_created_after
from hy_memory.agent.llm_provider import LLMResponse


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeLLM:
    def __init__(self, content, raise_exc=False):
        self._content = content
        self._raise = raise_exc
        self.last_prompt = None

    async def complete(self, *, prompt, max_tokens, temperature=None, **kw):
        self.last_prompt = prompt
        if self._raise:
            raise RuntimeError("llm down")
        return LLMResponse(content=self._content, tokens_used=1,
                           prompt_tokens=1, completion_tokens=0)


CT = "2026-07-01T10:00:00"


class TestClassifyPlusRewritePlusSince:
    def test_full_output_parsed(self):
        llm = _FakeLLM("1\nhow did we configure the qdrant client\nSINCE: 2026-06-24")
        r = run(analyze_queries(
            ["上周那个向量库的配置", "对，就是我刚才说的那个"],
            llm, want_classify=True, want_rewrite=True, current_time=CT))
        assert r["ok"] is True
        assert r["is_coding"] is True
        assert r["rewrite_query"] == "how did we configure the qdrant client"
        assert r["created_after"] == datetime(2026, 6, 24).timestamp()

    def test_chat_class_since_none(self):
        llm = _FakeLLM("0\n用户昨天提到的那个重要的事情是什么\nSINCE: NONE")
        r = run(analyze_queries(
            ["我昨天跟你说的那个事你还记得吧"],
            llm, want_classify=True, want_rewrite=True, current_time=CT))
        assert r["ok"] is True
        assert r["is_coding"] is False
        assert r["created_after"] is None
        assert "重要的事情" in r["rewrite_query"]


class TestRewriteOnly:
    def test_no_classify_line(self):
        # want_classify=False → 输出无 0/1 头，第一行就是 rewrite
        llm = _FakeLLM("what important thing did the user mention last week\nSINCE: 2026-06-24")
        r = run(analyze_queries(
            ["我上周跟你说了什么重要的事情"],
            llm, want_classify=False, want_rewrite=True, current_time=CT))
        assert r["ok"] is True
        assert r["is_coding"] is False  # 不判类恒 False
        assert r["rewrite_query"].startswith("what important thing")
        assert r["created_after"] == datetime(2026, 6, 24).timestamp()

    def test_prompt_has_no_classify_task_when_off(self):
        llm = _FakeLLM("rewritten\nSINCE: NONE")
        run(analyze_queries(["q"], llm, want_classify=False,
                           want_rewrite=True, current_time=CT))
        # 关闭判类时 prompt 不应含 "Classify"
        assert "Classify the target" not in llm.last_prompt


class TestFailSafe:
    def test_llm_exception_returns_ok_false(self):
        llm = _FakeLLM("", raise_exc=True)
        r = run(analyze_queries(["a", "b"], llm, want_classify=True,
                               want_rewrite=True, current_time=CT))
        assert r["ok"] is False
        assert r["rewrite_query"] == "b"  # fallback = target
        assert r["created_after"] is None

    def test_empty_content_fallback(self):
        llm = _FakeLLM("")
        r = run(analyze_queries(["a"], llm, want_classify=True,
                               want_rewrite=True, current_time=CT))
        assert r["ok"] is False

    def test_unrecognized_class_head(self):
        llm = _FakeLLM("maybe\nrewritten\nSINCE: NONE")
        r = run(analyze_queries(["a"], llm, want_classify=True,
                               want_rewrite=True, current_time=CT))
        assert r["ok"] is False

    def test_want_rewrite_false_short_circuits(self):
        llm = _FakeLLM("should not be called")
        r = run(analyze_queries(["a"], llm, want_classify=True,
                               want_rewrite=False, current_time=CT))
        assert r["ok"] is False
        assert llm.last_prompt is None  # 没调 LLM


class TestSinceParse:
    def test_iso_date(self):
        assert _since_to_created_after("2026-06-24", CT) == datetime(2026, 6, 24).timestamp()

    def test_slash_date(self):
        assert _since_to_created_after("2026/06/24", CT) == datetime(2026, 6, 24).timestamp()

    def test_none_variants(self):
        for v in ["NONE", "none", "", "N/A", "-", "null"]:
            assert _since_to_created_after(v, CT) is None

    def test_quoted_and_trailing(self):
        assert _since_to_created_after('"2026-06-24".', CT) == datetime(2026, 6, 24).timestamp()

    def test_date_with_time_truncated(self):
        assert _since_to_created_after("2026-06-24T08:00:00", CT) == datetime(2026, 6, 24).timestamp()

    def test_garbage_returns_none(self):
        assert _since_to_created_after("last tuesday", CT) is None
