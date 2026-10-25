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


def test_mobile_design_layer_linked_and_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "css/design-v113.css" in resp.get_data(as_text=True)
    css = client.get("/static/css/design-v113.css")
    assert css.status_code == 200
    body = css.get_data(as_text=True)
    assert "@media (max-width: 768px)" in body
    for selector in (".mobile-views", ".mobile-view-btn", ".mobile-view-btn.is-active"):
        assert selector in body, selector
    assert "gradient" not in body.lower()
    assert "!important" not in body
    # Desktop layout untouched: no bare .app-shell override outside the media query.
    assert ".app-shell {" not in body


def test_mobile_switcher_uses_newspaper_tokens():
    css = pathlib.Path(__file__).resolve().parents[1] / "feedflow" / "static" / "css" / "design-v113.css"
    body = css.read_text()
    for token in ("#FAFAF7", "#1C1A17", "#6B655A", "#E7E2D6", "#C2410C", "#FBEDE6"):
        assert token in body, token
