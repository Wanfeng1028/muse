from feedflow import db, store


def _make_feed(db_path):
    db.execute_write(db_path, "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, 0, ?)", ("F", "http://example.com/feed", "2024-01-01T00:00:00"))
    rows = db.query_all(db_path, "SELECT id FROM feeds ORDER BY id DESC LIMIT 1")
    return rows[0]["id"]


def _seed(db_path):
    feed_id = _make_feed(db_path)
    store.insert_article(db_path, feed_id, "g1", "Article 1", "author", "http://example.com/link-1", "summary", "<p>content</p>", "content", None)
    return feed_id


def _seeded_article_is_unread(client, feed_id):
    resp = client.get("/api/articles?scope=all")
    articles = resp.get_json()["articles"]
    for article in articles:
        if article.get("feed_id") == feed_id:
            return article.get("is_read") == 0
    return False


def test_mark_read_negative_feed_id_returns_400(client, tmp_db):
    feed_id = _seed(tmp_db)
    resp = client.post("/api/articles/mark_read", json={"feed_id": -1})
    assert resp.status_code == 400
    assert "feed_id 非法" in resp.get_json()["error"]
    assert _seeded_article_is_unread(client, feed_id)


def test_mark_read_negative_folder_id_returns_400(client, tmp_db):
    feed_id = _seed(tmp_db)
    resp = client.post("/api/articles/mark_read", json={"folder_id": -5})
    assert resp.status_code == 400
    assert "folder_id 非法" in resp.get_json()["error"]
    assert _seeded_article_is_unread(client, feed_id)


def test_mark_read_negative_tag_id_returns_400(client, tmp_db):
    feed_id = _seed(tmp_db)
    resp = client.post("/api/articles/mark_read", json={"tag_id": -1})
    assert resp.status_code == 400
    assert "tag_id 非法" in resp.get_json()["error"]
    assert _seeded_article_is_unread(client, feed_id)


def test_mark_read_negative_ids_combined_returns_400(client, tmp_db):
    _seed(tmp_db)
    resp = client.post("/api/articles/mark_read", json={"feed_id": -1, "tag_id": -2})
    assert resp.status_code == 400


def test_mark_read_zero_feed_id_still_200(client, tmp_db):
    _seed(tmp_db)
    resp = client.post("/api/articles/mark_read", json={"feed_id": 0})
    assert resp.status_code == 200


def test_mark_read_no_filter_still_200(client, tmp_db):
    feed_id = _seed(tmp_db)
    resp = client.post("/api/articles/mark_read", json={})
    assert resp.status_code == 200
    assert not _seeded_article_is_unread(client, feed_id)
