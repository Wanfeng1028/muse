import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


def _get_lists(client):
    resp = client.get("/api/reading-lists")
    assert resp.status_code == 200
    return resp.get_json().get("reading_lists")


def _clear(client):
    for lst in _get_lists(client) or []:
        client.post("/reading-lists/delete", data={"list_id": str(lst.get("id"))})


def _find_list_id(client, name):
    for lst in _get_lists(client) or []:
        if lst.get("name") == name:
            return lst.get("id")
    return None


def _create_list(client, name):
    resp = client.post("/api/reading-lists", json={"name": name})
    assert resp.status_code in (200, 201)
    list_id = _find_list_id(client, name)
    assert list_id
    return list_id


def _first_article(client):
    resp = client.get("/api/articles?scope=all&limit=200")
    assert resp.status_code == 200
    articles = resp.get_json().get("articles") or []
    if not articles:
        pytest.skip("no articles available")
    first = articles[0]
    return first.get("id"), first.get("title")


def test_reader_js_list_hooks(client):
    resp = client.get("/static/js/app.js")
    assert resp.status_code == 200
    js = resp.get_data(as_text=True)
    for token in (
        "list-select",
        "list-new",
        "btn-add-list",
        "list-add-status",
        "loadListOptions",
        "bindListEditor",
        "reading-lists",
    ):
        assert token in js


def test_reader_page_serves_app_js(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "static/js/app.js" in html


def test_reader_add_to_existing_list(client):
    _clear(client)
    list_id = _create_list(client, "阅读器旧清单")
    article_id, title = _first_article(client)
    resp = client.post(
        f"/api/reading-lists/{list_id}/articles",
        json={"article_id": int(article_id)},
    )
    assert resp.status_code == 200
    member = resp.get_json()
    assert member["article_id"] == int(article_id)
    resp = client.get(f"/api/reading-lists/{list_id}/articles")
    assert resp.status_code == 200
    articles = resp.get_json()["articles"]
    assert title in [a["title"] for a in articles]


def test_reader_duplicate_add_no_duplicate_row(client):
    _clear(client)
    list_id = _create_list(client, "阅读器去重清单")
    article_id, title = _first_article(client)
    payload = {"article_id": int(article_id)}
    first = client.post(f"/api/reading-lists/{list_id}/articles", json=payload).get_json()
    second = client.post(f"/api/reading-lists/{list_id}/articles", json=payload).get_json()
    assert first["id"] == second["id"]
    resp = client.get(f"/api/reading-lists/{list_id}/articles")
    assert resp.status_code == 200
    articles = resp.get_json()["articles"]
    assert [a["article_id"] for a in articles].count(int(article_id)) == 1
    assert [a["title"] for a in articles].count(title) == 1


def test_reader_new_list_flow(client):
    _clear(client)
    resp = client.post("/api/reading-lists", json={"name": "阅读器新清单"})
    list_id = resp.get_json()["id"]
    article_id, title = _first_article(client)
    resp = client.post(
        f"/api/reading-lists/{list_id}/articles",
        json={"article_id": int(article_id)},
    )
    assert resp.status_code == 200
    resp = client.get("/reading-lists")
    html = resp.get_data(as_text=True)
    assert "阅读器新清单" in html
    assert title in html
