# -*- coding: utf-8 -*-
"""
推理模型（hy3 / kimi-k2.5 / deepseek-v4）的 reasoning 诊断字段。

背景：推理模型的思维链（reasoning_content）与正文（content）共用 max_tokens。
思维链写满额度后 content 返回空字符串，EXTRACT 报 EMPTY_RESPONSE 并静默丢弃
记忆，而日志里看不出原因。这里覆盖 LLMResponse 的 reasoning 字段提取，确保
排查时能直接从日志判定「是思维链吃光了输出配额」。
"""

from hy_memory.agent.llm_provider import LLMProvider, LLMResponse


class _Details:
    def __init__(self, reasoning_tokens):
        self.reasoning_tokens = reasoning_tokens


class _Usage:
    def __init__(self, reasoning_tokens=None, flat_reasoning_tokens=None):
        self.total_tokens = 2000
        self.prompt_tokens = 0
        self.completion_tokens = 2000
        if reasoning_tokens is not None:
            self.completion_tokens_details = _Details(reasoning_tokens)
        if flat_reasoning_tokens is not None:
            self.reasoning_tokens = flat_reasoning_tokens


class _Msg:
    def __init__(self, content="", reasoning_content=None, provider_specific_fields=None):
        self.content = content
        if reasoning_content is not None:
            self.reasoning_content = reasoning_content
        if provider_specific_fields is not None:
            self.provider_specific_fields = provider_specific_fields


def test_reasoning_from_message_field():
    """hy3 / kimi 标准位置：message.reasoning_content。"""
    msg = _Msg(content="", reasoning_content="让我想想……")
    usage = _Usage(reasoning_tokens=2000)

    rc, rt = LLMProvider._extract_reasoning(msg, usage)

    assert rc == "让我想想……"
    assert rt == 2000


def test_reasoning_from_provider_specific_fields():
    """部分网关只在 provider_specific_fields 里回传思维链。"""
    msg = _Msg(content="", provider_specific_fields={"reasoning_content": "思考过程"})
    usage = _Usage(reasoning_tokens=123)

    rc, rt = LLMProvider._extract_reasoning(msg, usage)

    assert rc == "思考过程"
    assert rt == 123


def test_reasoning_tokens_flattened_on_usage():
    """LiteLLM 网关把 reasoning_tokens 平铺在 usage 上，而非 details 里。"""
    msg = _Msg(content="")
    usage = _Usage(flat_reasoning_tokens=888)

    _rc, rt = LLMProvider._extract_reasoning(msg, usage)

    assert rt == 888


def test_no_reasoning_is_zero():
    """非推理模型 / no_think 模式：两个字段都为空，不应报错。"""
    msg = _Msg(content="ok")
    usage = _Usage()

    rc, rt = LLMProvider._extract_reasoning(msg, usage)

    assert rc == ""
    assert rt == 0


def test_missing_usage_is_tolerated():
    """usage 缺失（部分错误响应）时不应抛异常。"""
    rc, rt = LLMProvider._extract_reasoning(_Msg(content="ok"), None)

    assert rc == ""
    assert rt == 0


def test_llm_response_defaults():
    """新字段有默认值，旧调用方构造 LLMResponse 不受影响。"""
    resp = LLMResponse(content="ok")

    assert resp.reasoning_content == ""
    assert resp.reasoning_tokens == 0
