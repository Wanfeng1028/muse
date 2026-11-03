# tests/test_web.py
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from feedflow import create_app, store


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("FEEDFLOW_DB", db_path)
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "信流".encode() in r.data


def test_feeds_page(client):
    r = client.get("/feeds")
    assert r.status_code == 200


def test_stats_page(client):
    r = client.get("/stats")
    assert r.status_code == 200


def test_opml_page(client):
    r = client.get("/opml")
    assert r.status_code == 200


def test_search_page(client):
    r = client.get("/search?q=xx")
    assert r.status_code == 200


def test_create_folder(client):
    r = client.post("/api/folders", json={"name": "科技"})
    assert r.status_code == 201
    r2 = client.get("/api/folders")
    assert r2.status_code == 200
    data = r2.get_json()
    assert any(f["name"] == "科技" for f in data)


def test_create_feed_requires_url(client):
    r = client.post("/api/feeds", json={})
    assert r.status_code == 400


def test_create_feed_and_duplicate(client):
    sample = str(ROOT / "tests" / "fixtures" / "sample.xml")
    r = client.post("/api/feeds", json={"feed_url": sample})
    assert r.status_code == 201
    r2 = client.post("/api/feeds", json={"feed_url": sample})
    assert r2.status_code == 409


def test_articles_all(client):
    r = client.get("/api/articles?scope=all")
    assert r.status_code == 200
    data = r.get_json()
    assert "total" in data
    assert data["total"] >= 0


def test_mark_read_excludes_from_unread(client):
    sample = str(ROOT / "tests" / "fixtures" / "sample.xml")
    r = client.post("/api/feeds", json={"feed_url": sample})
    assert r.status_code == 201
    feed_id = r.get_json()["id"]

    db_path = os.environ["FEEDFLOW_DB"]
    aid = store.insert_article(
        db_path, feed_id, "guid-1", "标题", "作者", "http://x", "摘要",
        "<p>正文</p>", "正文", None,
    )
    r = client.post(f"/api/articles/{aid}/read", json={"is_read": 1})
    assert r.status_code == 200
    r2 = client.get("/api/articles?scope=unread")
    ids = [a["id"] for a in r2.get_json()["articles"]]
    assert aid not in ids


def test_mark_starred_includes_in_starred(client):
    sample = str(ROOT / "tests" / "fixtures" / "sample.xml")
    r = client.post("/api/feeds", json={"feed_url": sample})
    feed_id = r.get_json()["id"]
    db_path = os.environ["FEEDFLOW_DB"]
    aid = store.insert_article(
        db_path, feed_id, "guid-2", "标题2", "作者", "http://x2", "摘要",
        "<p>正文</p>", "正文", None,
    )
    r = client.post(f"/api/articles/{aid}/star", json={"is_starred": 1})
    assert r.status_code == 200
    r2 = client.get("/api/articles?scope=starred")
    ids = [a["id"] for a in r2.get_json()["articles"]]
    assert aid in ids


def test_stats_api(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.get_json()
    assert "feeds" in data


def test_article_404(client):
    r = client.get("/api/articles/999999")
    assert r.status_code == 404
