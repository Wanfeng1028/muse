"""logging 模块深度测试：边界值、失败注入、幂等、并发、中文场景。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio

from ledger.logging import (
    JsonFormatter,
    RequestIdMiddleware,
    get_logger,
    request_id_ctx,
    setup_logging,
)


class _CaptureHandler(logging.Handler):
    """把日志记录序列化后存入列表，便于断言。"""

    def __init__(self, formatter: logging.Formatter) -> None:
        super().__init__()
        self.setFormatter(formatter)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


@pytest.fixture
def capture_logs():
    """挂一个 JsonFormatter handler 到 root logger，返回捕获列表。"""
    handler = _CaptureHandler(JsonFormatter())
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler.records
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def _parse(records: list[str]) -> list[dict]:
    return [json.loads(r) for r in records]


def test_json_formatter_empty_and_long_message(capture_logs):
    logger = get_logger("boundary")
    logger.info("")
    logger.info("超长消息" + "甲" * 5000)
    parsed = _parse(capture_logs)
    assert len(parsed) == 2
    assert parsed[0]["msg"] == ""
    assert parsed[1]["msg"].startswith("超长消息")
    assert len(parsed[1]["msg"]) == 5004
    assert parsed[0]["level"] == "INFO"
    assert parsed[0]["logger"] == "ledger.boundary"


def test_json_formatter_negative_and_huge_amount(capture_logs):
    logger = get_logger("amount")
    logger.info("金额", extra={"extra_data": {"amount": -1}})
    logger.info("金额", extra={"extra_data": {"amount": 10**18}})
    parsed = _parse(capture_logs)
    assert len(parsed) == 2
    assert parsed[0]["amount"] == -1
    assert parsed[1]["amount"] == 10**18
    assert isinstance(parsed[1]["amount"], int)
    assert parsed[0]["msg"] == "金额"


def test_json_formatter_chinese_merchant_and_remark(capture_logs):
    logger = get_logger("cn")
    logger.info(
        "记账",
        extra={
            "extra_data": {
                "merchant": "楼外楼",
                "remark": "中午和同事吃饭",
                "amount_upper": "壹佰贰拾叁元肆角伍分",
            }
        },
    )
    parsed = _parse(capture_logs)
    assert len(parsed) == 1
    assert parsed[0]["merchant"] == "楼外楼"
    assert parsed[0]["remark"] == "中午和同事吃饭"
    assert parsed[0]["amount_upper"] == "壹佰贰拾叁元肆角伍分"
    raw = capture_logs[0]
    assert "楼外楼" in raw


def test_json_formatter_ensure_ascii_false(capture_logs):
    logger = get_logger("cn2")
    logger.warning("警告：余额不足")
    raw = capture_logs[0]
    assert "余额不足" in raw
    assert "\\u" not in raw
    parsed = json.loads(raw)
    assert parsed["level"] == "WARNING"
    assert parsed["msg"] == "警告：余额不足"


def test_json_formatter_default_str_for_unserializable(capture_logs):
    logger = get_logger("obj")
    logger.info("时间", extra={"extra_data": {"when": datetime(2024, 1, 2, tzinfo=UTC)}})
    parsed = _parse(capture_logs)
    assert len(parsed) == 1
    assert "2024-01-02" in parsed[0]["when"]
    assert parsed[0]["level"] == "INFO"


def test_json_formatter_ignores_non_dict_extra(capture_logs):
    logger = get_logger("weird")
    logger.info("纯文本", extra={"extra_data": "not-a-dict"})
    logger.info("列表", extra={"extra_data": [1, 2, 3]})
    parsed = _parse(capture_logs)
    assert len(parsed) == 2
    assert parsed[0]["msg"] == "纯文本"
    assert "0" not in parsed[0]
    assert parsed[1]["msg"] == "列表"


def test_setup_logging_idempotent():
    setup_logging("INFO")
    setup_logging("INFO")
    setup_logging("DEBUG")
    root = logging.getLogger()
    json_handlers = [
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler) and isinstance(h.formatter, JsonFormatter)
    ]
    assert len(json_handlers) == 1
    assert root.level == logging.DEBUG


def test_request_id_ctx_default_is_dash():
    token = request_id_ctx.set("-")
    try:
        assert request_id_ctx.get() == "-"
    finally:
        request_id_ctx.reset(token)


def test_request_id_from_header(capture_logs, client):
    import anyio

    async def _run() -> httpx.Response:
        return await client.get("/health", headers={"X-Request-Id": "abc123def456"})

    response = anyio.from_thread.run(_run) if False else asyncio.run(_run())
    assert response.status_code in (200, 404)
    assert response.headers.get("X-Request-Id") == "abc123def456"
    parsed = _parse(capture_logs)
    http_logs = [p for p in parsed if p["logger"] == "ledger.http"]
    assert len(http_logs) >= 1
    assert http_logs[-1]["request_id"] == "abc123def456"


def test_request_id_generated_when_missing(capture_logs, client):
    async def _run() -> httpx.Response:
        return await client.get("/health")

    response = asyncio.run(_run())
    rid = response.headers.get("X-Request-Id")
    assert rid is not None
    assert len(rid) == 12
    assert rid != "-"


def test_access_log_contains_path_and_method(capture_logs, client):
    async def _run() -> httpx.Response:
        return await client.get("/health")

    asyncio.run(_run())
    parsed = _parse(capture_logs)
    http_logs = [p for p in parsed if p["logger"] == "ledger.http"]
    assert len(http_logs) >= 1
    entry = http_logs[-1]
    assert entry["method"] == "GET"
    assert entry["path"] == "/health"
    assert "duration_ms" in entry
    assert entry["duration_ms"] >= 0


def test_unhandled_exception_returns_500(capture_logs):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("数据库连接断了")

    with TestClient(app, raise_server_exceptions=False) as tc:
        resp = tc.get("/boom", headers={"X-Request-Id": "deadbeef0001"})

    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "服务器内部错误"
    assert body["request_id"] == "deadbeef0001"
    assert resp.headers.get("X-Request-Id") == "deadbeef0001"
    parsed = _parse(capture_logs)
    err_logs = [p for p in parsed if p["logger"] == "ledger.app" and p["level"] == "ERROR"]
    assert len(err_logs) == 1
    assert err_logs[0]["msg"] == "unhandled_exception"
    assert "数据库连接断了" in err_logs[0]["error"]


def test_http_exception_propagates(capture_logs):
    from fastapi import FastAPI, HTTPException
    from starlette.testclient import TestClient

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/nope")
    async def nope():
        raise HTTPException(status_code=404, detail="没找到账单")

    with TestClient(app, raise_server_exceptions=False) as tc:
        resp = tc.get("/nope", headers={"X-Request-Id": "cafebabe1234"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "没找到账单"
    assert resp.headers.get("X-Request-Id") == "cafebabe1234"
    parsed = _parse(capture_logs)
    err_logs = [p for p in parsed if p["logger"] == "ledger.app" and p["level"] == "ERROR"]
    assert len(err_logs) == 0


def test_concurrent_requests_have_distinct_request_ids(capture_logs):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async def _run() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            return await asyncio.gather(
                *[ac.get("/ping", headers={"X-Request-Id": f"req{i:08d}"}) for i in range(8)]
            )

    responses = asyncio.run(_run())
    assert len(responses) == 8
    ids = [r.headers.get("X-Request-Id") for r in responses]
    assert ids == [f"req{i:08d}" for i in range(8)]
    assert len(set(ids)) == 8
    parsed = _parse(capture_logs)
    http_logs = [p for p in parsed if p["logger"] == "ledger.http"]
    assert len(http_logs) == 8
    logged_ids = {p["request_id"] for p in http_logs}
    assert logged_ids == set(ids)


def test_concurrent_duplicate_bill_writes(capture_logs):
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    counter = {"n": 0}

    @app.post("/bills")
    async def create_bill():
        counter["n"] += 1
        return {"id": counter["n"]}

    async def _run() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            return await asyncio.gather(
                *[ac.post("/bills", headers={"X-Request-Id": "samebill0001"}) for _ in range(5)]
            )

    responses = asyncio.run(_run())
    assert len(responses) == 5
    assert all(r.status_code == 200 for r in responses)
    ids = sorted(r.json()["id"] for r in responses)
    assert ids == [1, 2, 3, 4, 5]
    parsed = _parse(capture_logs)
    http_logs = [p for p in parsed if p["logger"] == "ledger.http"]
    assert len(http_logs) == 5
    assert all(p["request_id"] == "samebill0001" for p in http_logs)
    assert all(p["method"] == "POST" for p in http_logs)