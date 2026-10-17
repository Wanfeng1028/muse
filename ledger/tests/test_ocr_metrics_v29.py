import importlib
import re
import shutil

import pytest

import ledger.ocr_metrics
from ledger.ocr import OcrEmptyError, OcrFailedError


@pytest.fixture(autouse=True)
def _reset_ocr_metrics():
    importlib.reload(ledger.ocr_metrics)


@pytest.fixture(autouse=True)
def _clean_ocr_env(monkeypatch):
    monkeypatch.delenv("LEDGER_OCR_PROVIDER", raising=False)
    monkeypatch.delenv("LEDGER_OCR_API_KEY", raising=False)


def png_file(name="sample.png", content=None, ctype="image/png"):
    if content is None:
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    return {"file": (name, content, ctype)}


def _extract_value(text, metric, labels=None):
    for line in text.splitlines():
        if not line.startswith(metric):
            continue
        if labels is not None:
            if not all(f'{k}="{v}"' in line for k, v in labels.items()):
                continue
        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            continue
        try:
            return float(parts[1])
        except ValueError:
            continue
    return None


def _bucket_values(text, metric):
    values = {}
    for line in text.splitlines():
        if not line.startswith(metric + "_bucket"):
            continue
        m = re.search(r'le="([^"]+)"', line)
        if not m:
            continue
        le = m.group(1)
        parts = line.rsplit(" ", 1)
        try:
            values[le] = float(parts[1])
        except ValueError:
            continue
    return values


def test_render_metric_names_and_help():
    text = ledger.ocr_metrics.render_ocr_metrics()

    for metric in (
        "ledger_ocr_requests_total",
        "ledger_ocr_failures_total",
        "ledger_ocr_duration_seconds",
        "ledger_ocr_confidence_avg",
    ):
        assert f"# HELP {metric} " in text
        assert f"# TYPE {metric} " in text

    assert "counter" in text
    assert "histogram" in text
    assert "gauge" in text

    for result in ("ok", "empty", "error"):
        assert (
            _extract_value(
                text,
                "ledger_ocr_requests_total",
                {"result": result},
            )
            == 0.0
        )

    for reason in (
        "unavailable",
        "unsupported",
        "invalid",
        "oversize",
        "internal",
    ):
        assert (
            _extract_value(
                text,
                "ledger_ocr_failures_total",
                {"reason": reason},
            )
            == 0.0
        )

    assert _extract_value(text, "ledger_ocr_confidence_avg") == 0.0


def test_record_request_result_normalization():
    ledger.ocr_metrics.record_ocr_request("bogus", 0.1)
    ledger.ocr_metrics.record_ocr_request("ok", -5)

    text = ledger.ocr_metrics.render_ocr_metrics()

    assert (
        _extract_value(
            text,
            "ledger_ocr_requests_total",
            {"result": "error"},
        )
        == 1.0
    )
    assert (
        _extract_value(
            text,
            "ledger_ocr_requests_total",
            {"result": "ok"},
        )
        == 1.0
    )
    assert _extract_value(text, "ledger_ocr_duration_seconds_sum") == pytest.approx(0.1)


def test_record_failure_reason_normalization():
    ledger.ocr_metrics.record_ocr_failure("bogus")
    ledger.ocr_metrics.record_ocr_failure("oversize")

    text = ledger.ocr_metrics.render_ocr_metrics()

    assert (
        _extract_value(
            text,
            "ledger_ocr_failures_total",
            {"reason": "internal"},
        )
        == 1.0
    )
    assert (
        _extract_value(
            text,
            "ledger_ocr_failures_total",
            {"reason": "oversize"},
        )
        == 1.0
    )


def test_record_confidence_validation():
    for bad in (None, float("nan"), "x", -0.1, 1.5):
        ledger.ocr_metrics.record_ocr_confidence(bad)

    text = ledger.ocr_metrics.render_ocr_metrics()
    assert _extract_value(text, "ledger_ocr_confidence_avg") == 0.0

    ledger.ocr_metrics.record_ocr_confidence(0.8)
    ledger.ocr_metrics.record_ocr_confidence(0.6)

    text = ledger.ocr_metrics.render_ocr_metrics()
    assert _extract_value(text, "ledger_ocr_confidence_avg") == pytest.approx(0.7)


def test_histogram_buckets():
    ledger.ocr_metrics.record_ocr_request("ok", 0.1)
    ledger.ocr_metrics.record_ocr_request("ok", 0.3)
    ledger.ocr_metrics.record_ocr_request("ok", 0.2)

    text = ledger.ocr_metrics.render_ocr_metrics()

    assert _extract_value(text, "ledger_ocr_duration_seconds_count") == 3.0
    assert _extract_value(text, "ledger_ocr_duration_seconds_sum") == pytest.approx(0.6)

    buckets = _bucket_values(text, "ledger_ocr_duration_seconds")
    assert buckets.get("0.1") == 1.0
    assert buckets.get("0.25") == 2.0
    assert buckets.get("0.5") == 3.0
    assert buckets.get("+Inf") == 3.0


