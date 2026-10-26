import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _ids3(client):
    return [
        a["id"]
        for a in client.get("/api/articles?scope=all").get_json()["articles"][:3]
    ]


def _queue(client, aid):
    client.post(f"/api/articles/{aid}/later")


def test_api_later_empty(client):
    assert client.get("/api/later").get_json()["later"] == []


def test_api_queue_and_get(client):
    aid = _ids3(client)[0]
    rv = client.post(f"/api/articles/{aid}/later")
    assert rv.status_code == 200
    assert rv.get_json()["queued"] is True
    rv = client.get(f"/api/articles/{aid}/later")
    assert rv.status_code == 200
    assert rv.get_json()["queued"] is True


def test_api_queue_dup(client):
    aid = _ids3(client)[0]
    assert client.post(f"/api/articles/{aid}/later").status_code == 200
    rv = client.post(f"/api/articles/{aid}/later")
    assert rv.status_code == 200
    assert rv.get_json()["queued"] is False


def test_api_missing_404(client):
    assert client.post("/api/articles/999999/later").status_code == 404
    assert client.get("/api/articles/999999/later").status_code == 404


def test_api_delete(client):
    aid = _ids3(client)[0]
    _queue(client, aid)
    rv = client.delete(f"/api/articles/{aid}/later")
    assert rv.status_code == 200
    assert rv.get_json()["removed"] is True
    rv = client.delete(f"/api/articles/{aid}/later")
    assert rv.status_code == 200
    assert rv.get_json()["removed"] is False


def test_api_move(client):
    ids = _ids3(client)
    for aid in ids:
        _queue(client, aid)
    rv = client.post(f"/api/articles/{ids[2]}/later/move", json={"direction": "up"})
    assert rv.status_code == 200
    later = client.get("/api/later").get_json()["later"]
    assert [x["article_id"] for x in later] == [ids[0], ids[2], ids[1]]
    client.post(f"/api/articles/{ids[0]}/later/move", json={"direction": "down"})
    later = client.get("/api/later").get_json()["later"]
    assert [x["article_id"] for x in later] == [ids[2], ids[0], ids[1]]


def test_api_move_bad_direction_400(client):
    aid = _ids3(client)[0]
    _queue(client, aid)
    rv = client.post(f"/api/articles/{aid}/later/move", json={"direction": "side"})
    assert rv.status_code == 400


def test_api_move_missing_404(client):
    rv = client.post("/api/articles/999999/later/move", json={"direction": "up"})
    assert rv.status_code == 404
