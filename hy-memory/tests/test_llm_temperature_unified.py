"""LLM 生成参数必须统一走用户配置，任何调用点都不许写死。

背景：Opus 5 网关只接受 `temperature=1` 或**干脆不传**，传 0 / 0.1 / 0.3 / 0.6 都会 400。
而 SDK 里此前有三类绕过用户配置的写法：

1. 调用点写死数值（abstractor 0.3/0.4/0.2、reflector 0.1/0.3、merger 0.3）
2. 子配置 dataclass 默认值写死（emotion_analyzer 0.1、intention_detector 0.2/0.1、
   topic_summary 0.3、episode_summary 0.3）
3. provider 入口默认值 0.7 —— 调用方不传就落到 0.7，与用户配置完全无关

结果是 `MEMORY_LLM_TEMPERATURE` 只对少数几条路径生效，换网关时其余路径全挂。
这些测试锁死"唯一收敛点在 provider"这条不变量。
"""

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hy_memory.agent.llm_provider import LLMProvider
from hy_memory.config import LLMConfig, MemoryConfig

_SRC = Path(__file__).resolve().parent.parent / "hy_memory"


# ======================================================================
# 静态守卫：不允许再出现写死的 temperature
# ======================================================================

class TestNoHardcodedTemperature:
    def test_no_numeric_temperature_at_call_sites(self):
        """`temperature=0.3` 这类字面量一律不允许。"""
        offenders = []
        for py in _SRC.rglob("*.py"):
            for i, line in enumerate(py.read_text().splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # 只查实参/默认值里的数字字面量
                if "temperature=" in stripped:
                    after = stripped.split("temperature=", 1)[1][:6]
                    if after and after[0].isdigit():
                        offenders.append(f"{py.relative_to(_SRC)}:{i}: {stripped}")
        assert not offenders, (
            "这些调用点写死了 temperature，会绕过用户配置：\n" + "\n".join(offenders)
        )

    def test_no_float_annotated_temperature_defaults(self):
        """子配置里 `temperature: float = 0.3` 也是绕过配置的写法。"""
        offenders = []
        for py in _SRC.rglob("*.py"):
            for i, line in enumerate(py.read_text().splitlines(), 1):
                s = line.strip()
                if s.startswith("#"):
                    continue
                if ("temperature" in s and ": float" in s and "=" in s
                        and "Optional" not in s):
                    val = s.split("=", 1)[1].strip()
                    if val and val[0].isdigit():
                        offenders.append(f"{py.relative_to(_SRC)}:{i}: {s}")
        assert not offenders, (
            "这些默认值写死了 temperature：\n" + "\n".join(offenders)
        )

    def test_provider_entrypoints_default_to_none(self):
        """provider 的入口默认值必须是 None（= 跟配置走），不能是 0.7。"""
        for name in ("complete", "complete_messages", "chat",
                     "_call_llm", "_chat_completions"):
            param = inspect.signature(getattr(LLMProvider, name)).parameters["temperature"]
            assert param.default is None, (
                f"LLMProvider.{name} 的 temperature 默认值是 {param.default!r}，"
                "调用方不传时会绕过用户配置"
            )


# ======================================================================
# 配置解析
# ======================================================================

class TestTemperatureResolution:
    def _provider(self, *, temperature=None, omit=False):
        cfg = MemoryConfig()
        cfg.llm.api_key = "sk-test"
        cfg.llm.model = "opus-5"
        if temperature is not None:
            cfg.llm.temperature = temperature
        cfg.llm.omit_temperature = omit
        return LLMProvider(cfg)

    def test_call_site_none_falls_back_to_config(self):
        p = self._provider(temperature=1.0)
        assert p._resolve_temperature(None) == 1.0

    def test_explicit_call_site_value_wins(self):
        """少数确实需要特定温度的场景仍可显式指定。"""
        p = self._provider(temperature=1.0)
        assert p._resolve_temperature(0.2) == 0.2

    def test_omit_config_resolves_to_none(self):
        p = self._provider(omit=True)
        assert p._resolve_temperature(None) is None

    def test_zero_is_not_treated_as_unset(self):
        """0.0 是合法温度，不能被 falsy 判断吞掉。"""
        p = self._provider(temperature=1.0)
        assert p._resolve_temperature(0.0) == 0.0


class TestConfigEnv:
    def test_env_numeric(self, monkeypatch):
        monkeypatch.setenv("MEMORY_LLM_TEMPERATURE", "1.0")
        cfg = LLMConfig()
        assert cfg.temperature == 1.0 and cfg.omit_temperature is False

    @pytest.mark.parametrize("val", ["none", "None", "null", "omit", "unset", ""])
    def test_env_omit_spellings(self, monkeypatch, val):
        monkeypatch.setenv("MEMORY_LLM_TEMPERATURE", val)
        assert LLMConfig().omit_temperature is True

    def test_env_explicit_omit_flag(self, monkeypatch):
        monkeypatch.setenv("MEMORY_LLM_OMIT_TEMPERATURE", "true")
        assert LLMConfig().omit_temperature is True

    def test_default_unchanged(self, monkeypatch):
        """默认行为不变（0.1、照常发送），避免静默改变现有部署。"""
        monkeypatch.delenv("MEMORY_LLM_TEMPERATURE", raising=False)
        monkeypatch.delenv("MEMORY_LLM_OMIT_TEMPERATURE", raising=False)
        cfg = LLMConfig()
        assert cfg.temperature == 0.1 and cfg.omit_temperature is False


# ======================================================================
# 落到真实请求 payload
# ======================================================================

class TestRequestPayload:
    """最终判据：请求体里到底带没带、带的是什么。"""

    def _capture(self):
        seen = []

        def _fake_client(*a, **kw):
            cli = MagicMock()

            async def _create(**kwargs):
                seen.append(kwargs)
                m = MagicMock()
                m.choices = [MagicMock(
                    message=MagicMock(content="ok", tool_calls=None),
                    finish_reason="stop",
                )]
                m.usage = MagicMock(
                    prompt_tokens=1, completion_tokens=1, total_tokens=2,
                )
                return m

            cli.chat.completions.create = _create
            return cli

        return seen, _fake_client

    async def _run(self, *, temperature=None, omit=False, call_kwargs=None):
        cfg = MemoryConfig()
        cfg.llm.api_key = "sk-test"
        cfg.llm.model = "opus-5"
        if temperature is not None:
            cfg.llm.temperature = temperature
        cfg.llm.omit_temperature = omit
        provider = LLMProvider(cfg)

        seen, fake = self._capture()
        with patch("openai.AsyncOpenAI", fake):
            await provider.complete(
                prompt="hi", max_tokens=10, **(call_kwargs or {}),
            )
        return seen[0]

    @pytest.mark.asyncio
    async def test_configured_value_is_sent(self):
        payload = await self._run(temperature=1.0)
        assert payload["temperature"] == 1.0

    @pytest.mark.asyncio
    async def test_omit_removes_key_entirely(self):
        """Opus 5 的诉求：参数**整个不出现**，而不是发个默认值。"""
        payload = await self._run(omit=True)
        assert "temperature" not in payload

    @pytest.mark.asyncio
    async def test_call_site_override_still_works(self):
        payload = await self._run(temperature=1.0, call_kwargs={"temperature": 0.2})
        assert payload["temperature"] == 0.2

    @pytest.mark.asyncio
    async def test_max_tokens_still_sent(self):
        """省略 temperature 不能顺手把别的参数弄丢。"""
        payload = await self._run(omit=True)
        assert payload["max_tokens"] == 10
        assert payload["model"] == "opus-5"


# ======================================================================
# coding 路径的独立解析器
# ======================================================================

class TestCodingPathsRespectConfig:
    """coding 下三个模块此前各自 `getattr(..., 0.1)` 兜底，会绕过 omit。"""

    class _Provider:
        def __init__(self, temperature, omit):
            self.config = MagicMock()
            self.config.llm.temperature = temperature
            self.config.llm.omit_temperature = omit

    @pytest.mark.parametrize("module_path", [
        "hy_memory.coding.extractor",
        "hy_memory.coding.reconciler",
        "hy_memory.coding.fact_reconciler",
    ])
    def test_resolver_honors_omit_and_value(self, module_path):
        import importlib

        mod = importlib.import_module(module_path)
        fn = mod._resolve_configured_temperature
        assert fn(self._Provider(0.1, True)) is None, "omit 时必须返回 None"
        assert fn(self._Provider(1.0, False)) == 1.0

    def test_judge_resolver_honors_omit(self):
        from hy_memory.coding.judge import _resolve_llm_temperature

        assert _resolve_llm_temperature(self._Provider(0.1, True)) is None
        assert _resolve_llm_temperature(self._Provider(1.0, False)) == 1.0
