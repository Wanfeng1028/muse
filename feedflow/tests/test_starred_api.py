import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _ids(client):
    return [
        a["id"]
        for a in client.get("/api/articles?scope=all").get_json()["articles"]
    ]


def _clear_starred(client):
    starred = client.get("/api/articles?scope=starred").get_json()["articles"]
    for a in starred:
        client.post(f"/api/articles/{a['id']}/star", json={"is_starred": 0})


def test_api_starred_list_only_starred(client):
    _clear_starred(client)
    ids = _ids(client)
    client.post(f"/api/articles/{ids[0]}/star", json={"is_starred": 1})
    rows = client.get("/api/starred").get_json()["starred"]
    assert [r["article_id"] for r in rows] == [ids[0]]


def test_api_starred_star_returns_time(client):
    ids = _ids(client)
    resp = client.post(f"/api/articles/{ids[0]}/star", json={"is_starred": 1})
    data = resp.get_json()
    assert data["is_starred"] == 1
    assert data["starred_at"]

    resp = client.post(f"/api/articles/{ids[0]}/star", json={"is_starred": 0})
    data = resp.get_json()
    assert data["is_starred"] == 0
    assert data["starred_at"] is None


def test_api_starred_unstar_removes_from_list(client):
    _clear_starred(client)
    ids = _ids(client)
    client.post(f"/api/articles/{ids[0]}/star", json={"is_starred": 1})
    client.post(f"/api/articles/{ids[1]}/star", json={"is_starred": 1})
    client.post(f"/api/articles/{ids[0]}/star", json={"is_starred": 0})
    rows = client.get("/api/starred").get_json()["starred"]
    assert [r["article_id"] for r in rows] == [ids[1]]


def test_api_starred_order_by_starred_at(client):
    _clear_starred(client)
    ids = _ids(client)
    client.post(f"/api/articles/{ids[0]}/star", json={"is_starred": 1})
    client.post(f"/api/articles/{ids[1]}/star", json={"is_starred": 1})
    rows = client.get("/api/starred").get_json()["starred"]
    assert [r["article_id"] for r in rows] == [ids[1], ids[0]]


def test_api_starred_row_shape(client):
    _clear_starred(client)
    ids = _ids(client)
    client.post(f"/api/articles/{ids[0]}/star", json={"is_starred": 1})
    rows = client.get("/api/starred").get_json()["starred"]
    assert len(rows) == 1
    row = rows[0]
    for key in ("article_id", "title", "feed_title", "starred_at"):
        assert key in row
    assert row["is_starred"]
    assert row["starred_at"]
