"""测试 /healthz 健康检查端点。"""


def test_healthz_ok(app):
    """/healthz 应返回 200，并包含 status/db/scheduler 字段。"""
    client = app.test_client()
    resp = client.get("/healthz")
    assert resp.status_code == 200

    data = resp.get_json()
    assert isinstance(data, dict)
    assert "status" in data
    assert "db" in data
    assert "scheduler" in data
    assert data["status"] in ("ok", "healthy", "degraded")
    assert data["db"] in ("ok", "error")
    # FEEDFLOW_NO_SCHEDULER=1 下 scheduler 应处于 disabled 状态
    assert data["scheduler"] in ("ok", "disabled", "error")
