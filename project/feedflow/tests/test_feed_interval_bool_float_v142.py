def test_update_feed_interval_bool_true_v142(client, tmp_db):
    resp = client.post(
        "/api/feeds",
        json={"feed_url": "http://example.com/v142-true.xml", "interval_min": 30},
    )
    assert resp.status_code == 201
    feed_id = resp.get_json()["id"]

    resp = client.put(f"/api/feeds/{feed_id}", json={"interval_min": True})
    assert resp.status_code == 400
    assert "interval_min 非法" in resp.get_json()["error"]

    resp = client.get("/api/feeds")
    feed = next(
        f for f in resp.get_json() if f["feed_url"] == "http://example.com/v142-true.xml"
    )
    assert feed["interval_min"] == 30


def test_update_feed_interval_bool_false_v142(client, tmp_db):
    resp = client.post(
        "/api/feeds",
        json={"feed_url": "http://example.com/v142-false.xml", "interval_min": 30},
    )
    assert resp.status_code == 201
    feed_id = resp.get_json()["id"]

    resp = client.put(f"/api/feeds/{feed_id}", json={"interval_min": False})
    assert resp.status_code == 400
    assert "interval_min 非法" in resp.get_json()["error"]

    resp = client.get("/api/feeds")
    feed = next(
        f for f in resp.get_json() if f["feed_url"] == "http://example.com/v142-false.xml"
    )
    assert feed["interval_min"] == 30


def test_update_feed_interval_float_1_5_v142(client, tmp_db):
    resp = client.post(
        "/api/feeds",
        json={"feed_url": "http://example.com/v142-float15.xml", "interval_min": 30},
    )
    assert resp.status_code == 201
    feed_id = resp.get_json()["id"]

    resp = client.put(f"/api/feeds/{feed_id}", json={"interval_min": 1.5})
    assert resp.status_code == 400
    assert "interval_min 非法" in resp.get_json()["error"]

    resp = client.get("/api/feeds")
    feed = next(
        f for f in resp.get_json() if f["feed_url"] == "http://example.com/v142-float15.xml"
    )
    assert feed["interval_min"] == 30


def test_update_feed_interval_float_2_0_v142(client, tmp_db):
    resp = client.post(
        "/api/feeds",
        json={"feed_url": "http://example.com/v142-float20.xml", "interval_min": 30},
    )
    assert resp.status_code == 201
    feed_id = resp.get_json()["id"]

    resp = client.put(f"/api/feeds/{feed_id}", json={"interval_min": 2.0})
    assert resp.status_code == 400
    assert "interval_min 非法" in resp.get_json()["error"]

    resp = client.get("/api/feeds")
    feed = next(
        f for f in resp.get_json() if f["feed_url"] == "http://example.com/v142-float20.xml"
    )
    assert feed["interval_min"] == 30


def test_update_feed_interval_int_regression_v142(client, tmp_db):
    resp = client.post(
        "/api/feeds",
        json={"feed_url": "http://example.com/v142-int.xml", "interval_min": 30},
    )
    assert resp.status_code == 201
    feed_id = resp.get_json()["id"]

    resp = client.put(f"/api/feeds/{feed_id}", json={"interval_min": 45})
    assert resp.status_code == 200
    assert resp.get_json()["interval_min"] == 45


def test_update_feed_interval_str_regression_v142(client, tmp_db):
    resp = client.post(
        "/api/feeds",
        json={"feed_url": "http://example.com/v142-str.xml", "interval_min": 30},
    )
    assert resp.status_code == 201
    feed_id = resp.get_json()["id"]

    resp = client.put(f"/api/feeds/{feed_id}", json={"interval_min": "60"})
    assert resp.status_code == 200
    assert resp.get_json()["interval_min"] == 60


def test_update_feed_interval_missing_feed_bool_v142(client, tmp_db):
    resp = client.put("/api/feeds/999999", json={"interval_min": True})
    assert resp.status_code == 404
