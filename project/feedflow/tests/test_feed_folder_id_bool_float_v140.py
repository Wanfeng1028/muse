from feedflow import store


def test_create_feed_folder_id_bool_true_v140(client, tmp_db):
    resp = client.post("/api/feeds", json={"feed_url": "http://example.com/v140-true.xml", "folder_id": True})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "folder_id 非法"
    feeds = client.get("/api/feeds").get_json()
    assert all(f["feed_url"] != "http://example.com/v140-true.xml" for f in feeds)


def test_create_feed_folder_id_bool_false_v140(client, tmp_db):
    resp = client.post("/api/feeds", json={"feed_url": "http://example.com/v140-false.xml", "folder_id": False})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "folder_id 非法"
    feeds = client.get("/api/feeds").get_json()
    assert all(f["feed_url"] != "http://example.com/v140-false.xml" for f in feeds)


def test_create_feed_folder_id_float_1_5_v140(client, tmp_db):
    resp = client.post("/api/feeds", json={"feed_url": "http://example.com/v140-float-1-5.xml", "folder_id": 1.5})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "folder_id 非法"
    feeds = client.get("/api/feeds").get_json()
    assert all(f["feed_url"] != "http://example.com/v140-float-1-5.xml" for f in feeds)


def test_create_feed_folder_id_float_2_0_v140(client, tmp_db):
    resp = client.post("/api/feeds", json={"feed_url": "http://example.com/v140-float-2-0.xml", "folder_id": 2.0})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "folder_id 非法"
    feeds = client.get("/api/feeds").get_json()
    assert all(f["feed_url"] != "http://example.com/v140-float-2-0.xml" for f in feeds)


def test_create_feed_folder_id_int_regression_v140(client, tmp_db):
    resp = client.post("/api/feeds", json={"feed_url": "http://example.com/v140-int-2.xml", "folder_id": 2})
    assert resp.status_code == 201
    assert resp.get_json()["folder_id"] == 2
    resp2 = client.post("/api/feeds", json={"feed_url": "http://example.com/v140-int-default.xml"})
    assert resp2.status_code == 201



def test_update_feed_folder_id_bool_true_v140(client, tmp_db):
    url = "http://example.com/v140-upd-bool-true.xml"
    fid = store.create_feed(str(tmp_db), url)
    resp = client.put(f"/api/feeds/{fid}", json={"folder_id": True})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "folder_id 非法"
    assert store.get_feed(str(tmp_db), fid)["folder_id"] is None

def test_update_feed_folder_id_float_1_5_v140(client, tmp_db):
    url = "http://example.com/v140-upd-float-1-5.xml"
    fid = store.create_feed(str(tmp_db), url)
    resp = client.put(f"/api/feeds/{fid}", json={"folder_id": 1.5})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "folder_id 非法"
    assert store.get_feed(str(tmp_db), fid)["folder_id"] is None

def test_update_feed_folder_id_bool_false_v140(client, tmp_db):
    url = "http://example.com/v140-upd-bool-false.xml"
    fid = store.create_feed(str(tmp_db), url)
    resp = client.put(f"/api/feeds/{fid}", json={"folder_id": False})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "folder_id 非法"
    assert store.get_feed(str(tmp_db), fid)["folder_id"] is None

def test_update_feed_folder_id_int_regression_v140(client, tmp_db):
    url = "http://example.com/v140-upd-int-3.xml"
    fid = store.create_feed(str(tmp_db), url)
    resp = client.put(f"/api/feeds/{fid}", json={"folder_id": 3})
    assert resp.status_code == 200
    assert store.get_feed(str(tmp_db), fid)["folder_id"] == 3

def test_update_feed_missing_feed_bool_folder_id_v140(client, tmp_db):
    resp = client.put("/api/feeds/999999", json={"folder_id": True})
    assert resp.status_code == 404
