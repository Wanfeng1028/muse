from feedflow import db, store


def _make_feed(db_path, feed_url="http://example.com/feed", title="F"):
    db.execute_write(
        db_path,
        "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, 0, ?)",
        (title, feed_url, "2024-01-01T00:00:00"),
    )
    rows = db.query_all(db_path, "SELECT id FROM feeds ORDER BY id DESC LIMIT 1")
    return rows[0]["id"]


def _seed_three(db_path):
    feed_id = _make_feed(db_path)
    for i in range(3):
        store.insert_article(
            db_path,
            feed_id,
            f"g{i}",
            f"Article {i}",
            "author",
            f"http://example.com/link-{i}",
            "summary",
            "<p>content</p>",
            "content",
            None,
        )
    return feed_id


def test_feed_id_abc_returns_400(client, tmp_db):
    _seed_three(tmp_db)
    resp = client.get("/api/articles?feed_id=abc")
    assert resp.status_code == 400
    assert "feed_id 参数非法" in resp.get_json()["error"]


def test_folder_id_abc_returns_400(client, tmp_db):
    _seed_three(tmp_db)
    resp = client.get("/api/articles?folder_id=abc")
    assert resp.status_code == 400
    assert "folder_id 参数非法" in resp.get_json()["error"]


def test_tag_id_abc_returns_400(client, tmp_db):
    _seed_three(tmp_db)
    resp = client.get("/api/articles?tag_id=abc")
    assert resp.status_code == 400
    assert "tag_id 参数非法" in resp.get_json()["error"]


def test_feed_id_float_returns_400(client, tmp_db):
    _seed_three(tmp_db)
    resp = client.get("/api/articles?feed_id=1.5")
    assert resp.status_code == 400
    assert "feed_id 参数非法" in resp.get_json()["error"]


def test_feed_id_missing_returns_200(client, tmp_db):
    _seed_three(tmp_db)
    resp = client.get("/api/articles")
    assert resp.status_code == 200


def test_feed_id_empty_returns_200(client, tmp_db):
    _seed_three(tmp_db)
    resp = client.get("/api/articles?feed_id=")
    assert resp.status_code == 200


def test_feed_id_valid_filters(client, tmp_db):
    feed_id = _seed_three(tmp_db)
    resp = client.get(f"/api/articles?feed_id={feed_id}")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 3


def test_feed_id_and_folder_id_invalid_returns_400(client, tmp_db):
    _seed_three(tmp_db)
    resp = client.get("/api/articles?feed_id=abc&folder_id=abc")
    assert resp.status_code == 400