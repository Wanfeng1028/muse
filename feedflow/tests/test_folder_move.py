import pytest


def _create_folder(client, name):
    resp = client.post("/api/folders", json={"name": name})
    assert resp.status_code == 201
    return resp.get_json()


def _folder_names(client):
    resp = client.get("/api/folders")
    assert resp.status_code == 200
    data = resp.get_json()
    return [f["name"] for f in data]


def _abc_order(client):
    names = _folder_names(client)
    return [n for n in names if n in ("A", "B", "C")]


def _move(client, folder_id, direction):
    return client.post(
        f"/api/folders/{folder_id}/move",
        json={"direction": direction},
    )


@pytest.mark.parametrize("direction", ["", "left", "right", "UP", "Down", "  "])
def test_move_rejects_invalid_direction(client, direction):
    folder = _create_folder(client, "A")
    resp = _move(client, folder["id"], direction)
    assert resp.status_code == 400


def test_move_rejects_missing_direction(client):
    folder = _create_folder(client, "A")
    resp = client.post(f"/api/folders/{folder['id']}/move", json={})
    assert resp.status_code == 400


def test_move_rejects_unknown_folder(client):
    resp = _move(client, 999999, "up")
    assert resp.status_code == 404


def test_move_up_reorders_folders(client):
    _create_folder(client, "A")
    _create_folder(client, "B")
    c = _create_folder(client, "C")
    assert _abc_order(client) == ["A", "B", "C"]

    resp = _move(client, c["id"], "up")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["moved"] is True
    assert body["folder"]["name"] == "C"
    assert _abc_order(client) == ["A", "C", "B"]

    resp = _move(client, c["id"], "up")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["moved"] is True
    assert body["folder"]["name"] == "C"
    assert _abc_order(client) == ["C", "A", "B"]


def test_move_down_reorders_folders(client):
    a = _create_folder(client, "A")
    _create_folder(client, "B")
    _create_folder(client, "C")
    assert _abc_order(client) == ["A", "B", "C"]

    resp = _move(client, a["id"], "down")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["moved"] is True
    assert body["folder"]["name"] == "A"
    assert _abc_order(client) == ["B", "A", "C"]

    resp = _move(client, a["id"], "down")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["moved"] is True
    assert body["folder"]["name"] == "A"
    assert _abc_order(client) == ["B", "C", "A"]


def test_move_up_on_top_folder_is_noop(client):
    _create_folder(client, "A")
    _create_folder(client, "B")
    top_id = client.get("/api/folders").get_json()[0]["id"]
    before = _folder_names(client)

    resp = _move(client, top_id, "up")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["moved"] is False
    assert _folder_names(client) == before


def test_move_down_on_bottom_folder_is_noop(client):
    _create_folder(client, "A")
    b = _create_folder(client, "B")
    assert _abc_order(client) == ["A", "B"]

    resp = _move(client, b["id"], "down")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["moved"] is False
    assert body["folder"]["name"] == "B"
    assert _abc_order(client) == ["A", "B"]


def test_move_keeps_feeds_in_folder(client):
    _create_folder(client, "A")
    _create_folder(client, "B")
    c = _create_folder(client, "C")

    feed_resp = client.post(
        "/api/feeds",
        json={"feed_url": "http://example.invalid/rss", "folder_id": c["id"]},
    )
    assert feed_resp.status_code == 201

    resp = _move(client, c["id"], "up")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["moved"] is True
    assert body["folder"]["name"] == "C"

    resp = client.get("/api/folders")
    assert resp.status_code == 200
    folders = resp.get_json()
    names = [f["name"] for f in folders]
    assert [n for n in names if n in ("A", "B", "C")] == ["A", "C", "B"]

    by_name = {f["name"]: f for f in folders}
    assert "feeds" in by_name["C"]
    titles = [feed["title"] for feed in by_name["C"]["feeds"]]
    assert titles == ["http://example.invalid/rss"]
