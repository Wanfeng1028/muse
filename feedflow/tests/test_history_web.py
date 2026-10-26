import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _articles(client):
    return client.get("/api/articles?scope=all").get_json()["articles"]


def test_history_page_empty(client):
    resp = client.get("/history")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "阅读历史" in html
    assert "还没有阅读历史，去阅读器打开一篇文章吧。" in html


def test_history_page_lists_recorded(client):
    articles = _articles(client)[:2]
    for article in articles:
        client.post(f"/api/articles/{article['id']}/history")
    html = client.get("/history").get_data(as_text=True)
    for article in articles:
        assert article["title"] in html
    assert "读过 1 次" in html


def test_history_page_clear(client):
    article = _articles(client)[0]
    client.post(f"/api/articles/{article['id']}/history")
    resp = client.post("/history/clear", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "阅读历史已清空。" in html
    assert "还没有阅读历史，去阅读器打开一篇文章吧。" in html


def test_reader_foot_history_link(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "阅读历史" in html
    assert "/history" in html
