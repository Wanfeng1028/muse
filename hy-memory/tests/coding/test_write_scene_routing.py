# -*- coding: utf-8 -*-
"""write(scene=None) 三分类结果必须真正选择 working/coding variant。"""

import asyncio
from types import SimpleNamespace

import pytest

from hy_memory.client import HyMemoryClient


def _messages():
    return [
        {"role": "user", "content": "修改 auth.py 修复异常"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "1", "type": "function",
                "function": {
                    "name": "Edit",
                    "arguments": '{"path":"auth.py"}',
                },
            }],
        },
        {"role": "tool", "content": "done", "tool_call_id": "1", "name": "Edit"},
    ]


@pytest.mark.asyncio
async def test_auto_scene_routes_to_judged_coding_variant(monkeypatch):
    seen = {}

    async def _judge(*args, **kwargs):
        return "coding"

    class _Writer:
        async def write(self, *args, **kwargs):
            return {"success": True, "experience_ids": [], "fact_ids": []}

    async def _get_writer(*, variant):
        seen["variant"] = variant
        return _Writer()

    monkeypatch.setattr("hy_memory.client.classify_messages_scene", _judge)

    cfg = SimpleNamespace(coding=SimpleNamespace(enable=True))
    ns = SimpleNamespace(
        _config=cfg,
        _coding_llm_provider=object(),
        _cache=None,
        _get_coding_writer=_get_writer,
        _observe_chain=lambda *args, **kwargs: 0,
        _normalize_scene=HyMemoryClient._normalize_scene,
        _scene_variant=HyMemoryClient._scene_variant,
        _parse_input=HyMemoryClient._parse_input,
    )

    result = await HyMemoryClient._async_add_impl(
        ns, _messages(), user_id="u1", agent_id="a1", scene=None,
    )
    assert result["success"] is True
    assert seen["variant"] == "coding"
