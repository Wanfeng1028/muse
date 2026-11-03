import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _ids(client):
    return [
        a["id"]
        for a in client.get("/api/articles?scope=all").get_json()["articles"]
    ]


def test_api_history_empty(client):
    assert client.get("/api/history").get_json()["history"] == []


def test_api_history_missing_404(client):
    resp = client.post("/api/articles/99999/history")
    assert resp.status_code == 404


def test_api_history_record_counts(client):
    article_id = _ids(client)[0]

    first = client.post(f"/api/articles/{article_id}/history")
    assert first.status_code == 200
    data = first.get_json()
    assert data["recorded"] is True
    assert data["read_count"] == 1

    second = client.post(f"/api/articles/{article_id}/history").get_json()
    assert second["read_count"] == 2


def test_api_history_order_by_recent(client):
    ids = _ids(client)
    a, b = ids[0], ids[1]
    client.post(f"/api/articles/{a}/history")
    client.post(f"/api/articles/{b}/history")
    client.post(f"/api/articles/{a}/history")
    resp = client.get("/api/history")
    history = resp.get_json()["history"]
    assert [row["article_id"] for row in history] == [a, b]


def test_api_history_delete_clears(client):
    ids = _ids(client)
    a, b = ids[0], ids[1]
    client.post(f"/api/articles/{a}/history")
    client.post(f"/api/articles/{b}/history")
    resp = client.delete("/api/history")
    assert resp.get_json()["cleared"] == 2
    assert client.get("/api/history").get_json()["history"] == []
    resp_again = client.delete("/api/history")
    assert resp_again.get_json()["cleared"] == 0
