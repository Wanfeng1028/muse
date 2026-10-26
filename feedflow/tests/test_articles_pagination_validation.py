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


def test_limit_abc_returns_400(client, tmp_db):
    feed_id = _seed_three(tmp_db)
    resp = client.get(f"/api/articles?feed_id={feed_id}&limit=abc")
    assert resp.status_code == 400
    assert "limit 参数非法" in resp.get_json()["error"]


def test_limit_float_returns_400(client, tmp_db):
    feed_id = _seed_three(tmp_db)
    resp = client.get(f"/api/articles?feed_id={feed_id}&limit=1.5")
    assert resp.status_code == 400
    assert "limit 参数非法" in resp.get_json()["error"]


def test_limit_zero_returns_400(client, tmp_db):
    feed_id = _seed_three(tmp_db)
    resp = client.get(f"/api/articles?feed_id={feed_id}&limit=0")
    assert resp.status_code == 400
    assert "limit 参数非法" in resp.get_json()["error"]


def test_limit_negative_returns_400(client, tmp_db):
    feed_id = _seed_three(tmp_db)
    resp = client.get(f"/api/articles?feed_id={feed_id}&limit=-3")
    assert resp.status_code == 400
    assert "limit 参数非法" in resp.get_json()["error"]


def test_offset_invalid_returns_400(client, tmp_db):
    feed_id = _seed_three(tmp_db)
    resp = client.get(f"/api/articles?feed_id={feed_id}&offset=7x")
    assert resp.status_code == 400
    assert "offset 参数非法" in resp.get_json()["error"]


def test_offset_negative_returns_400(client, tmp_db):
    feed_id = _seed_three(tmp_db)
    resp = client.get(f"/api/articles?feed_id={feed_id}&offset=-5")
    assert resp.status_code == 400
    assert "offset 参数非法" in resp.get_json()["error"]


def test_empty_limit_offset_use_defaults(client, tmp_db):
    feed_id = _seed_three(tmp_db)
    resp = client.get(f"/api/articles?feed_id={feed_id}&limit=&offset=")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 3
    assert len(data["articles"]) == 3


def test_limit_over_200_clamped(client, tmp_db):
    feed_id = _seed_three(tmp_db)
    resp = client.get(f"/api/articles?feed_id={feed_id}&limit=999")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 3
    assert len(data["articles"]) == 3


def test_valid_slice(client, tmp_db):
    feed_id = _seed_three(tmp_db)
    resp1 = client.get(f"/api/articles?feed_id={feed_id}&limit=3&offset=0")
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    assert len(data1["articles"]) == 3
    second_article_id = data1["articles"][1]["id"]

    resp2 = client.get(f"/api/articles?feed_id={feed_id}&limit=2&offset=1")
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert len(data2["articles"]) == 2
    assert data2["articles"][0]["id"] == second_article_id
