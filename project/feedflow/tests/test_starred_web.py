import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _articles(client):
    return client.get("/api/articles?scope=all").get_json()["articles"]


def _clear_starred(client):
    starred = client.get("/api/articles?scope=starred").get_json()["articles"]
    for a in starred:
        client.post(f"/api/articles/{a['id']}/star", json={"is_starred": 0})


EMPTY_HINT = "还没有星标文章，去阅读器打开一篇文章点“星标”吧。"


def test_starred_page_empty(client):
    _clear_starred(client)
    resp = client.get("/starred")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "星标收藏" in html
    assert EMPTY_HINT in html


def test_starred_page_lists_starred(client):
    _clear_starred(client)
    articles = _articles(client)[:2]
    for a in articles:
        client.post(f"/api/articles/{a['id']}/star", json={"is_starred": 1})
    resp = client.get("/starred")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for a in articles:
        assert a["title"] in html
    assert "取消星标" in html


def test_starred_page_unstar(client):
    _clear_starred(client)
    a = _articles(client)[0]
    client.post(f"/api/articles/{a['id']}/star", json={"is_starred": 1})
    resp = client.post(
        "/starred/unstar", data={"article_id": a["id"]}, follow_redirects=True
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "已取消星标。" in html
    assert EMPTY_HINT in html


def test_reader_foot_starred_link(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "星标收藏" in html
    assert "/starred" in html
