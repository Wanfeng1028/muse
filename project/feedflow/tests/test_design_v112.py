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


def test_design_layer_linked_and_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "css/design-v112.css" in resp.get_data(as_text=True)
    css = client.get("/static/css/design-v112.css")
    assert css.status_code == 200
    body = css.get_data(as_text=True)
    for selector in (".mainnav a.active", ".tree-item.active", ".article-item.active",
                     ".list-bar", "main.page .digest-wrap", ".stats-page .stat-card"):
        assert selector in body, selector
    assert "gradient" not in body.lower()
    assert ".app-shell {" not in body


def test_list_star_is_svg_not_character():
    app_js = pathlib.Path(__file__).resolve().parents[1] / "feedflow" / "static" / "js" / "app.js"
    text = app_js.read_text()
    assert '<span class="star"><svg' in text
    assert '<span class="star">★</span>' not in text


def test_open_article_marks_active_item():
    app_js = pathlib.Path(__file__).resolve().parents[1] / "feedflow" / "static" / "js" / "app.js"
    text = app_js.read_text()
    assert 'classList.toggle("active"' in text
