import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _ids(client):
    return [
        a["id"]
        for a in client.get("/api/articles?scope=all").get_json()["articles"]
    ]


def _clear_archived(client):
    archived = client.get("/api/archived").get_json()["archived"]
    for a in archived:
        client.post(f"/api/articles/{a['article_id']}/archive", json={"is_archived": 0})


def test_api_archived_list_only_archived(client):
    _clear_archived(client)
    ids = _ids(client)
    client.post(f"/api/articles/{ids[0]}/archive", json={"is_archived": 1})
    rows = client.get("/api/archived").get_json()["archived"]
    assert [r["article_id"] for r in rows] == [ids[0]]


def test_api_archived_archive_returns_time(client):
    ids = _ids(client)
    resp = client.post(f"/api/articles/{ids[0]}/archive", json={"is_archived": 1})
    body = resp.get_json()
    assert body["is_archived"] == 1
    assert body["archived_at"]
    resp = client.post(f"/api/articles/{ids[0]}/archive", json={"is_archived": 0})
    body = resp.get_json()
    assert body["is_archived"] == 0
    assert body["archived_at"] is None


def test_api_archived_unarchive_removes_from_list(client):
    _clear_archived(client)
    ids = _ids(client)
    client.post(f"/api/articles/{ids[0]}/archive", json={"is_archived": 1})
    client.post(f"/api/articles/{ids[1]}/archive", json={"is_archived": 1})
    client.post(f"/api/articles/{ids[0]}/archive", json={"is_archived": 0})
    rows = client.get("/api/archived").get_json()["archived"]
    assert [r["article_id"] for r in rows] == [ids[1]]


def test_api_archived_order_by_archived_at(client):
    _clear_archived(client)
    ids = _ids(client)
    client.post(f"/api/articles/{ids[0]}/archive", json={"is_archived": 1})
    client.post(f"/api/articles/{ids[1]}/archive", json={"is_archived": 1})
    rows = client.get("/api/archived").get_json()["archived"]
    assert [r["article_id"] for r in rows] == [ids[1], ids[0]]


def test_api_archived_row_shape(client):
    _clear_archived(client)
    ids = _ids(client)
    client.post(f"/api/articles/{ids[0]}/archive", json={"is_archived": 1})
    rows = client.get("/api/archived").get_json()["archived"]
    row = rows[0]
    for field in [
        "article_id",
        "title",
        "link",
        "feed_title",
        "published_at",
        "is_read",
        "is_starred",
        "is_archived",
        "archived_at",
    ]:
        assert field in row
    assert row["is_archived"]


def test_api_archived_missing_field_returns_400(client):
    ids = _ids(client)
    resp = client.post(f"/api/articles/{ids[0]}/archive", json={})
    assert resp.status_code == 400
    assert "is_archived 必填" in resp.get_json()["error"]


def test_api_archived_unknown_article_returns_404(client):
    resp = client.post("/api/articles/999999/archive", json={"is_archived": 1})
    assert resp.status_code == 404
