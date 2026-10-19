
import re
from datetime import date

import pytest

from feedflow import create_app, db, store


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("FEEDFLOW_DB", db_path)
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def _db_path(app):
    return app.config["FEEDFLOW"]["db_path"]


def test_digest_clusters_page_ok(client):
    resp = client.get("/digest/clusters")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "聚类 Top" in body


def test_digest_clusters_page_has_score(client):
    resp = client.get("/digest/clusters")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    match = re.search(r"重要性\s*[:：]?\s*(\d+(?:\.\d+)?)", body)
    assert match is not None, "页面应包含 重要性 后跟数字"
    score = float(match.group(1))
    assert score >= 0


def test_digest_clusters_page_empty_when_all_read(client):
    app = client.application
    db_path = _db_path(app)
    conn = db.get_conn(db_path)
    try:
        conn.execute("UPDATE articles SET is_read=1")
        conn.commit()
    finally:
        conn.close()

    resp = client.get("/digest/clusters")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "没有可聚类" in body


def test_digest_clusters_page_respects_digest_n(client):
    app = client.application
    db_path = _db_path(app)
    from feedflow import ranking

    ranking.set_setting(db_path, "digest_n", 2)

    resp = client.get("/digest/clusters")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    card_count = body.count('class="clu-card"')
    assert card_count <= 2


def test_digest_clusters_page_no_auth_required(client):
    resp = client.get("/digest/clusters")
    assert resp.status_code == 200


def test_digest_clusters_page_today_format(client):
    resp = client.get("/digest/clusters")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    today = date.today().isoformat()
    assert today in body
    assert re.search(r"\d{4}-\d{2}-\d{2}", body) is not None
