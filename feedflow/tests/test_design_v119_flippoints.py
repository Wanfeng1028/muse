import re

import pytest

from feedflow import create_app


@pytest.fixture
def app_open(tmp_path):
    """无密码门的应用：必需配置带齐，不开 auth；库用 tmp_path 隔离，绝不碰仓库 data 库。"""
    cfg = {
        "db_path": str(tmp_path / "feedflow-v119-open.sqlite3"),
        "host": "127.0.0.1",
        "port": 8300,
        "fetch_interval": 30,
        "user_agent": "FeedFlow-test",
    }
    return create_app(cfg)


def test_v119_layer_linked_after_v116(app_open):
    client = app_open.test_client()

    page = client.get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "design-v116.css" in html
    assert "design-v117.css" in html
    assert html.index("design-v117.css") > html.index("design-v116.css")

    css_resp = client.get("/static/css/design-v117.css")
    assert css_resp.status_code == 200


def test_v119_breakpoint_pairing(app_open):
    import re

    resp = app_open.test_client().get("/static/css/design-v117.css")
    assert resp.status_code == 200
    css = resp.get_data(as_text=True)

    assert css.count("calc(100vh - 121px - 48px)") == 2

    media_re = re.compile(
        r"@media\s*\(\s*max-width:\s*768px\s*\)\s*and\s*"
        r"\(\s*min-width:\s*(\d+)px\s*\)\s*\{(.*?)\}\s*\}",
        re.S,
    )
    blocks = {int(m.group(1)): m.group(2) for m in media_re.finditer(css)}

    assert 521 in blocks
    assert 471 in blocks
    assert 521 > 471

    block_a = blocks[521]
    block_b = blocks[471]

    assert "is-logged-in" in block_a
    assert ":not(" not in block_a
    assert ":not(.is-logged-in)" in block_b


def test_v119_no_banned_declarations(app_open):
    client = app_open.test_client()

    css_resp = client.get("/static/css/design-v117.css")
    assert css_resp.status_code == 200
    css = css_resp.get_data(as_text=True)
    assert "!important" not in css
    assert "gradient" not in css
    assert "box-shadow" not in css
