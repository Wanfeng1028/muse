import re

import pytest
from werkzeug.security import generate_password_hash

from feedflow import create_app

TEST_PASSWORD = "feedflow-one-time-test-password"


def _base_cfg():
    return {
        "host": "127.0.0.1",
        "port": 8300,
        "fetch_interval": 30,
        "user_agent": "FeedFlow-test",
    }


@pytest.fixture
def app_open(tmp_path):
    """无密码门的应用：必需配置带齐，不开 auth；库用 tmp_path 隔离，绝不碰仓库 data 库。"""
    cfg = _base_cfg()
    cfg["db_path"] = str(tmp_path / "feedflow-v118-open.sqlite3")
    return create_app(cfg)


@pytest.fixture
def app_password(tmp_path):
    """开启密码门的应用：auth_password_hash 与 secret_key 同时提供；库用 tmp_path 隔离。"""
    cfg = _base_cfg()
    cfg["db_path"] = str(tmp_path / "feedflow-v118-gated.sqlite3")
    cfg["auth_password_hash"] = generate_password_hash(TEST_PASSWORD)
    cfg["secret_key"] = "feedflow-test-secret"
    return create_app(cfg)


def _body_tag(html):
    match = re.search(r"<body\b[^>]*>", html)
    assert match is not None, "页面 HTML 中没有 <body> 标签"
    return match.group(0)


def test_v117_layer_linked_after_v116(app_open):
    client = app_open.test_client()

    page = client.get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "design-v116.css" in html
    assert "design-v117.css" in html
    assert html.index("design-v117.css") > html.index("design-v116.css")

    css_resp = client.get("/static/css/design-v117.css")
    assert css_resp.status_code == 200
    css = css_resp.get_data(as_text=True)
    assert "@media (max-width: 768px) and (min-width: 521px)" in css
    assert "@media (max-width: 768px) and (min-width: 471px)" in css
    assert css.count("calc(100vh - 121px - 48px)") == 2
    assert "gradient" not in css
    assert "!important" not in css
    assert "box-shadow" not in css


def test_body_class_marks_logged_in(app_password):
    client = app_password.test_client()

    login = client.post("/login", data={"password": TEST_PASSWORD, "next": "/"})
    assert login.status_code == 302

    page = client.get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "is-logged-in" in _body_tag(html)


def test_body_class_absent_when_logged_out(app_open):
    client = app_open.test_client()

    page = client.get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "is-logged-in" not in _body_tag(html)
