import sqlite3

from feedflow import store


def _make_article(db_path):
    feed_id = store.create_feed(
        db_path,
        "http://127.0.0.1:9/nonexistent.xml",
        None,
        0,
    )
    return store.insert_article(
        db_path,
        feed_id,
        "guid-1",
        "标题",
        "作者",
        "http://example.com/a",
        "摘要",
        "<p>正文</p>",
        "正文",
        "2024-01-01T00:00:00",
    )


def test_migration_v4_adds_scroll_pos(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
    finally:
        conn.close()
    assert "scroll_pos" in cols


def test_set_get_scroll_pos_roundtrip(tmp_db):
    aid = _make_article(tmp_db)
    store.set_scroll_pos(tmp_db, aid, 123.5)
    assert store.get_scroll_pos(tmp_db, aid) == 123.5


def test_negative_scroll_pos_clamped_to_zero(tmp_db):
    aid = _make_article(tmp_db)
    store.set_scroll_pos(tmp_db, aid, -50)
    assert store.get_scroll_pos(tmp_db, aid) == 0.0


def test_get_article_contains_scroll_pos_key(tmp_db):
    aid = _make_article(tmp_db)
    a = store.get_article(tmp_db, aid)
    assert a is not None
    assert "scroll_pos" in a


def test_api_progress_persists(client, tmp_db):
    aid = _make_article(tmp_db)
    resp = client.post(f"/api/articles/{aid}/progress", json={"scroll_pos": 42.0})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == aid
    assert data["scroll_pos"] == 42.0
    a = store.get_article(tmp_db, aid)
    assert a["scroll_pos"] == 42.0


def test_api_progress_invalid_returns_400(client, tmp_db):
    aid = _make_article(tmp_db)
    resp = client.post(f"/api/articles/{aid}/progress", json={"scroll_pos": "abc"})
    assert resp.status_code == 400
    resp = client.post(f"/api/articles/{aid}/progress", json={"scroll_pos": -1})
    assert resp.status_code == 400


def test_api_progress_missing_article_returns_404(client):
    resp = client.post("/api/articles/99999/progress", json={"scroll_pos": 10})
    assert resp.status_code == 404


def test_api_progress_caps_at_100000(client, tmp_db):
    aid = _make_article(tmp_db)
    resp = client.post(f"/api/articles/{aid}/progress", json={"scroll_pos": 200000})
    assert resp.status_code == 200
    assert resp.get_json()["scroll_pos"] == 100000
    a = store.get_article(tmp_db, aid)
    assert a["scroll_pos"] == 100000.0
