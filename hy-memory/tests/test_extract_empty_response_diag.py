from types import SimpleNamespace

import pytest

from hy_memory.agent.extractor import Extractor
from hy_memory.agent.llm_provider import LLMResponse
from hy_memory.config import LLMConfig
from hy_memory.pipelines.writer import MemoryWriter


class EmptyLLMProvider:
    async def complete_messages(self, **kwargs):
        return LLMResponse(
            content="",
            tokens_used=123,
            prompt_tokens=120,
            completion_tokens=3,
            model="mock-empty-model",
            finish_reason="stop",
            response_id="resp-empty-1",
            choices_count=1,
            tool_calls=None,
        )


@pytest.mark.asyncio
async def test_empty_response_keeps_llm_diagnostics():
    extractor = Extractor(EmptyLLMProvider(), LLMConfig())

    result = await extractor.extract(
        content="用户喜欢喝咖啡。",
        current_time="2026-08-12T00:00:00",
    )

    assert result.success is False
    assert result.error_code == "EMPTY_RESPONSE"
    assert result.llm_finish_reason == "stop"
    assert result.llm_model == "mock-empty-model"
    assert result.llm_response_id == "resp-empty-1"
    assert result.llm_choices_count == 1
    assert result.llm_content_len == 0
    assert result.llm_tool_calls_count == 0
    assert result.prompt_tokens == 120
    assert result.completion_tokens == 3
    assert result.tokens_used == 123


def test_writer_extract_llm_diag_fields():
    extract_result = SimpleNamespace(
        llm_finish_reason="stop",
        llm_model="mock-model",
        llm_response_id="resp-123",
        llm_choices_count=1,
        llm_content_len=0,
        llm_tool_calls_count=0,
        prompt_tokens=120,
        completion_tokens=3,
        tokens_used=123,
    )
    agent_result = SimpleNamespace(_extract_result=extract_result)

    diag = MemoryWriter._extract_llm_diag(None, agent_result)

    assert diag == {
        "llm_finish_reason": "stop",
        "llm_model": "mock-model",
        "llm_response_id": "resp-123",
        "llm_choices_count": 1,
        "llm_content_len": 0,
        "llm_tool_calls_count": 0,
        "llm_prompt_tokens": 120,
        "llm_completion_tokens": 3,
        "llm_total_tokens": 123,
    }
