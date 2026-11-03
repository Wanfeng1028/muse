"""结构化日志、request_id 中间件与 log_level 配置的测试。"""

from __future__ import annotations

import json
import logging
import re

import pytest

from ledger.config import get_settings
from ledger.logging import JsonFormatter, request_id_ctx


def _make_record(msg: str = "hello") -> logging.LogRecord:
    return logging.LogRecord(
        name="ledger.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_json_formatter_produces_single_line_json():
    fmt = JsonFormatter()
    out = fmt.format(_make_record("hi"))
    assert "\n" not in out
    data = json.loads(out)
    for key in ("ts", "level", "logger", "msg", "request_id"):
        assert key in data
    assert data["msg"] == "hi"
    assert data["level"] == "INFO"
    assert data["logger"] == "ledger.test"


def test_json_formatter_reads_request_id_from_contextvar():
    fmt = JsonFormatter()
    token = request_id_ctx.set("ctx123")
    try:
        data = json.loads(fmt.format(_make_record()))
    finally:
        request_id_ctx.reset(token)
    assert data["request_id"] == "ctx123"


def test_json_formatter_merges_extra_data():
    fmt = JsonFormatter()
    record = _make_record("req")
    record.extra_data = {"method": "GET", "status_code": 200}
    data = json.loads(fmt.format(record))
    assert data["method"] == "GET"
    assert data["status_code"] == 200
    assert data["msg"] == "req"


async def test_middleware_sets_request_id_header(client):
    resp = await client.get("/api/health")
    rid = resp.headers.get("X-Request-Id")
    assert rid is not None
    assert re.fullmatch(r"[0-9a-f]{12}", rid)


async def test_middleware_echoes_client_request_id(client):
    resp = await client.get("/api/health", headers={"X-Request-Id": "abc123"})
    assert resp.headers.get("X-Request-Id") == "abc123"


def test_get_settings_rejects_invalid_log_level(monkeypatch):
    monkeypatch.setenv("LEDGER_LOG_LEVEL", "nope")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError):
            get_settings()
    finally:
        get_settings.cache_clear()
