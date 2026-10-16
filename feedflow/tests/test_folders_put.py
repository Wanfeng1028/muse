
def _create_folder(client, name):
    resp = client.post("/api/folders", json={"name": name})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["name"] == name
    return body["id"]


def _list_folders(client):
    resp = client.get("/api/folders")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def test_put_rename(client):
    fid = _create_folder(client, "工作")

    resp = client.put(f"/api/folders/{fid}", json={"name": "学习"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["id"] == fid
    assert body["name"] == "学习"
    assert "position" in body

    folders = _list_folders(client)
    matched = [f for f in folders if f["id"] == fid]
    assert len(matched) == 1
    assert matched[0]["name"] == "学习"


def test_put_position(client):
    a_id = _create_folder(client, "A")
    b_id = _create_folder(client, "B")

    resp = client.put(f"/api/folders/{b_id}", json={"position": -5})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["position"] == -5

    folders = _list_folders(client)
    ids = [f["id"] for f in folders]
    assert b_id in ids
    assert a_id in ids
    assert ids.index(b_id) < ids.index(a_id)


def test_put_404(client):
    resp = client.put("/api/folders/999999", json={"name": "x"})
    assert resp.status_code == 404, resp.get_data(as_text=True)
    body = resp.get_json()
    assert "error" in body
    assert "不存在" in body["error"]


def test_put_empty_name_400(client):
    fid = _create_folder(client, "原始名")

    resp = client.put(f"/api/folders/{fid}", json={"name": "   "})
    assert resp.status_code == 400, resp.get_data(as_text=True)

    folders = _list_folders(client)
    matched = [f for f in folders if f["id"] == fid]
    assert len(matched) == 1
    assert matched[0]["name"] == "原始名"


def test_put_invalid_position_400(client):
    fid = _create_folder(client, "分组")

    resp = client.put(f"/api/folders/{fid}", json={"position": "abc"})
    assert resp.status_code == 400, resp.get_data(as_text=True)


def test_put_name_and_position(client):
    fid = _create_folder(client, "旧名")

    resp = client.put(f"/api/folders/{fid}", json={"name": "新名", "position": 3})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["id"] == fid
    assert body["name"] == "新名"
    assert body["position"] == 3

    folders = _list_folders(client)
    matched = [f for f in folders if f["id"] == fid]
    assert len(matched) == 1
    assert matched[0]["name"] == "新名"
    assert matched[0]["position"] == 3


def test_put_404_no_side_effect(client):
    before = _list_folders(client)

    resp = client.put(
        "/api/folders/999999",
        json={"name": "幽灵", "position": 7},
    )
    assert resp.status_code == 404, resp.get_data(as_text=True)
    body = resp.get_json()
    assert "error" in body
    assert "不存在" in body["error"]

    after = _list_folders(client)
    assert after == before
    assert all(f["name"] != "幽灵" for f in after)
