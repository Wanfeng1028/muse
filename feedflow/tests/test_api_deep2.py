import os

import pytest

from feedflow import db
from feedflow import store


def _insert_article(db_path, feed_id, guid, title="T", published_at="2024-01-01T00:00:00"):
    store.insert_article(
        db_path,
        feed_id,
        guid,
        title,
        "author",
        "http://example.com/link",
        "summary",
        "<p>content</p>",
        "content",
        published_at,
    )


def _make_feed(db_path, feed_url="http://example.com/feed", title="F"):
    db_conn = store.get_db(db_path) if hasattr(store, "get_db") else None
    db.execute_write(
        db_path,
        "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, 0, ?)",
        (title, feed_url, "2024-01-01T00:00:00"),
    )
    rows = db.query_all(db_path, "SELECT id FROM feeds ORDER BY id DESC LIMIT 1")
    return rows[0]["id"]


def _write_rss(tmp_path, name="feed.xml", title="T"):
    path = tmp_path / name
    path.write_text(
        '<?xml version="1.0"?><rss version="2.0"><channel><title>%s</title>'
        "<item><title>I</title><link>http://x/1</link><guid>g1</guid></item>"
        "</channel></rss>" % title,
        encoding="utf-8",
    )
    return str(path)


def test_sql_injection_folder_name_roundtrip(client, tmp_db):
    payload = "x'); DROP TABLE folders; --"
    resp = client.post("/api/folders", json={"name": payload})
    assert resp.status_code == 201
    created = resp.get_json()
    assert created["name"] == payload

    listing = client.get("/api/folders")
    assert listing.status_code == 200
    items = listing.get_json()
    names = [f["name"] for f in items]
    assert payload in names
    assert any(f["name"] == payload for f in items)


def test_xss_payload_folder_name_not_escaped(client, tmp_db):
    payload = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    resp = client.post("/api/folders", json={"name": payload})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["name"] == payload

    listing = client.get("/api/folders").get_json()
    stored = [f for f in listing if f["name"] == payload]
    assert len(stored) == 1


def test_very_long_folder_name(client, tmp_db):
    name = "名" * 5000
    resp = client.post("/api/folders", json={"name": name})
    assert resp.status_code == 201
    assert resp.get_json()["name"] == name


def test_whitespace_only_folder_name_rejected(client, tmp_db):
    resp = client.post("/api/folders", json={"name": "   "})
    assert resp.status_code == 400


def test_json_array_body_treated_as_empty(client, tmp_db):
    resp = client.post("/api/folders", json=[1, 2])
    assert resp.status_code == 400


def test_put_folder_invalid_position(client, tmp_db):
    created = client.post("/api/folders", json={"name": "grp"}).get_json()
    folder_id = created["id"]
    resp = client.put("/api/folders/%d" % folder_id, json={"name": "grp2", "position": "abc"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body.get("error") == "position 非法"


def test_articles_pagination_edge_cases(client, tmp_db):
    feed_id = _make_feed(tmp_db)
    for i in range(3):
        _insert_article(tmp_db, feed_id, "guid-%d" % i, title="T%d" % i)

    r1 = client.get("/api/articles?limit=abc")
    assert r1.status_code == 200

    r2 = client.get("/api/articles?limit=-5")
    assert r2.status_code == 200

    r3 = client.get("/api/articles?limit=999")
    assert r3.status_code == 200
    assert len(r3.get_json()["articles"]) <= 200

    r4 = client.get("/api/articles?offset=-3")
    assert r4.status_code == 200

    r5 = client.get("/api/articles?offset=abc")
    assert r5.status_code == 200

    r6 = client.get("/api/articles?scope=bogus")
    assert r6.status_code == 200


def test_read_missing_article_404(client, tmp_db):
    resp = client.post("/api/articles/999999/read", json={"is_read": 1})
    assert resp.status_code == 404


def test_read_invalid_is_read(client, tmp_db):
    feed_id = _make_feed(tmp_db)
    _insert_article(tmp_db, feed_id, "g-read")
    rows = db.query_all(tmp_db, "SELECT id FROM articles ORDER BY id DESC LIMIT 1")
    article_id = rows[0]["id"]

    resp = client.post("/api/articles/%d/read" % article_id, json={"is_read": "yes"})
    assert resp.status_code == 400

    resp2 = client.post("/api/articles/%d/read" % article_id, json={})
    assert resp2.status_code == 400


def test_star_string_one_ok(client, tmp_db):
    feed_id = _make_feed(tmp_db)
    _insert_article(tmp_db, feed_id, "g-star")
    rows = db.query_all(tmp_db, "SELECT id FROM articles ORDER BY id DESC LIMIT 1")
    article_id = rows[0]["id"]

    resp = client.post("/api/articles/%d/star" % article_id, json={"is_starred": "1"})
    assert resp.status_code == 200
    assert resp.get_json()["is_starred"] == 1


def test_progress_negative_rejected(client, tmp_db):
    feed_id = _make_feed(tmp_db)
    _insert_article(tmp_db, feed_id, "g-prog1")
    rows = db.query_all(tmp_db, "SELECT id FROM articles ORDER BY id DESC LIMIT 1")
    article_id = rows[0]["id"]

    resp = client.post("/api/articles/%d/progress" % article_id, json={"scroll_pos": -1})
    assert resp.status_code == 400


def test_progress_clamped_to_max(client, tmp_db):
    feed_id = _make_feed(tmp_db)
    _insert_article(tmp_db, feed_id, "g-prog2")
    rows = db.query_all(tmp_db, "SELECT id FROM articles ORDER BY id DESC LIMIT 1")
    article_id = rows[0]["id"]

    resp = client.post("/api/articles/%d/progress" % article_id, json={"scroll_pos": 200000})
    assert resp.status_code == 200
    assert resp.get_json()["scroll_pos"] == 100000.0


def test_progress_missing_scroll_pos(client, tmp_db):
    feed_id = _make_feed(tmp_db)
    _insert_article(tmp_db, feed_id, "g-prog3")
    rows = db.query_all(tmp_db, "SELECT id FROM articles ORDER BY id DESC LIMIT 1")
    article_id = rows[0]["id"]

    resp = client.post("/api/articles/%d/progress" % article_id, json={})
    assert resp.status_code == 400


def test_mark_read_invalid_feed_id(client, tmp_db):
    resp = client.post("/api/articles/mark_read", json={"feed_id": "abc"})
    assert resp.status_code == 400


def test_create_feed_missing_url(client, tmp_db):
    resp = client.post("/api/feeds", json={})
    assert resp.status_code == 400


def test_create_feed_invalid_interval_min(client, tmp_db):
    resp = client.post(
        "/api/feeds",
        json={"feed_url": "/tmp/nonexistent-xyz", "interval_min": "abc"},
    )
    assert resp.status_code == 400
    assert resp.get_json().get("error") == "interval_min 非法"


def test_create_feed_invalid_folder_id(client, tmp_db):
    resp = client.post(
        "/api/feeds",
        json={"feed_url": "/tmp/nonexistent-xyz", "folder_id": "abc"},
    )
    assert resp.status_code == 400


def test_create_feed_duplicate_conflict(client, tmp_path, tmp_db):
    rss_path = _write_rss(tmp_path, "valid.xml", "T")
    first = client.post("/api/feeds", json={"feed_url": rss_path})
    assert first.status_code == 201

    second = client.post("/api/feeds", json={"feed_url": rss_path})
    assert second.status_code == 409
    assert second.get_json().get("error") == "该订阅源已存在"