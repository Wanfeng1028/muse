import os
import re

from feedflow import create_app
from feedflow.ratelimit import RateLimiter


def _make_app(tmp_db, **overrides):
    os.environ["FEEDFLOW_NO_SCHEDULER"] = "1"
    cfg = {
        "db_path": tmp_db,
        "host": "127.0.0.1",
        "port": 8300,
        "fetch_interval": 30,
        "user_agent": "FeedFlow-test",
    }
    cfg.update(overrides)
    return create_app(cfg)


def test_rate_limiter_allows_then_rejects():
    rl = RateLimiter(10.0, 2)
    ok1, _ = rl.allow("k")
    ok2, _ = rl.allow("k")
    ok3, retry = rl.allow("k")
    assert ok1 is True
    assert ok2 is True
    assert ok3 is False
    assert retry > 0


def test_http_429_with_retry_after(tmp_db):
    app = _make_app(
        tmp_db,
        # rps 极小：杜绝请求之间回充令牌，测试确定性（此前 rps=10 在慢请求下会抖动）
        rate_limit_rps=0.001,
        rate_limit_burst=2,
        rate_limit_enabled=True,
    )
    client = app.test_client()

    r1 = client.get("/")
    r2 = client.get("/")
    r3 = client.get("/")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    retry_after = r3.headers.get("Retry-After")
    assert retry_after is not None
    int(retry_after)
    body = r3.get_json()
    assert body is not None
    assert "error" in body


def test_healthz_metrics_exempt(tmp_db):
    app = _make_app(
        tmp_db,
        rate_limit_rps=10.0,
        rate_limit_burst=2,
        rate_limit_enabled=True,
    )
    client = app.test_client()

    for _ in range(5):
        assert client.get("/healthz").status_code == 200
    for _ in range(5):
        assert client.get("/metrics").status_code == 200


def test_rate_limit_disabled(tmp_db):
    app = _make_app(
        tmp_db,
        rate_limit_rps=10.0,
        rate_limit_burst=1,
        rate_limit_enabled=False,
    )
    client = app.test_client()

    for _ in range(5):
        assert client.get("/").status_code == 200


def test_rate_limited_metric(tmp_db):
    app = _make_app(
        tmp_db,
        rate_limit_rps=0.001,
        rate_limit_burst=1,
        rate_limit_enabled=True,
    )
    client = app.test_client()

    client.get("/")
    r2 = client.get("/")
    assert r2.status_code == 429

    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.data.decode("utf-8")
    assert "feedflow_http_rate_limited_total" in text
    m = re.search(r"feedflow_http_rate_limited_total (\d+)", text)
    assert m is not None
    assert int(m.group(1)) >= 1
