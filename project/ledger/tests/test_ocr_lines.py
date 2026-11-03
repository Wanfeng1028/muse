import csv
import shutil
import subprocess

import pytest

from ledger.ocr import (
    MockOcrProvider,
    OcrFailedError,
    OcrUnavailableError,
    TesseractOcrProvider,
)


@pytest.mark.asyncio
async def test_mock_lines_shape():
    lines = await MockOcrProvider().ocr_lines(b"fake-bytes")
    assert isinstance(lines, list)
    assert len(lines) >= 4
    assert all(isinstance(line, str) for line in lines)
    header = lines[0]
    assert "交易时间" in header
    assert "金额(元)" in header


@pytest.mark.asyncio
async def test_mock_lines_empty_image():
    with pytest.raises(OcrFailedError):
        await MockOcrProvider().ocr_lines(b"")


@pytest.mark.asyncio
async def test_mock_lines_parseable():
    lines = await MockOcrProvider().ocr_lines(b"fake-bytes")
    rows = list(csv.reader(lines))
    assert len(rows) >= 4
    header = rows[0]
    assert "交易时间" in header
    assert "金额(元)" in header
    for row in rows[1:]:
        assert len(row) == len(header)


@pytest.mark.asyncio
async def test_tesseract_missing_binary(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    provider = TesseractOcrProvider()
    with pytest.raises(OcrUnavailableError) as exc_info:
        await provider.ocr_lines(b"x")
    assert "apt install tesseract" in str(exc_info.value)


@pytest.mark.asyncio
async def test_tesseract_timeout(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *a, **k: "/usr/bin/tesseract")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="tesseract", timeout=30)

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = TesseractOcrProvider(timeout=30)
    monkeypatch.setattr(provider, "_preprocess", lambda b: b, raising=False)
    with pytest.raises(OcrUnavailableError) as exc_info:
        await provider.ocr_lines(b"x")
    assert "超时" in str(exc_info.value)


@pytest.mark.asyncio
async def test_tesseract_nonzero_exit(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *a, **k: "/usr/bin/tesseract")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout=b"", stderr=b"Error: failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = TesseractOcrProvider()
    monkeypatch.setattr(provider, "_preprocess", lambda b: b, raising=False)
    with pytest.raises(OcrUnavailableError):
        await provider.ocr_lines(b"x")


@pytest.mark.asyncio
async def test_tesseract_empty_image():
    with pytest.raises(OcrFailedError):
        await TesseractOcrProvider().ocr_lines(b"")


@pytest.mark.asyncio
async def test_tesseract_success_lines(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *a, **k: "/usr/bin/tesseract")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=b"line1\n\n  line2  \n", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = TesseractOcrProvider()
    monkeypatch.setattr(provider, "_preprocess", lambda b: b, raising=False)
    lines = await provider.ocr_lines(b"x")
    assert lines == ["line1", "line2"]
