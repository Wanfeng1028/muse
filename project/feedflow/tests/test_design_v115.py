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


def test_topbar_design_layer_linked_and_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "css/design-v115.css" in resp.get_data(as_text=True)
    css = client.get("/static/css/design-v115.css")
    assert css.status_code == 200
    body = css.get_data(as_text=True)
    assert "@media (max-width: 768px)" in body
    for selector in (".topbar-inner", ".topbar-inner .mainnav", ".topbar-inner .searchbox input"):
        assert selector in body, selector
    assert "overflow-x: visible" in body
    assert "overflow-x: auto" in body
    assert "width: 120px" in body
    assert "gradient" not in body.lower()
    assert "!important" not in body
    assert "box-shadow" not in body
    # Desktop untouched: no bare .topbar rule outside the media query.
    assert "\n.topbar {" not in body
    assert ".app-shell {" not in body


def test_topbar_layer_is_mobile_only():
    css = pathlib.Path(__file__).resolve().parents[1] / "feedflow" / "static" / "css" / "design-v115.css"
    body = css.read_text()
    first_rule = body.find(".topbar-inner")
    media = body.find("@media (max-width: 768px)")
    assert 0 <= media < first_rule
