import pathlib

import pytest

from feedflow import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FEEDFLOW_DB", str(tmp_path / "test.db"))
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_reader_guide_design_layer_linked_and_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "css/design-v114.css" in html
    assert 'class="reader-guide"' in html
    assert "左边订阅树选一个订阅源" in html
    assert "中间文章列表选一篇文章" in html
    assert "订阅管理" in html
    css = client.get("/static/css/design-v114.css")
    assert css.status_code == 200
    body = css.get_data(as_text=True)
    for selector in (".reader-guide", ".reader-guide li", ".guide-step"):
        assert selector in body, selector
    assert "gradient" not in body.lower()
    assert "!important" not in body
    assert "box-shadow" not in body
    assert ".app-shell {" not in body
    assert ".col-reader {" not in body


def test_reader_guide_uses_newspaper_tokens():
    css = pathlib.Path(__file__).resolve().parents[1] / "feedflow" / "static" / "css" / "design-v114.css"
    body = css.read_text()
    # 纸面 #FAFAF7 与次要色 #6B655A 由 v112 层的 .reader-pane/.reader-empty 提供，本层规则只用以下四项。
    for token in ("#1C1A17", "#E7E2D6", "#C2410C", "#FBEDE6"):
        assert token in body, token
