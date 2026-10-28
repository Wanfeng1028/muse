from feedflow import db, store


def _seed_three_clusters(db_path):
    db.execute_write(db_path, "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, 0, ?)", ("F", "http://example.com/feed", "2024-01-01T00:00:00"))
    rows = db.query_all(db_path, "SELECT id FROM feeds ORDER BY id DESC LIMIT 1")
    feed_id = rows[0]["id"]
    for i in range(3):
        store.insert_article(db_path, feed_id, f"g{i}", f"Article {i}", "author", f"http://example.com/link-{i}", "summary", "<p>content</p>", "content", None)


def test_n_abc_returns_400(client, tmp_db):
    _seed_three_clusters(tmp_db)
    resp = client.get("/api/clusters?n=abc")
    assert resp.status_code == 400
    assert "n 参数非法" in resp.get_json()["error"]


def test_n_float_returns_400(client, tmp_db):
    _seed_three_clusters(tmp_db)
    resp = client.get("/api/clusters?n=1.5")
    assert resp.status_code == 400
    assert "n 参数非法" in resp.get_json()["error"]


def test_n_zero_returns_400(client, tmp_db):
    _seed_three_clusters(tmp_db)
    resp = client.get("/api/clusters?n=0")
    assert resp.status_code == 400
    assert "n 参数非法" in resp.get_json()["error"]


def test_n_negative_returns_400(client, tmp_db):
    _seed_three_clusters(tmp_db)
    resp = client.get("/api/clusters?n=-5")
    assert resp.status_code == 400
    assert "n 参数非法" in resp.get_json()["error"]


def test_n_missing_defaults_to_10(client, tmp_db):
    _seed_three_clusters(tmp_db)
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == len(body["clusters"])


def test_n_empty_defaults_to_10(client, tmp_db):
    _seed_three_clusters(tmp_db)
    resp = client.get("/api/clusters?n=")
    assert resp.status_code == 200


def test_n_1_limits_to_one(client, tmp_db):
    _seed_three_clusters(tmp_db)
    resp = client.get("/api/clusters?n=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["clusters"]) <= 1
