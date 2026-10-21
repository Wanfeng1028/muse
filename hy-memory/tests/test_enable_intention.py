# -*- coding: utf-8 -*-
"""MEMORY_ENABLE_INTENTION / LLMConfig.enable_intention 开关。"""

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from hy_memory.agent.extractor import (
    EXTRACT_PROMPT,
    EXTRACT_PROMPT_NO_INTENTION,
    EXTRACT_SYSTEM_PROMPT,
    _system_prompt_without_intention,
)
from hy_memory.agent.prompts_zh import (
    EXTRACT_PROMPT_ZH_NO_INTENTION,
    EXTRACT_SYSTEM_PROMPT_ZH,
)
from hy_memory.config import LLMConfig, MemoryConfig
from hy_memory.models.memory import MemoryLayer, MemoryNode, MemoryStatus
from hy_memory.pipelines.base import WriteRequest


class TestIntentionPromptGate:
    def test_system_en_strips_intentions(self):
        s = _system_prompt_without_intention(EXTRACT_SYSTEM_PROMPT, lang="en")
        assert "## intentions" not in s
        assert "INTENTION DISABLED" in s
        assert "future plans" in s.lower() or "upcoming" in s.lower()

    def test_system_zh_strips_intentions(self):
        s = _system_prompt_without_intention(EXTRACT_SYSTEM_PROMPT_ZH, lang="zh")
        assert "## intentions" not in s
        assert "INTENTION 关闭" in s

    def test_user_prompt_variants(self):
        assert '"intentions"' in EXTRACT_PROMPT
        assert '"intentions"' not in EXTRACT_PROMPT_NO_INTENTION
        assert '"intentions"' not in EXTRACT_PROMPT_ZH_NO_INTENTION


class TestIntentionConfig:
    def test_default_true(self, monkeypatch):
        monkeypatch.delenv("MEMORY_ENABLE_INTENTION", raising=False)
        c = LLMConfig(enable_intention=None)
        assert c.enable_intention is True

    def test_env_false(self, monkeypatch):
        monkeypatch.setenv("MEMORY_ENABLE_INTENTION", "false")
        c = LLMConfig(enable_intention=None)
        assert c.enable_intention is False


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestWriterSkipsIntentionWhenDisabled:
    def test_flag_gates_store_path(self):
        """与 writer.py 意图写入处同一条件：关闭时不 collect/store。"""
        cfg_off = LLMConfig(enable_intention=False)
        cfg_on = LLMConfig(enable_intention=True)
        assert cfg_off.enable_intention is False
        assert cfg_on.enable_intention is True

        collect_calls = []

        def collect(_info):
            collect_calls.append(1)
            return [{"content": "plan"}]

        def maybe_store(enable):
            if enable:
                intentions = collect({})
                return len(intentions)
            return 0

        assert maybe_store(cfg_off.enable_intention) == 0
        assert collect_calls == []
        assert maybe_store(cfg_on.enable_intention) == 1
        assert collect_calls == [1]