async def test_e2e_ok_records_metric(client):
    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 200

    metrics = await client.get("/api/metrics")
    text = metrics.text

    value = _extract_value(
        text,
        "ledger_ocr_requests_total",
        {"result": "ok"},
    )
    assert value is not None
    assert value >= 1.0


async def test_e2e_empty_records_empty(client, monkeypatch):
    class EmptyProvider:
        def ocr_lines(self, *args, **kwargs):
            raise OcrEmptyError("tesseract 未识别出任何文本")

    monkeypatch.setattr(
        "ledger.routers.statements.get_provider",
        lambda: EmptyProvider(),
    )

    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 422

    metrics = await client.get("/api/metrics")
    text = metrics.text

    empty = _extract_value(
        text,
        "ledger_ocr_requests_total",
        {"result": "empty"},
    )
    assert empty is not None
    assert empty >= 1.0

    err = _extract_value(
        text,
        "ledger_ocr_requests_total",
        {"result": "error"},
    )
    assert err == 0.0


async def test_e2e_415_unsupported(client):
    resp = await client.post(
        "/api/statements/ocr",
        files=png_file(name="x.txt", ctype="text/plain"),
    )
    assert resp.status_code == 415

    metrics = await client.get("/api/metrics")
    text = metrics.text

    err = _extract_value(
        text,
        "ledger_ocr_requests_total",
        {"result": "error"},
    )
    assert err is not None
    assert err >= 1.0

    reason = _extract_value(
        text,
        "ledger_ocr_failures_total",
        {"reason": "unsupported"},
    )
    assert reason is not None
    assert reason >= 1.0


async def test_e2e_413_oversize(client):
    content = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024)
    resp = await client.post(
        "/api/statements/ocr",
        files=png_file(name="big.png", content=content),
    )
    assert resp.status_code == 413

    metrics = await client.get("/api/metrics")
    text = metrics.text

    reason = _extract_value(
        text,
        "ledger_ocr_failures_total",
        {"reason": "oversize"},
    )
    assert reason is not None
    assert reason >= 1.0


async def test_e2e_400_invalid(client):
    content = b"ZZZZ" + b"\x00" * 64
    resp = await client.post(
        "/api/statements/ocr",
        files=png_file(name="bad.png", content=content),
    )
    assert resp.status_code == 400

    metrics = await client.get("/api/metrics")
    text = metrics.text

    reason = _extract_value(
        text,
        "ledger_ocr_failures_total",
        {"reason": "invalid"},
    )
    assert reason is not None
    assert reason >= 1.0


async def test_e2e_503_unavailable(client, monkeypatch):
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "tesseract")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)

    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 503

    metrics = await client.get("/api/metrics")
    text = metrics.text

    err = _extract_value(
        text,
        "ledger_ocr_requests_total",
        {"result": "error"},
    )
    assert err is not None
    assert err >= 1.0

    reason = _extract_value(
        text,
        "ledger_ocr_failures_total",
        {"reason": "unavailable"},
    )
    assert reason is not None
    assert reason >= 1.0


async def test_e2e_422_failed_internal(client, monkeypatch):
    class FailedProvider:
        def ocr_lines(self, *args, **kwargs):
            raise OcrFailedError("识别失败（测试注入）")

    monkeypatch.setattr(
        "ledger.routers.statements.get_provider",
        lambda: FailedProvider(),
    )

    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 422

    metrics = await client.get("/api/metrics")
    text = metrics.text

    err = _extract_value(
        text,
        "ledger_ocr_requests_total",
        {"result": "error"},
    )
    assert err is not None
    assert err >= 1.0

    reason = _extract_value(
        text,
        "ledger_ocr_failures_total",
        {"reason": "internal"},
    )
    assert reason is not None
    assert reason >= 1.0


async def test_fault_isolation(client, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("metrics boom")

    monkeypatch.setattr(ledger.ocr_metrics, "record_ocr_request", boom, raising=False)
    monkeypatch.setattr(ledger.ocr_metrics, "record_ocr_failure", boom, raising=False)
    monkeypatch.setattr(ledger.ocr_metrics, "record_ocr_confidence", boom, raising=False)
    monkeypatch.setattr("ledger.routers.statements.record_ocr_request", boom, raising=False)
    monkeypatch.setattr("ledger.routers.statements.record_ocr_failure", boom, raising=False)
    monkeypatch.setattr("ledger.routers.statements.record_ocr_confidence", boom, raising=False)

    import logging

    caplog.set_level(logging.WARNING)

    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 200
    assert resp.json().get("encoding") == "ocr"

    assert any(record.levelno >= logging.WARNING for record in caplog.records)


async def test_confidence_gauge_zero_without_sample(client):
    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 200

    metrics = await client.get("/api/metrics")
    text = metrics.text

    assert _extract_value(text, "ledger_ocr_confidence_avg") == 0.0
