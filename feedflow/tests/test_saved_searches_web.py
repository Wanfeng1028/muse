import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _clear(client):
    rows = client.get("/api/saved-searches").get_json()["saved_searches"]
    for r in rows:
        client.delete(f"/api/saved-searches/{r['id']}")


def test_saved_searches_page_empty(client):
    _clear(client)
    resp = client.get("/saved-searches")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "保存的搜索" in html
    assert "还没有保存的搜索，去搜索页搜一次并点“保存这次搜索”吧。" in html


def test_saved_searches_page_lists_saved(client):
    _clear(client)
    client.post("/api/saved-searches", json={"query": "AI 新闻"})
    resp = client.get("/saved-searches")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "AI 新闻" in html
    assert "删除" in html


def test_saved_searches_save_form_redirect(client):
    resp = client.post("/saved-searches/save", data={"q": "量子计算"})
    assert resp.status_code in (301, 302, 303)
    assert "saved=1" in resp.headers.get("Location", "")
    page = client.get("/saved-searches")
    assert page.status_code == 200
    assert "量子计算" in page.get_data(as_text=True)


def test_saved_searches_delete_form_redirect(client):
    _clear(client)
    client.post("/api/saved-searches", json={"query": "深度学习"})
    rows = client.get("/api/saved-searches").get_json()["saved_searches"]
    search_id = rows[0]["id"]
    resp = client.post("/saved-searches/delete", data={"search_id": str(search_id)})
    assert resp.status_code in (301, 302, 303)
    assert "removed=1" in resp.headers.get("Location", "")
    page = client.get("/saved-searches")
    assert page.status_code == 200
    assert "深度学习" not in page.get_data(as_text=True)


def test_saved_searches_entry_points(client):
    resp = client.get("/search?q=AI")
    assert resp.status_code == 200
    assert "保存这次搜索" in resp.get_data(as_text=True)
    home = client.get("/")
    assert home.status_code == 200
    assert "保存的搜索" in home.get_data(as_text=True)
