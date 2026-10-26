import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def seed_articles(client):
    return client.get("/api/articles?scope=all").get_json()["articles"]


def later_ids(client):
    return [item["article_id"] for item in client.get("/api/later").get_json()["later"]]


def test_later_page_empty(client):
    resp = client.get("/later")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "稍后读" in html
    assert "还没有稍后读的文章" in html


def test_later_page_lists_in_order(client):
    articles = seed_articles(client)[:2]
    for article in articles:
        client.post(f"/api/articles/{article['id']}/later")
    html = client.get("/later").get_data(as_text=True)
    assert html.index(articles[0]["title"]) < html.index(articles[1]["title"])


def test_later_web_move(client):
    a, b = seed_articles(client)[:2]
    client.post(f"/api/articles/{a['id']}/later")
    client.post(f"/api/articles/{b['id']}/later")
    resp = client.post(
        "/later/move",
        data={"article_id": b["id"], "direction": "up"},
        follow_redirects=True,
    )
    assert "顺序已调整。" in resp.get_data(as_text=True)
    assert later_ids(client) == [b["id"], a["id"]]


def test_later_web_remove(client):
    article = seed_articles(client)[0]
    client.post(f"/api/articles/{article['id']}/later")
    resp = client.post(
        "/later/remove",
        data={"article_id": article["id"]},
        follow_redirects=True,
    )
    assert "已移出队列。" in resp.get_data(as_text=True)
    assert later_ids(client) == []


def test_later_web_bad_form(client):
    resp = client.post("/later/move", data={"direction": "up"})
    assert resp.status_code == 302
    assert "err=bad" in resp.headers["Location"]
