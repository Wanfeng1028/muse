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


def test_mark_read_feed_id_bool_true_v139(client, tmp_db):
    db_path = str(tmp_db)
    feed_id = _seed(db_path)
    resp = client.post("/api/articles/mark_read", json={"feed_id": True})
    assert resp.status_code == 400
    assert "feed_id 非法" in resp.get_json()["error"]
    assert _seeded_article_is_unread(client, feed_id)


def test_mark_read_feed_id_bool_false_v139(client, tmp_db):
    db_path = str(tmp_db)
    feed_id = _seed(db_path)
    resp = client.post("/api/articles/mark_read", json={"feed_id": False})
    assert resp.status_code == 400
    assert "feed_id 非法" in resp.get_json()["error"]
    assert _seeded_article_is_unread(client, feed_id)


def test_mark_read_folder_id_bool_true_v139(client, tmp_db):
    db_path = str(tmp_db)
    feed_id = _seed(db_path)
    resp = client.post("/api/articles/mark_read", json={"folder_id": True})
    assert resp.status_code == 400
    assert "folder_id 非法" in resp.get_json()["error"]
    assert _seeded_article_is_unread(client, feed_id)


def test_mark_read_tag_id_bool_false_v139(client, tmp_db):
    db_path = str(tmp_db)
    feed_id = _seed(db_path)
    resp = client.post("/api/articles/mark_read", json={"tag_id": False})
    assert resp.status_code == 400
    assert "tag_id 非法" in resp.get_json()["error"]
    assert _seeded_article_is_unread(client, feed_id)


def test_mark_read_feed_id_float_non_integral_v139(client, tmp_db):
    db_path = str(tmp_db)
    feed_id = _seed(db_path)
    resp = client.post("/api/articles/mark_read", json={"feed_id": 1.5})
    assert resp.status_code == 400
    assert "feed_id 非法" in resp.get_json()["error"]
    assert _seeded_article_is_unread(client, feed_id)


def test_mark_read_feed_id_float_integral_v139(client, tmp_db):
    db_path = str(tmp_db)
    feed_id = _seed(db_path)
    resp = client.post("/api/articles/mark_read", json={"feed_id": 2.0})
    assert resp.status_code == 400
    assert "feed_id 非法" in resp.get_json()["error"]
    assert _seeded_article_is_unread(client, feed_id)


def test_mark_read_feed_id_bool_with_valid_scope_v139(client, tmp_db):
    db_path = str(tmp_db)
    feed_id = _seed(db_path)
    resp = client.post("/api/articles/mark_read", json={"feed_id": True, "scope": "all"})
    assert resp.status_code == 400
    assert "feed_id 非法" in resp.get_json()["error"]
    assert _seeded_article_is_unread(client, feed_id)


def test_mark_read_feed_id_int_and_str_still_ok_v139(client, tmp_db):
    db_path = str(tmp_db)
    feed_id = _seed(db_path)
    resp = client.post("/api/articles/mark_read", json={"feed_id": feed_id})
    assert resp.status_code == 200
    assert resp.get_json()["updated"] is None
    resp = client.post("/api/articles/mark_read", json={"feed_id": str(feed_id)})
    assert resp.status_code == 200
    assert resp.get_json()["updated"] is None
    resp = client.get("/api/articles?scope=all")
    articles = resp.get_json()["articles"]
    for article in articles:
        if article.get("feed_id") == feed_id:
            assert article.get("is_read") == 1
