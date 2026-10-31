def test_create_feed_interval_bool_true_v141(client, tmp_db):
    url = "http://example.com/v141-true.xml"
    resp = client.post("/api/feeds", json={"feed_url": url, "interval_min": True})
    assert resp.status_code == 400
    assert "interval_min 非法" in resp.get_json().get("error", "")
    feeds = client.get("/api/feeds").get_json()
    assert not any(f["feed_url"] == url for f in feeds)

def test_create_feed_interval_bool_false_v141(client, tmp_db):
    url = "http://example.com/v141-false.xml"
    resp = client.post("/api/feeds", json={"feed_url": url, "interval_min": False})
    assert resp.status_code == 400
    assert "interval_min 非法" in resp.get_json().get("error", "")
    feeds = client.get("/api/feeds").get_json()
    assert not any(f["feed_url"] == url for f in feeds)

def test_create_feed_interval_float_1_5_v141(client, tmp_db):
    url = "http://example.com/v141-float-1-5.xml"
    resp = client.post("/api/feeds", json={"feed_url": url, "interval_min": 1.5})
    assert resp.status_code == 400
    assert "interval_min 非法" in resp.get_json().get("error", "")
    feeds = client.get("/api/feeds").get_json()
    assert not any(f["feed_url"] == url for f in feeds)

def test_create_feed_interval_float_2_0_v141(client, tmp_db):
    url = "http://example.com/v141-float-2-0.xml"
    resp = client.post("/api/feeds", json={"feed_url": url, "interval_min": 2.0})
    assert resp.status_code == 400
    assert "interval_min 非法" in resp.get_json().get("error", "")
    feeds = client.get("/api/feeds").get_json()
    assert not any(f["feed_url"] == url for f in feeds)

def test_create_feed_interval_int_regression_v141(client, tmp_db):
    url = "http://example.com/v141-int.xml"
    resp = client.post("/api/feeds", json={"feed_url": url, "interval_min": 30})
    assert resp.status_code == 201
    assert resp.get_json().get("interval_min") == 30

def test_create_feed_interval_default_regression_v141(client, tmp_db):
    url = "http://example.com/v141-default.xml"
    resp = client.post("/api/feeds", json={"feed_url": url})
    assert resp.status_code == 201
    assert resp.get_json().get("interval_min") == 0

def test_create_feed_interval_str_regression_v141(client, tmp_db):
    url = "http://example.com/v141-str.xml"
    resp = client.post("/api/feeds", json={"feed_url": url, "interval_min": "30"})
    assert resp.status_code == 201
    assert resp.get_json().get("interval_min") == 30