
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


def test_limit_invalid_returns_400(client, tmp_db):
    fid = _seed_three(tmp_db)

    resp = client.get(f"/api/articles?feed_id={fid}&limit=abc")
    assert resp.status_code == 400
    assert "limit 参数非法" in resp.get_json()["error"]

    resp = client.get(f"/api/articles?feed_id={fid}&limit=-3")
    assert resp.status_code == 400
    assert "limit 参数非法" in resp.get_json()["error"]

    resp = client.get(f"/api/articles?feed_id={fid}&limit=")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 3
    assert len(data["articles"]) == 3


def test_offset_invalid_returns_400(client, tmp_db):
    fid = _seed_three(tmp_db)

    resp = client.get(f"/api/articles?feed_id={fid}&offset=7x")
    assert resp.status_code == 400
    assert "offset 参数非法" in resp.get_json()["error"]


def test_limit_offset_slice(client, tmp_db):
    fid = _seed_three(tmp_db)

    resp = client.get(f"/api/articles?feed_id={fid}&limit=3&offset=0")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["articles"]) == 3
    second_id = data["articles"][1]["id"]

    resp = client.get(f"/api/articles?feed_id={fid}&limit=2&offset=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["articles"]) == 2
    assert data["articles"][0]["id"] == second_id