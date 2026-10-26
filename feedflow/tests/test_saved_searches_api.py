import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _clear(client):
    rows = client.get("/api/saved-searches").get_json()["saved_searches"]
    for r in rows:
        client.delete(f"/api/saved-searches/{r['id']}")


def test_api_saved_searches_create_and_list(client):
    _clear(client)
    resp = client.post("/api/saved-searches", json={"query": "AI 新闻"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["query"] == "AI 新闻"
    assert isinstance(body["id"], int)

    rows = client.get("/api/saved-searches").get_json()["saved_searches"]
    assert any(r["query"] == "AI 新闻" for r in rows)


def test_api_saved_searches_duplicate_reuses(client):
    _clear(client)
    first = client.post("/api/saved-searches", json={"query": "AI 新闻"}).get_json()
    second = client.post("/api/saved-searches", json={"query": "AI 新闻"}).get_json()
    assert first["id"] == second["id"]

    rows = client.get("/api/saved-searches").get_json()["saved_searches"]
    assert len(rows) == 1


def test_api_saved_searches_empty_returns_400(client):
    resp = client.post("/api/saved-searches", json={"query": "   "})
    assert resp.status_code == 400
    assert "搜索词为空" in resp.get_json()["error"]

    resp = client.post("/api/saved-searches", json={})
    assert resp.status_code == 400


def test_api_saved_searches_delete_removes(client):
    _clear(client)
    created = client.post("/api/saved-searches", json={"query": "AI 新闻"}).get_json()

    resp = client.delete(f"/api/saved-searches/{created['id']}")
    assert resp.get_json()["removed"] is True

    rows = client.get("/api/saved-searches").get_json()["saved_searches"]
    assert rows == []


def test_api_saved_searches_delete_unknown_404(client):
    resp = client.delete("/api/saved-searches/999999")
    assert resp.status_code == 404


def test_api_saved_searches_row_shape(client):
    _clear(client)
    client.post("/api/saved-searches", json={"query": "AI 新闻"})

    rows = client.get("/api/saved-searches").get_json()["saved_searches"]
    row = rows[0]
    assert "id" in row
    assert "query" in row
    assert "created_at" in row
