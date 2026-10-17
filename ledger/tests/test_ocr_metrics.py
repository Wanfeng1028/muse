"""OCR Prometheus 指标测试：render 输出格式、计数正确性、端到端埋点、埋点故障隔离。"""

from __future__ import annotations

import logging
import re
import shutil

import pytest

import ledger.ocr_metrics

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128


def png_file(name="bill.png", content=PNG_BYTES, ctype="image/png"):
    return {"file": (name, content, ctype)}


@pytest.fixture(autouse=True)
def _reset_ocr_metrics():
    import importlib

    import ledger.ocr_metrics

    importlib.reload(ledger.ocr_metrics)
    yield


@pytest.fixture(autouse=True)
def _clean_ocr_env(monkeypatch):
    monkeypatch.delenv("LEDGER_OCR_PROVIDER", raising=False)
    monkeypatch.delenv("LEDGER_OCR_API_KEY", raising=False)
    yield


def _extract_value(text: str, pattern: str) -> float:
    m = re.search(pattern, text)
    assert m is not None, f"pattern not found: {pattern}\n---\n{text}"
    return float(m.group(1))


def _bucket_values(text: str) -> list[tuple[str, float]]:
    pairs: list[tuple[str, float]] = []
    for line in text.splitlines():
        m = re.match(r'^ocr_duration_seconds_bucket\{le="([^"]+)"\} ([0-9.eE+-]+)$', line)
        if m:
            pairs.append((m.group(1), float(m.group(2))))
    return pairs


def test_render_contains_help_type_and_counter_labels():
    text = ledger.ocr_metrics.render_ocr_metrics()

    assert "# HELP ocr_requests_total" in text
    assert "# TYPE ocr_requests_total counter" in text
    assert "# HELP ocr_duration_seconds" in text
    assert "# TYPE ocr_duration_seconds histogram" in text

    assert _extract_value(text, r'ocr_requests_total\{result="ok"\} ([0-9.eE+-]+)') == 0.0
    assert _extract_value(text, r'ocr_requests_total\{result="unavailable"\} ([0-9.eE+-]+)') == 0.0
    assert _extract_value(text, r'ocr_requests_total\{result="error"\} ([0-9.eE+-]+)') == 0.0

    assert _extract_value(text, r"ocr_duration_seconds_count ([0-9.eE+-]+)") == 0.0
    assert _extract_value(text, r"ocr_duration_seconds_sum ([0-9.eE+-]+)") == 0.0


def test_render_bucket_boundaries_exact():
    text = ledger.ocr_metrics.render_ocr_metrics()
    les = [le for le, _ in _bucket_values(text)]
    assert les == ["0.05", "0.1", "0.25", "0.5", "1", "2.5", "5", "10", "+Inf"]


def test_record_ocr_request_counts_and_histogram():
    ledger.ocr_metrics.record_ocr_request("ok", 0.1)
    ledger.ocr_metrics.record_ocr_request("ok", 0.3)
    ledger.ocr_metrics.record_ocr_request("unavailable", 0.2)

    text = ledger.ocr_metrics.render_ocr_metrics()

    assert _extract_value(text, r'ocr_requests_total\{result="ok"\} ([0-9.eE+-]+)') == 2.0
    assert _extract_value(text, r'ocr_requests_total\{result="unavailable"\} ([0-9.eE+-]+)') == 1.0
    assert _extract_value(text, r'ocr_requests_total\{result="error"\} ([0-9.eE+-]+)') == 0.0

    assert _extract_value(text, r"ocr_duration_seconds_count ([0-9.eE+-]+)") == 3.0
    assert _extract_value(text, r"ocr_duration_seconds_sum ([0-9.eE+-]+)") == pytest.approx(0.6)

    buckets = dict(_bucket_values(text))
    assert buckets["0.05"] == 0.0
    assert buckets["0.1"] == 1.0
    assert buckets["0.25"] == 2.0
    assert buckets["0.5"] == 3.0
    assert buckets["+Inf"] == 3.0


async def test_e2e_ocr_ok_records_metric(client):
    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 200, resp.text
    assert resp.json()["encoding"] == "ocr"

    mresp = await client.get("/api/metrics")
    assert mresp.status_code == 200, mresp.text
    value = _extract_value(mresp.text, r'ocr_requests_total\{result="ok"\} ([0-9.eE+-]+)')
    assert int(value) >= 1


async def test_e2e_ocr_unavailable_records_metric(client, monkeypatch):
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "tesseract")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)

    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 503, resp.text

    mresp = await client.get("/api/metrics")
    assert mresp.status_code == 200, mresp.text
    unavailable = _extract_value(mresp.text, r'ocr_requests_total\{result="unavailable"\} ([0-9.eE+-]+)')
    assert int(unavailable) >= 1
    ok = _extract_value(mresp.text, r'ocr_requests_total\{result="ok"\} ([0-9.eE+-]+)')
    assert int(ok) == 0


async def test_e2e_ocr_failed_records_error_metric(client, monkeypatch):
    from ledger.ocr import OcrFailedError

    class _FailLinesProvider:
        async def ocr_lines(self, image: bytes):
            raise OcrFailedError("识别失败（测试注入）")

    monkeypatch.setattr("ledger.routers.statements.get_provider", lambda: _FailLinesProvider())

    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 422, resp.text

    mresp = await client.get("/api/metrics")
    assert mresp.status_code == 200, mresp.text
    value = _extract_value(mresp.text, r'ocr_requests_total\{result="error"\} ([0-9.eE+-]+)')
    assert int(value) >= 1


async def test_metrics_failure_does_not_break_main_flow(client, monkeypatch, caplog):
    def _boom(*a, **k):
        raise RuntimeError("metrics boom")

    monkeypatch.setattr("ledger.ocr_metrics.record_ocr_request", _boom, raising=False)
    monkeypatch.setattr("ledger.routers.statements.record_ocr_request", _boom, raising=False)

    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 200, resp.text
    assert resp.json()["encoding"] == "ocr"

    assert any(r.levelno == logging.WARNING for r in caplog.records)
