import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


def _get_lists(client):
    resp = client.get("/api/reading-lists")
    data = resp.get_json()
    if isinstance(data, dict):
        data = data.get("reading_lists") or []
    return data if isinstance(data, list) else []


def _clear(client):
    for item in _get_lists(client):
        list_id = item.get("id") if isinstance(item, dict) else item
        if list_id is not None:
            client.post("/reading-lists/delete", data={"list_id": str(list_id)})


def _find_list_id(client, name):
    for item in _get_lists(client):
        if isinstance(item, dict) and item.get("name") == name:
            return item.get("id")
    return None


def _create_list(client, name):
    client.post("/api/reading-lists", json={"name": name})
    return _find_list_id(client, name)


def _first_article(client):
    resp = client.get("/api/articles?scope=all&limit=200")
    data = resp.get_json()
    if isinstance(data, dict):
        data = data.get("articles") or data.get("items") or data.get("data") or []
    art = data[0] if data else None
    article_id = None
    title = None
    if isinstance(art, dict):
        article_id = art.get("id") or art.get("article_id")
        title = art.get("title")
    if article_id is None or not title:
        pytest.skip("no articles available")
    return str(article_id), title


def test_reading_lists_page_empty(client):
    _clear(client)
    resp = client.get("/reading-lists")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "阅读清单" in html
    assert "还没有阅读清单，新建一个，把想慢慢读的文章收进来吧。" in html


def test_reading_lists_page_lists_created(client):
    _clear(client)
    client.post("/api/reading-lists", json={"name": "周末深读"})
    resp = client.get("/reading-lists")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "周末深读" in html
    assert "新建清单" in html
    assert "删除清单" in html
    assert "按文章 ID 加入" in html
    assert "这个清单还没有文章。" in html


def test_reading_lists_create_form_redirect(client):
    _clear(client)
    resp = client.post("/reading-lists/create", data={"name": "表单清单"})
    assert resp.status_code in (301, 302, 303)
    assert "created=1" in resp.headers.get("Location", "")
    html = client.get("/reading-lists").get_data(as_text=True)
    assert "表单清单" in html


def test_reading_lists_delete_form_redirect(client):
    _clear(client)
    list_id = _create_list(client, "待删清单")
    assert list_id is not None
    resp = client.post("/reading-lists/delete", data={"list_id": str(list_id)})
    assert resp.status_code in (301, 302, 303)
    assert "removed=1" in resp.headers.get("Location", "")
    html = client.get("/reading-lists").get_data(as_text=True)
    assert "待删清单" not in html


def test_reading_lists_add_remove_form_redirect(client):
    _clear(client)
    list_id = _create_list(client, "稍后读样例")
    assert list_id is not None
    article_id, title = _first_article(client)

    resp = client.post(f"/reading-lists/{list_id}/add", data={"article_id": article_id})
    assert resp.status_code in (301, 302, 303)
    assert "added=1" in resp.headers.get("Location", "")
    html = client.get("/reading-lists").get_data(as_text=True)
    assert title in html

    resp = client.post(f"/reading-lists/{list_id}/remove", data={"article_id": article_id})
    assert resp.status_code in (301, 302, 303)
    assert "removed=1" in resp.headers.get("Location", "")
    html = client.get("/reading-lists").get_data(as_text=True)
    assert title not in html


def test_reading_lists_reader_footer_link(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "阅读清单" in html
    assert "/reading-lists" in html
