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


def test_feed_id_negative_returns_400(client, tmp_db):
    _seed_three(tmp_db)
    response = client.get("/api/articles?feed_id=-1")
    assert response.status_code == 400
    payload = response.get_json()
    assert "feed_id 参数非法" in payload["error"]


def test_folder_id_negative_returns_400(client, tmp_db):
    _seed_three(tmp_db)
    response = client.get("/api/articles?folder_id=-5")
    assert response.status_code == 400
    payload = response.get_json()
    assert "folder_id 参数非法" in payload["error"]


def test_tag_id_negative_returns_400(client, tmp_db):
    _seed_three(tmp_db)
    response = client.get("/api/articles?tag_id=-1")
    assert response.status_code == 400
    payload = response.get_json()
    assert "tag_id 参数非法" in payload["error"]


def test_negative_ids_combined_returns_400(client, tmp_db):
    _seed_three(tmp_db)
    response = client.get("/api/articles?feed_id=-1&tag_id=-2")
    assert response.status_code == 400


def test_feed_id_zero_still_returns_200(client, tmp_db):
    _seed_three(tmp_db)
    response = client.get("/api/articles?feed_id=0")
    assert response.status_code == 200
