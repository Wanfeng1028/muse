import os

os.environ["FEEDFLOW_NO_SCHEDULER"] = "1"

import pytest
from werkzeug.security import generate_password_hash

from feedflow import create_app
from feedflow.auth import safe_next
from feedflow.config import validate


def _make_client(tmp_path, enabled: bool):
    db_path = str(tmp_path / "t.db")
    cfg = {
        "db_path": db_path,
        "host": "127.0.0.1",
        "port": 8300,
        "fetch_interval": 30,
        "user_agent": "test",
    }
    if enabled:
        cfg["auth_password_hash"] = generate_password_hash("pw123")
        cfg["secret_key"] = "test-secret-key"
    app = create_app(cfg)
    return app.test_client()


# 未开启时保持原有行为
def test_auth_disabled_keeps_old_behavior(tmp_path):
    client = _make_client(tmp_path, enabled=False)
    rv = client.get("/")
    assert rv.status_code == 200
    rv = client.get("/login")
    assert rv.status_code == 302
    assert rv.headers["Location"] == "/"


# 开启后未登录拦截页面与 API
def test_auth_enabled_blocks_pages_and_api(tmp_path):
    client = _make_client(tmp_path, enabled=True)
    rv = client.get("/")
    assert rv.status_code == 302
    assert rv.headers["Location"].startswith("/login")
    rv = client.get("/api/feeds")
    assert rv.status_code == 401
    assert rv.get_json()["error"] == "需要登录"
    rv = client.get("/healthz")
    assert rv.status_code == 200
    rv = client.get("/metrics")
    assert rv.status_code == 200


# 登录页渲染密码表单
def test_login_page_renders(tmp_path):
    client = _make_client(tmp_path, enabled=True)
    rv = client.get("/login")
    assert rv.status_code == 200
    assert 'name="password"' in rv.get_data(as_text=True)


# 错误密码不登录且仍被拦截
def test_wrong_password_stays_locked(tmp_path):
    client = _make_client(tmp_path, enabled=True)
    rv = client.post("/login", data={"password": "wrong"})
    assert rv.status_code == 200
    assert "密码不正确" in rv.get_data(as_text=True)
    rv = client.get("/")
    assert rv.status_code == 302


# 正确密码登录后跳转，登出后再次拦截
def test_login_logout_flow(tmp_path):
    client = _make_client(tmp_path, enabled=True)
    rv = client.post("/login", data={"password": "pw123", "next": "/feeds"})
    assert rv.status_code == 302
    assert rv.headers["Location"] == "/feeds"
    rv = client.get("/")
    assert rv.status_code == 200
    assert "退出" in rv.get_data(as_text=True)
    client.get("/logout")
    rv = client.get("/")
    assert rv.status_code == 302


# 登录 next 参数禁止开放重定向
def test_login_next_open_redirect_guard(tmp_path):
    client = _make_client(tmp_path, enabled=True)
    rv = client.post(
        "/login",
        data={"password": "pw123", "next": "https://evil.example/x"},
    )
    assert rv.status_code == 302
    assert rv.headers["Location"] == "/"


# safe_next 各分支
def test_safe_next_cases():
    assert safe_next("/feeds") == "/feeds"
    assert safe_next("https://evil.example") == "/"
    assert safe_next("//evil.example") == "/"
    assert safe_next("") == "/"


# validate 在有密码哈希但缺 secret_key 时抛 SystemExit
def test_validate_requires_secret_key(tmp_path):
    cfg = {
        "db_path": str(tmp_path / "t.db"),
        "host": "127.0.0.1",
        "port": 8300,
        "fetch_interval": 30,
        "fetch_timeout": 20,
        "fetch_retries": 3,
        "digest_n": 20,
        "extract_timeout": 15,
        "rate_limit_rps": 1.0,
        "rate_limit_burst": 60,
        "rate_limit_enabled": True,
        "feed_dead_after": 10,
        "user_agent": "test",
        "auth_password_hash": generate_password_hash("pw123"),
        "secret_key": "",
    }
    with pytest.raises(SystemExit):
        validate(cfg)
