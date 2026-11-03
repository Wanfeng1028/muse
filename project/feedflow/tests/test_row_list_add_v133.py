import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def _get_lists(client):
    resp = client.get("/api/reading-lists")
    return resp.get_json().get("reading_lists")


def _find_list_id(client, name):
    lists = _get_lists(client) or []
    for lst in lists:
        if lst.get("name") == name:
            return lst.get("id")
    return None


def _clear(client):
    lists = _get_lists(client) or []
    for lst in lists:
        client.post("/reading-lists/delete", data={"list_id": str(lst.get("id"))})


def _create_list(client, name):
    client.post("/api/reading-lists", json={"name": name})
    return _find_list_id(client, name)


def _first_article(client):
    resp = client.get("/api/articles?scope=all&limit=200")
    data = resp.get_json() or {}
    articles = data.get("articles", [])
    if not articles:
        pytest.skip("No articles available")
    return articles[0]


def test_row_list_js_hooks(client):
    resp = client.get("/static/js/app.js")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    tokens = [
        "row-list-btn",
        "row-list-picker",
        "toggleRowListPicker",
        "row-list-select",
        "row-list-new",
        "row-list-confirm",
        "row-list-status",
        "reading-lists",
        "data-row-list",
        "stopPropagation",
    ]
    for token in tokens:
        assert token in text, f"Missing token in app.js: {token}"


def test_row_list_add_to_existing_list(client):
    _clear(client)
    list_id = _create_list(client, "行内旧清单")
    assert list_id is not None
    article = _first_article(client)
    article_id = article["id"]
    resp = client.post(f"/api/reading-lists/{list_id}/articles", json={"article_id": article_id})
    assert resp.status_code == 200
    data = resp.get_json()
    if isinstance(data, dict):
        assert data.get("article_id") == article_id, f"Expected article_id in {data}"
    elif isinstance(data, list):
        assert any(m.get("article_id") == article_id for m in data if isinstance(m, dict)), \
            f"Expected article_id in list response {data}"
    resp2 = client.get(f"/api/reading-lists/{list_id}/articles")
    assert resp2.status_code == 200


def test_row_list_add_twice_idempotent(client):
    _clear(client)
    list_id = _create_list(client, "行内重复清单")
    assert list_id is not None
    article = _first_article(client)
    article_id = article["id"]
    resp1 = client.post(f"/api/reading-lists/{list_id}/articles", json={"article_id": article_id})
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    resp2 = client.post(f"/api/reading-lists/{list_id}/articles", json={"article_id": article_id})
    assert resp2.status_code == 200
    data2 = resp2.get_json()

    def _extract_member_row_id(data):
        if isinstance(data, dict):
            if "id" in data:
                return data["id"]
            articles = data.get("articles", [])
            if articles and isinstance(articles, list):
                return articles[0].get("id")
        elif isinstance(data, list) and data:
            return data[0].get("id")
        return None

    row_id1 = _extract_member_row_id(data1)
    row_id2 = _extract_member_row_id(data2)
    assert row_id1 is not None, f"Could not extract member row id from first response: {data1}"
    assert row_id2 is not None, f"Could not extract member row id from second response: {data2}"
    assert row_id1 == row_id2, f"Member row id changed on second add: {row_id1} != {row_id2}"


def test_row_list_create_then_add(client):
    _clear(client)
    resp = client.post("/api/reading-lists", json={"name": "行内新清单"})
    assert resp.status_code in (200, 201)
    list_id = _find_list_id(client, "行内新清单")
    assert list_id is not None
    article = _first_article(client)
    article_id = article["id"]
    resp2 = client.post(f"/api/reading-lists/{list_id}/articles", json={"article_id": article_id})
    assert resp2.status_code == 200
    resp3 = client.get(f"/api/reading-lists/{list_id}/articles")
    assert resp3.status_code == 200
    data = resp3.get_json()
    if isinstance(data, dict):
        members = data.get("articles", [])
    elif isinstance(data, list):
        members = data
    else:
        members = []
    member_ids = [m.get("article_id") for m in members if isinstance(m, dict)]
    assert article_id in member_ids, f"Article {article_id} not found in members {member_ids}"