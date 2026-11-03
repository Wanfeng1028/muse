import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _first_article_id(client):
    r = client.get("/api/articles?scope=all")
    data = r.get_json()
    assert data["total"] > 0
    return data["articles"][0]["id"]


def test_api_tags_empty(client):
    r = client.get("/api/tags")
    assert r.status_code == 200
    assert r.get_json() == {"tags": []}


def test_api_create_tag(client):
    r = client.post("/api/tags", json={"name": "  AI "})
    assert r.status_code == 201
    body = r.get_json()
    assert body["name"] == "ai"
    r2 = client.post("/api/tags", json={"name": "  AI "})
    assert r2.status_code == 201
    assert r2.get_json()["id"] == body["id"]


def test_api_create_tag_empty(client):
    r = client.post("/api/tags", json={"name": "   "})
    assert r.status_code == 400


def test_api_article_tags_missing(client):
    r = client.get("/api/articles/999999/tags")
    assert r.status_code == 404


def test_api_add_tag_by_name(client):
    article_id = _first_article_id(client)
    r = client.post(f"/api/articles/{article_id}/tags", json={"name": "tech"})
    assert r.status_code == 200
    assert r.get_json()["added"] is True
    data = client.get(f"/api/articles/{article_id}/tags").get_json()
    tags = data["tags"] if isinstance(data, dict) else data
    names = [t["name"] if isinstance(t, dict) else t for t in tags]
    assert "tech" in names


def test_api_add_tag_duplicate_and_missing(client):
    article_id = _first_article_id(client)
    tag_id = client.post("/api/tags", json={"name": "dup"}).get_json()["id"]
    r1 = client.post(f"/api/articles/{article_id}/tags", json={"tag_id": tag_id})
    assert r1.get_json()["added"] is True
    r2 = client.post(f"/api/articles/{article_id}/tags", json={"tag_id": tag_id})
    assert r2.get_json()["added"] is False
    r3 = client.post(f"/api/articles/{article_id}/tags", json={"tag_id": 999999})
    assert r3.status_code == 404


def test_api_delete_tag(client):
    article_id = _first_article_id(client)
    tag_id = client.post("/api/tags", json={"name": "del"}).get_json()["id"]
    client.post(f"/api/articles/{article_id}/tags", json={"tag_id": tag_id})
    r1 = client.delete(f"/api/articles/{article_id}/tags/{tag_id}")
    assert r1.get_json()["removed"] is True
    r2 = client.delete(f"/api/articles/{article_id}/tags/{tag_id}")
    assert r2.get_json()["removed"] is False


def test_api_articles_tag_filter(client):
    article_id = _first_article_id(client)
    tag_id = client.post("/api/tags", json={"name": "solo"}).get_json()["id"]
    client.post(f"/api/articles/{article_id}/tags", json={"tag_id": tag_id})
    data = client.get(f"/api/articles?scope=all&tag_id={tag_id}").get_json()
    assert data["total"] == 1


def test_tags_page_and_forms(client):
    page = client.get("/tags")
    assert page.status_code == 200
    assert "标签" in page.get_data(as_text=True)
    assert client.post("/tags", data={"name": "web"}).status_code == 302
    article_id = _first_article_id(client)
    assert client.post("/tags/assign", data={"article_id": article_id, "name": "web"}).status_code == 302
    web_id = next(t["id"] for t in client.get("/api/tags").get_json()["tags"] if t["name"] == "web")
    title = client.get("/api/articles?scope=all").get_json()["articles"][0]["title"]
    assert title in client.get(f"/tags?tag_id={web_id}").get_data(as_text=True)
    assert client.post("/tags/unassign", data={"article_id": article_id, "tag_id": web_id}).status_code == 302
