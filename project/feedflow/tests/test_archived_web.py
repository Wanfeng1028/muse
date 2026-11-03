import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _articles(client):
    return client.get("/api/articles?scope=all").get_json()["articles"]


def _clear_archived(client):
    archived = client.get("/api/archived").get_json()["archived"]
    for a in archived:
        client.post(f"/api/articles/{a['article_id']}/archive", json={"is_archived": 0})


EMPTY_HINT = "还没有归档文章，去阅读器打开一篇文章点“归档”吧。"


def test_archived_page_empty(client):
    _clear_archived(client)
    resp = client.get("/archived")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "文章归档" in html
    assert EMPTY_HINT in html


def test_archived_page_lists_archived(client):
    _clear_archived(client)
    articles = _articles(client)[:2]
    for a in articles:
        client.post(f"/api/articles/{a['id']}/archive", json={"is_archived": 1})
    resp = client.get("/archived")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for a in articles:
        assert a["title"] in html
    assert "取消归档" in html


def test_archived_page_unarchive(client):
    _clear_archived(client)
    a = _articles(client)[0]
    client.post(f"/api/articles/{a['id']}/archive", json={"is_archived": 1})
    resp = client.post(
        "/archived/unarchive", data={"article_id": a["id"]}, follow_redirects=True
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "已取消归档。" in html
    assert EMPTY_HINT in html


def test_reader_foot_archived_link(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "文章归档" in html
    assert "/archived" in html
