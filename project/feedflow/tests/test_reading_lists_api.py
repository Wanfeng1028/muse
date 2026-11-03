import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


def _clear(client):
    rows = client.get("/api/reading-lists").get_json()["reading_lists"]
    for r in rows:
        client.delete(f"/api/reading-lists/{r['id']}")


def _first_article_id(client):
    articles = client.get("/api/articles?scope=all&limit=200").get_json()["articles"]
    if not articles:
        pytest.skip("隔离库无可用文章，跳过成员相关断言")
    return articles[0]["id"]


def test_api_reading_lists_create_and_list(client):
    _clear(client)
    resp = client.post("/api/reading-lists", json={"name": "周末深读"})
    assert resp.status_code == 200
    row = resp.get_json()
    assert row["name"] == "周末深读"
    assert isinstance(row["id"], int)

    names = [r["name"] for r in client.get("/api/reading-lists").get_json()["reading_lists"]]
    assert "周末深读" in names


def test_api_reading_lists_duplicate_reuses(client):
    _clear(client)
    first = client.post("/api/reading-lists", json={"name": "技术长文"}).get_json()
    second = client.post("/api/reading-lists", json={"name": "技术长文"}).get_json()
    assert second["id"] == first["id"]

    rows = client.get("/api/reading-lists").get_json()["reading_lists"]
    assert len(rows) == 1


def test_api_reading_lists_empty_returns_400(client):
    _clear(client)
    resp = client.post("/api/reading-lists", json={"name": "   "})
    assert resp.status_code == 400
    assert "清单名为空" in resp.get_json()["error"]

    resp = client.post("/api/reading-lists", json={})
    assert resp.status_code == 400
    assert "清单名为空" in resp.get_json()["error"]


def test_api_reading_lists_delete_and_unknown_404(client):
    _clear(client)
    row = client.post("/api/reading-lists", json={"name": "一次性清单"}).get_json()
    resp = client.delete(f"/api/reading-lists/{row['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["removed"] is True

    resp = client.delete(f"/api/reading-lists/{row['id']}")
    assert resp.status_code == 404
    assert "阅读清单不存在" in resp.get_json()["error"]


def test_api_reading_lists_members_add_and_list(client):
    _clear(client)
    article_id = _first_article_id(client)
    lst = client.post("/api/reading-lists", json={"name": "成员清单"}).get_json()

    resp = client.post(f"/api/reading-lists/{lst['id']}/articles", json={"article_id": article_id})
    assert resp.status_code == 200

    rows = client.get(f"/api/reading-lists/{lst['id']}/articles").get_json()["articles"]
    assert [r["article_id"] for r in rows] == [article_id]
    assert len(rows) == 1

    client.post(f"/api/reading-lists/{lst['id']}/articles", json={"article_id": article_id})
    rows = client.get(f"/api/reading-lists/{lst['id']}/articles").get_json()["articles"]
    assert len(rows) == 1


def test_api_reading_lists_members_add_errors(client):
    _clear(client)
    resp = client.post("/api/reading-lists/999999/articles", json={"article_id": 1})
    assert resp.status_code == 404

    lst = client.post("/api/reading-lists", json={"name": "报错清单"}).get_json()

    resp = client.post(f"/api/reading-lists/{lst['id']}/articles", json={"article_id": 999999})
    assert resp.status_code == 404

    resp = client.post(f"/api/reading-lists/{lst['id']}/articles", json={"article_id": "abc"})
    assert resp.status_code == 400
    assert "article_id 非法" in resp.get_json()["error"]

    resp = client.get("/api/reading-lists/999999/articles")
    assert resp.status_code == 404


def test_api_reading_lists_members_remove(client):
    _clear(client)
    article_id = _first_article_id(client)
    lst = client.post("/api/reading-lists", json={"name": "移除清单"}).get_json()
    client.post(f"/api/reading-lists/{lst['id']}/articles", json={"article_id": article_id})

    resp = client.delete(f"/api/reading-lists/{lst['id']}/articles/{article_id}")
    assert resp.status_code == 200
    assert resp.get_json()["removed"] is True

    resp = client.delete(f"/api/reading-lists/{lst['id']}/articles/{article_id}")
    assert resp.status_code == 404
    assert "文章不在清单中" in resp.get_json()["error"]


def test_api_reading_lists_row_shape(client):
    _clear(client)
    article_id = _first_article_id(client)
    lst = client.post("/api/reading-lists", json={"name": "字段清单"}).get_json()
    client.post(f"/api/reading-lists/{lst['id']}/articles", json={"article_id": article_id})

    rows = client.get(f"/api/reading-lists/{lst['id']}/articles").get_json()["articles"]
    assert len(rows) == 1
    assert set(rows[0].keys()) == {
        "article_id",
        "title",
        "link",
        "feed_title",
        "published_at",
        "is_read",
        "is_starred",
        "added_at",
    }

    lists = client.get("/api/reading-lists").get_json()["reading_lists"]
    target = next(r for r in lists if r["id"] == lst["id"])
    assert {"id", "name", "created_at", "article_count"} <= set(target.keys())
