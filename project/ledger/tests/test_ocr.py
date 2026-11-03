"""ocr 模块单元测试：Mock 固定结果、Env 诚实报错、get_provider 选择逻辑。"""

from __future__ import annotations

import re

import pytest

from ledger.ocr import (
    EnvOcrProvider,
    MockOcrProvider,
    OcrFailedError,
    OcrNotConfiguredError,
    get_provider,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@pytest.fixture(autouse=True)
def _clean_ocr_env(monkeypatch):
    """用例间隔离 OCR 环境变量。"""
    monkeypatch.delenv("LEDGER_OCR_PROVIDER", raising=False)
    monkeypatch.delenv("LEDGER_OCR_API_KEY", raising=False)
    yield


async def test_mock_returns_fixed_fields():
    result = await MockOcrProvider().recognize(b"img", "a.jpg", "image/jpeg")
    assert result.merchant == "星巴克臻选"
    assert result.amount_cents == 6800
    assert DATE_RE.match(result.occurred_on)
    assert result.provider == "mock"
    assert result.mock is True
    assert result.raw_text == "星巴克臻选\n拿铁 68.00\n2026-10-16"


async def test_mock_occurred_on_is_valid_date():
    result = await MockOcrProvider().recognize(b"img", "a.jpg", "image/jpeg")
    assert DATE_RE.match(result.occurred_on)
    from datetime import date

    y, m, d = result.occurred_on.split("-")
    date(int(y), int(m), int(d))


async def test_mock_same_result_for_different_inputs():
    p = MockOcrProvider()
    r1 = await p.recognize(b"aaaa", "a.jpg", "image/jpeg")
    r2 = await p.recognize(b"bbbbbb", "b.png", "image/png")
    assert r1.merchant == r2.merchant
    assert r1.amount_cents == r2.amount_cents
    assert r1.candidates == r2.candidates
    assert r1.mock == r2.mock is True


async def test_mock_empty_image_raises():
    with pytest.raises(OcrFailedError) as ei:
        await MockOcrProvider().recognize(b"", "a.jpg", "image/jpeg")
    assert "图片内容为空" in str(ei.value)


async def test_mock_candidates_confidence_in_range():
    result = await MockOcrProvider().recognize(b"img", "a.jpg", "image/jpeg")
    assert result.candidates
    for c in result.candidates:
        assert "category_name" in c
        assert isinstance(c["confidence"], float)
        assert 0.0 <= c["confidence"] <= 1.0


async def test_env_without_key_raises_not_configured():
    with pytest.raises(OcrNotConfiguredError) as ei:
        await EnvOcrProvider().recognize(b"img", "a.jpg", "image/jpeg")
    assert "未配置真实 OCR 服务" in str(ei.value)


async def test_env_with_key_raises_not_implemented(monkeypatch):
    monkeypatch.setenv("LEDGER_OCR_API_KEY", "fake-key")
    with pytest.raises(NotImplementedError):
        await EnvOcrProvider().recognize(b"img", "a.jpg", "image/jpeg")


def test_get_provider_default_is_mock():
    assert isinstance(get_provider(), MockOcrProvider)


def test_get_provider_env_returns_env_provider(monkeypatch):
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "env")
    assert isinstance(get_provider(), EnvOcrProvider)


def test_get_provider_unknown_raises(monkeypatch):
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "xxx")
    with pytest.raises(ValueError) as ei:
        get_provider()
    assert "未知的 OCR 提供商" in str(ei.value)


def test_get_provider_case_insensitive(monkeypatch):
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "  MOCK ")
    assert isinstance(get_provider(), MockOcrProvider)
