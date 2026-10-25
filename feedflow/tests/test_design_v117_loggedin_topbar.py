"""design-v117 已登录顶栏与 v116 两行布局回归测试。

fixture 自带 auth 配置（auth_password_hash + secret_key），不依赖
tests/conftest.py 的 app/client fixture。实测口径：已登录 390px 宽下
顶栏仍 183px、导航仍两行、app-shell 仍 613px（= 100vh - 183px - 48px）。
"""

import pytest
from werkzeug.security import generate_password_hash

from feedflow import create_app

# 一次性测试密码：只存在于本文件，用后即弃
_TEST_PASSWORD = "v117-loggedin-topbar-onceoff-password"

_LOGGEDOUT_LINK_TEXTS = ("阅读器", "今日必读", "聚类 Top", "订阅管理", "统计", "OPML")
_LOGGEDIN_ONLY_TEXT = "退出"

_V116_CSS_PATH = "/static/css/design-v116.css"
_APP_SHELL_HEIGHT = "calc(100vh - 183px - 48px)"


def _make_gated_app(tmp_path):
    return create_app(
        {
            "db_path": str(tmp_path / "feedflow-v117-test.sqlite3"),
            "host": "127.0.0.1",
            "port": 8300,
            "fetch_interval": 30,
            "user_agent": "FeedFlow-test",
            "auth_password_hash": generate_password_hash(_TEST_PASSWORD),
            "secret_key": "v117-test-secret-key",
        }
    )


def _mainnav_segment(html):
    start = html.find("mainnav")
    assert start != -1, "正文未找到 nav.mainnav"
    end = html.find("</nav>", start)
    assert end != -1, "nav.mainnav 段未闭合"
    return html[start:end]


@pytest.fixture()
def gated_app(tmp_path):
    return _make_gated_app(tmp_path)


def test_loggedin_nav_has_seven_links_and_v116_layer(gated_app):
    client = gated_app.test_client()

    login = client.post("/login", data={"password": _TEST_PASSWORD, "next": "/"})
    assert login.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("feedflow_authed") is True

    page = client.get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert _LOGGEDIN_ONLY_TEXT in html

    segment = _mainnav_segment(html)
    assert segment.count("<a") == 7, f"mainnav 应有 7 个 <a>，实际 {segment.count('<a')}"
    for text in (*_LOGGEDOUT_LINK_TEXTS, _LOGGEDIN_ONLY_TEXT):
        assert text in segment, f"mainnav 缺少链接文本：{text}"

    css = client.get(_V116_CSS_PATH)
    assert css.status_code == 200
    css_text = css.get_data(as_text=True)
    assert _APP_SHELL_HEIGHT in css_text
    assert "height: auto" in css_text


def test_loggedout_nav_has_six_links_no_logout(tmp_path):
    # 未开启密码门的应用：首页直接 200，导航为 6 链无“退出”。
    # 注意：开启密码门时未登录 GET / 会 302 到 /login，登录页没有导航，
    # 因此本例必须用不带 auth 配置的应用，不能复用 gated_app。
    app = create_app(
        {
            "db_path": str(tmp_path / "feedflow-v117-test-nogate.sqlite3"),
            "host": "127.0.0.1",
            "port": 8300,
            "fetch_interval": 30,
            "user_agent": "FeedFlow-test",
        }
    )
    client = app.test_client()

    page = client.get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert _LOGGEDIN_ONLY_TEXT not in html

    segment = _mainnav_segment(html)
    assert segment.count("<a") == 6
    for text in _LOGGEDOUT_LINK_TEXTS:
        assert text in html, f"正文缺少未登录链接文本：{text}"
