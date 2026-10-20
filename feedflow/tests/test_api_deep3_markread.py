import pytest

from feedflow import db
from feedflow import store


def _make_feed(db_path, feed_url, title):
    db.execute_write(
        db_path,
        "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, 0, ?)",
        (title, feed_url, "2024-01-01T00:00:00"),
    )
    rows = db.query_all(db_path, "SELECT id FROM feeds WHERE feed_url = ?", (feed_url,))
    return rows[0]["id"]


def _mk(db_path, feed_id, guid, title):
    store.insert_article(
        db_path,
        feed_id,
        guid,
        title,
        "",
        "",
        "",
        "",
        "",
        None,
    )


def test_mark_read_bad_scope_falls_back(client, tmp_db):
    feed_id = _make_feed(tmp_db, "http://example.com/feed-a", "A")
    _mk(tmp_db, feed_id, "g1", "one")
    _mk(tmp_db, feed_id, "g2", "two")
    db.execute_write(
        tmp_db,
        "UPDATE articles SET is_read=1 WHERE feed_id=? AND guid=?",
        (feed_id, "g1"),
    )

    resp = client.post("/api/articles/mark_read", json={"scope": "bogus"})
    assert resp.status_code == 200
    body = resp.get_json()
    # store.mark_all_read 无返回值，API 的 updated 恒为 null
    assert body["updated"] is None

    listing = client.get("/api/articles?scope=all")
    assert listing.status_code == 200
    items = listing.get_json()["articles"]
    mine = [a for a in items if a["feed_id"] == feed_id]
    assert len(mine) == 2
    assert all(a["is_read"] == 1 for a in mine)


def test_mark_read_bad_folder_id(client, tmp_db):
    resp = client.post("/api/articles/mark_read", json={"folder_id": "abc"})
    assert resp.status_code == 400


def test_mark_read_feed_filter(client, tmp_db):
    feed1_id = _make_feed(tmp_db, "http://example.com/feed-1", "F1")
    feed2_id = _make_feed(tmp_db, "http://example.com/feed-2", "F2")
    _mk(tmp_db, feed1_id, "f1-g1", "f1 one")
    _mk(tmp_db, feed2_id, "f2-g1", "f2 one")

    resp = client.post("/api/articles/mark_read", json={"feed_id": feed1_id})
    assert resp.status_code == 200
    body = resp.get_json()
    # store.mark_all_read 无返回值，API 的 updated 恒为 null
    assert body["updated"] is None

    listing = client.get("/api/articles?scope=all")
    assert listing.status_code == 200
    items = listing.get_json()["articles"]
    f1 = [a for a in items if a["feed_id"] == feed1_id]
    f2 = [a for a in items if a["feed_id"] == feed2_id]
    assert len(f1) == 1
    assert len(f2) == 1
    assert f1[0]["is_read"] == 1
    assert f2[0]["is_read"] == 0
