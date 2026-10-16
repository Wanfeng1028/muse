from __future__ import annotations

import shutil
import subprocess
from datetime import date

import pytest

from ledger.ocr import (
    OcrFailedError,
    OcrNotConfiguredError,
    TesseractOcrProvider,
    get_provider,
)

NEEDS_TESSERACT = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="未安装 tesseract，跳过真实识别测试",
)


def _provider(monkeypatch: pytest.MonkeyPatch) -> TesseractOcrProvider:
    monkeypatch.delenv("LEDGER_OCR_LANG", raising=False)
    monkeypatch.delenv("LEDGER_OCR_TIMEOUT", raising=False)
    return TesseractOcrProvider()


def test_parse_amount_cny_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    text = "星巴克臻选\n拿铁 ￥68.00\n2026-10-16"
    merchant, amount_cents, occurred_on, conf = provider._parse(text)
    assert amount_cents == 6800
    assert conf["amount_cents"] >= 0.8
    assert merchant == "星巴克臻选"
    assert occurred_on == "2026-10-16"


def test_parse_amount_picks_max(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    text = "小计 12.00\n合计 58.50\n找零 41.50"
    _merchant, amount_cents, _occurred_on, conf = provider._parse(text)
    assert amount_cents == 5850
    assert conf["amount_cents"] >= 0.8


def test_parse_date_iso(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    _merchant, _amount, occurred_on, conf = provider._parse("订单 2026-10-16")
    assert occurred_on == "2026-10-16"
    assert conf["occurred_on"] >= 0.6


def test_parse_date_chinese(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    _merchant, _amount, occurred_on, _conf = provider._parse("消费 2026年10月16日")
    assert occurred_on == "2026-10-16"


def test_parse_date_invalid_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    text = "日期 2026-13-99\n2026-10-15"
    _merchant, _amount, occurred_on, _conf = provider._parse(text)
    assert occurred_on == "2026-10-15"


def test_parse_merchant_first_line(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    merchant, _amount, _occurred_on, _conf = provider._parse(" 海底捞火锅 ")
    assert merchant == "海底捞火锅"


def test_parse_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    merchant, amount_cents, occurred_on, conf = provider._parse("")
    assert amount_cents == 0
    assert conf["merchant"] == 0.0
    assert conf["amount_cents"] == 0.0
    assert conf["occurred_on"] == 0.0
    assert occurred_on == date.today().isoformat()
    assert merchant == ""


def test_init_lang_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEDGER_OCR_LANG", raising=False)
    monkeypatch.delenv("LEDGER_OCR_TIMEOUT", raising=False)
    provider = TesseractOcrProvider()
    assert provider._lang == "chi_sim+eng"


def test_init_lang_env_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEDGER_OCR_LANG", "eng")
    monkeypatch.delenv("LEDGER_OCR_TIMEOUT", raising=False)
    provider = TesseractOcrProvider()
    assert provider._lang == "eng"


def test_init_timeout_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEDGER_OCR_TIMEOUT", raising=False)
    monkeypatch.delenv("LEDGER_OCR_LANG", raising=False)
    provider = TesseractOcrProvider()
    assert provider._timeout == 30


def test_init_timeout_invalid_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEDGER_OCR_LANG", raising=False)

    monkeypatch.setenv("LEDGER_OCR_TIMEOUT", "abc")
    provider = TesseractOcrProvider()
    assert provider._timeout == 30

    monkeypatch.setenv("LEDGER_OCR_TIMEOUT", "2")
    provider2 = TesseractOcrProvider()
    assert provider2._timeout == 30


def test_get_provider_tesseract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "tesseract")
    monkeypatch.delenv("LEDGER_OCR_LANG", raising=False)
    monkeypatch.delenv("LEDGER_OCR_TIMEOUT", raising=False)
    provider = get_provider()
    assert isinstance(provider, TesseractOcrProvider)


def test_get_provider_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "nope")
    with pytest.raises(ValueError) as exc_info:
        get_provider()
    assert "tesseract" in str(exc_info.value)


@pytest.mark.asyncio
async def test_missing_binary_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(OcrNotConfiguredError) as exc_info:
        await provider.recognize(b"\x89PNG fake", "a.png", "image/png")
    assert "tesseract-ocr" in str(exc_info.value)


@pytest.mark.asyncio
async def test_empty_image(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    with pytest.raises(OcrFailedError):
        await provider.recognize(b"", "empty.png", "image/png")


@pytest.mark.asyncio
async def test_subprocess_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/tesseract")

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="tesseract", timeout=30)

    monkeypatch.setattr(subprocess, "run", _raise)
    with pytest.raises(OcrFailedError) as exc_info:
        await provider.recognize(b"fake-image-bytes", "a.png", "image/png")
    assert "超时" in str(exc_info.value)


@pytest.mark.asyncio
async def test_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/tesseract")

    def _run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout=b"", stderr=b"Error: failed")

    monkeypatch.setattr(subprocess, "run", _run)
    with pytest.raises(OcrFailedError) as exc_info:
        await provider.recognize(b"fake-image-bytes", "a.png", "image/png")
    assert "1" in str(exc_info.value)


@pytest.mark.asyncio
async def test_empty_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/tesseract")

    def _run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=b" \n", stderr=b"")

    monkeypatch.setattr(subprocess, "run", _run)
    with pytest.raises(OcrFailedError) as exc_info:
        await provider.recognize(b"fake-image-bytes", "a.png", "image/png")
    assert "未识别出" in str(exc_info.value)


@NEEDS_TESSERACT
@pytest.mark.asyncio
async def test_recognize_real_image(monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO

    from PIL import Image, ImageDraw

    provider = _provider(monkeypatch)

    image = Image.new("RGB", (600, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 40), "TEST MART", fill="black")
    draw.text((20, 120), "TOTAL 123.45", fill="black")
    draw.text((20, 200), "2026-10-16", fill="black")
    buf = BytesIO()
    image.save(buf, format="PNG")
    payload = buf.getvalue()

    result = await provider.recognize(payload, "receipt.png", "image/png")
    assert result.provider == "tesseract"
    assert result.mock is False
    assert result.amount_cents == 12345
    assert result.occurred_on == "2026-10-16"
    assert "merchant" in result.field_confidence
    assert "amount_cents" in result.field_confidence
    assert "occurred_on" in result.field_confidence
