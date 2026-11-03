"""tests for bills OCR full-path Prometheus metrics."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from ledger.ocr_metrics import (
    record_bills_ocr_failure,
    record_bills_ocr_request,
    record_ocr_failure,
    record_ocr_request,
    render_bills_ocr_metrics,
    render_ocr_metrics,
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_test_db(app):
    """复用 conftest 的 session 级 app fixture，确保 LEDGER_DB 与表结构已初始化。"""
    return app


class _FakeCandidate(dict):
    pass


class _FakeResult:
    def __init__(self, mock: bool = True) -> None:
        self.merchant = "测试商家"
        self.amount_cents = 1234
        self.occurred_on = "2024-01-01"
        self.raw_text = "raw"
        self.provider = "mock"
        self.mock = mock
        self.field_confidence = {"merchant": 0.9}
        self.candidates = [
            {"category_name": "餐饮", "confidence": 0.9},
        ]


class _FakeProvider:
    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc

    async def recognize(self, raw: bytes, filename: str, content_type: str) -> _FakeResult:
        if self._exc is not None:
            raise self._exc
        return _FakeResult()


def _metric_value(text: str, name: str, labels: dict[str, str] | None = None) -> float:
    labels = labels or {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([0-9eE+\-.]+)$", line)
        if not match:
            continue
        metric = match.group(1)
        label_part = match.group(2) or ""
        if metric != name:
            continue
        ok = True
        for key, value in labels.items():
            if f'{key}="{value}"' not in label_part:
                ok = False
                break
        if ok:
            return float(match.group(3))
    raise AssertionError(f"metric not found: {name} {labels}")


def _bills_text() -> str:
    return render_bills_ocr_metrics()


def test_bills_metrics_prefix_and_help_present() -> None:
    text = _bills_text()
    assert "# HELP ledger_bills_ocr_requests_total" in text
    assert "# TYPE ledger_bills_ocr_requests_total counter" in text
    assert "# HELP ledger_bills_ocr_failures_total" in text
    assert "# HELP ledger_bills_ocr_duration_seconds" in text
    assert "# HELP ledger_bills_ocr_confidence_avg" in text


def test_bills_and_statements_instances_are_isolated() -> None:
    before_bills = _metric_value(_bills_text(), "ledger_bills_ocr_requests_total", {"result": "ok"})
    before_statements = _metric_value(render_ocr_metrics(), "ledger_ocr_requests_total", {"result": "ok"})

    record_bills_ocr_request("ok", 0.01)
    after_bills = _metric_value(_bills_text(), "ledger_bills_ocr_requests_total", {"result": "ok"})
    after_statements = _metric_value(render_ocr_metrics(), "ledger_ocr_requests_total", {"result": "ok"})
    assert after_bills == before_bills + 1
    assert after_statements == before_statements

    record_ocr_request("ok", 0.01)
    after_bills2 = _metric_value(_bills_text(), "ledger_bills_ocr_requests_total", {"result": "ok"})
    after_statements2 = _metric_value(render_ocr_metrics(), "ledger_ocr_requests_total", {"result": "ok"})
    assert after_bills2 == after_bills
    assert after_statements2 == after_statements + 1

    record_bills_ocr_failure("invalid")
    assert _metric_value(_bills_text(), "ledger_bills_ocr_failures_total", {"reason": "invalid"}) >= 1
    record_ocr_failure("oversize")
    assert _metric_value(render_ocr_metrics(), "ledger_ocr_failures_total", {"reason": "oversize"}) >= 1


def _build_client(monkeypatch, provider_factory):
    import ledger.routers.bills as bills_module

    monkeypatch.setattr(bills_module, "get_provider", provider_factory)

    from ledger.main import app

    return TestClient(app)


def test_bills_ocr_ok_path_increments_ok(monkeypatch) -> None:
    client = _build_client(monkeypatch, lambda: _FakeProvider())
    before = _metric_value(_bills_text(), "ledger_bills_ocr_requests_total", {"result": "ok"})
    resp = client.post(
        "/api/bills/ocr",
        files={"file": ("bill.png", b"\x89PNG\r\n\x1a\nDATA", "image/png")},
    )
    assert resp.status_code == 200, resp.text
    after = _metric_value(_bills_text(), "ledger_bills_ocr_requests_total", {"result": "ok"})
    assert after == before + 1


def test_bills_ocr_unsupported_reason(monkeypatch) -> None:
    client = _build_client(monkeypatch, lambda: _FakeProvider())
    before = _metric_value(_bills_text(), "ledger_bills_ocr_failures_total", {"reason": "unsupported"})
    resp = client.post(
        "/api/bills/ocr",
        files={"file": ("bill.txt", b"not an image", "text/plain")},
    )
    assert resp.status_code == 422
    after = _metric_value(_bills_text(), "ledger_bills_ocr_failures_total", {"reason": "unsupported"})
    assert after == before + 1


def test_bills_ocr_oversize_reason(monkeypatch) -> None:
    client = _build_client(monkeypatch, lambda: _FakeProvider())
    before = _metric_value(_bills_text(), "ledger_bills_ocr_failures_total", {"reason": "oversize"})
    big = b"\x89PNG\r\n\x1a\n" + b"a" * (5 * 1024 * 1024 + 10)
    resp = client.post(
        "/api/bills/ocr",
        files={"file": ("bill.png", big, "image/png")},
    )
    assert resp.status_code == 422
    after = _metric_value(_bills_text(), "ledger_bills_ocr_failures_total", {"reason": "oversize"})
    assert after == before + 1


def test_bills_ocr_invalid_reason_empty_body(monkeypatch) -> None:
    client = _build_client(monkeypatch, lambda: _FakeProvider())
    before = _metric_value(_bills_text(), "ledger_bills_ocr_failures_total", {"reason": "invalid"})
    resp = client.post(
        "/api/bills/ocr",
        files={"file": ("bill.png", b"", "image/png")},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "图片内容为空"
    after = _metric_value(_bills_text(), "ledger_bills_ocr_failures_total", {"reason": "invalid"})
    assert after == before + 1


def test_bills_ocr_unavailable_reason(monkeypatch) -> None:
    from ledger.ocr import OcrNotConfiguredError

    client = _build_client(
        monkeypatch,
        lambda: _FakeProvider(exc=OcrNotConfiguredError("not configured")),
    )
    before = _metric_value(_bills_text(), "ledger_bills_ocr_failures_total", {"reason": "unavailable"})
    resp = client.post(
        "/api/bills/ocr",
        files={"file": ("bill.png", b"\x89PNG\r\n\x1a\nDATA", "image/png")},
    )
    assert resp.status_code == 422
    after = _metric_value(_bills_text(), "ledger_bills_ocr_failures_total", {"reason": "unavailable"})
    assert after == before + 1


def test_bills_ocr_internal_reason(monkeypatch) -> None:
    client = _build_client(monkeypatch, lambda: _FakeProvider(exc=RuntimeError("boom")))
    before = _metric_value(_bills_text(), "ledger_bills_ocr_failures_total", {"reason": "internal"})
    resp = client.post(
        "/api/bills/ocr",
        files={"file": ("bill.png", b"\x89PNG\r\n\x1a\nDATA", "image/png")},
    )
    # 未处理异常由 RequestIdMiddleware 兜底为 500 JSON，不会抛到 TestClient
    assert resp.status_code == 500
    after = _metric_value(_bills_text(), "ledger_bills_ocr_failures_total", {"reason": "internal"})
    assert after == before + 1


def test_bills_ocr_metrics_failure_is_isolated(monkeypatch) -> None:
    import ledger.routers.bills as bills_module

    monkeypatch.setattr(bills_module, "get_provider", lambda: _FakeProvider())

    def _boom(*args, **kwargs):
        raise RuntimeError("metrics down")

    monkeypatch.setattr(bills_module, "record_bills_ocr_request", _boom)

    from ledger.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/bills/ocr",
        files={"file": ("bill.png", b"\x89PNG\r\n\x1a\nDATA", "image/png")},
    )
    assert resp.status_code == 200, resp.text


def test_metrics_endpoint_contains_bills_ocr_lines(monkeypatch) -> None:
    from ledger.main import app

    record_bills_ocr_request("ok", 0.01)
    client = TestClient(app)
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert re.search(r"^ledger_bills_ocr_requests_total\{result=\"ok\"\}\s+\d+$", text, re.M)
    assert "# HELP ledger_bills_ocr_requests_total" in text


def test_module_level_ocr_functions_still_work() -> None:
    before = _metric_value(render_ocr_metrics(), "ledger_ocr_requests_total", {"result": "ok"})
    record_ocr_request("ok", 0.01)
    after = _metric_value(render_ocr_metrics(), "ledger_ocr_requests_total", {"result": "ok"})
    assert after == before + 1
    assert "# HELP ledger_ocr_requests_total OCR 全路径请求总数（按结果分组）" in render_ocr_metrics()
