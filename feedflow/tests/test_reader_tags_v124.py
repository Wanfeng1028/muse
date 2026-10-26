import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

def test_v119_layer_referenced_after_v118_and_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    pos_v118 = html.find("design-v118.css")
    pos_v119 = html.find("design-v119.css")
    assert pos_v118 != -1
    assert pos_v119 != -1
    assert pos_v118 < pos_v119
    assert client.get("/static/css/design-v118.css").status_code == 200
    assert client.get("/static/css/design-v119.css").status_code == 200


def test_v119_tag_selectors_no_important_no_gradient(client):
    css_path = os.path.join(ROOT, "feedflow", "static", "css", "design-v119.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()
    for selector in [
        ".article-tags",
        ".tag-chip",
        ".tag-chip-x",
        ".tag-empty",
        ".tag-editor",
        "#clear-tag-filter",
    ]:
        assert selector in css
    assert "!important" not in css
    assert "gradient" not in css.lower()


def test_reader_js_tag_hooks(client):
    resp = client.get("/static/js/app.js")
    assert resp.status_code == 200
    js = resp.get_data(as_text=True)
    for token in [
        "article-tags",
        "loadArticleTags",
        "setTagFilter",
        "clearTagFilter",
        "tag-select",
        "btn-add-tag",
        "tag_id",
    ]:
        assert token in js


def test_reader_page_has_clear_tag_filter_button(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="clear-tag-filter"' in html


def test_tags_assign_form_has_empty_option(client):
    resp = client.get("/tags")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '<option value="">选已有标签</option>' in html


def test_tags_page_article_time_formatted(client):
    from datetime import datetime

    listing = client.get("/api/articles?scope=all")
    assert listing.status_code == 200
    articles = listing.get_json()["articles"]
    target = next((a for a in articles if a.get("published_at")), None)
    assert target is not None, "scope=all 中没有带 published_at 的文章"

    tag_resp = client.post("/api/tags", json={"name": "时间格式化测试"})
    tag_id = tag_resp.get_json()["id"]
    assert isinstance(tag_id, int)

    assign_resp = client.post(
        f"/api/articles/{target['id']}/tags", json={"tag_id": tag_id}
    )
    assert tag_id is not None and assign_resp is not None

    page = client.get(f"/tags?tag_id={tag_id}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    expected = datetime.fromisoformat(target["published_at"]).strftime("%Y-%m-%d %H:%M")
    assert expected in html
    assert target["published_at"] not in html


def test_mark_read_by_tag_only(client):
    listing = client.get("/api/articles?scope=all")
    assert listing.status_code == 200
    articles = listing.get_json()["articles"]
    assert len(articles) >= 2, "至少需要两篇文章"
    article_a, article_b = articles[0], articles[1]
    assert article_a["id"] != article_b["id"]

    tag_resp = client.post("/api/tags", json={"name": "只标A的标签"})
    tag_id = tag_resp.get_json()["id"]

    client.post(f"/api/articles/{article_a['id']}/tags", json={"tag_id": tag_id})

    b_read_before = article_b["is_read"]

    mark_resp = client.post(
        "/api/articles/mark_read",
        json={"scope": "all", "tag_id": tag_id},
    )
    # 既有契约：store.mark_all_read 无返回值，API 的 updated 恒为 null（见 test_api_deep3_markread.py）
    assert mark_resp.get_json()["updated"] is None

    a_after = client.get(f"/api/articles/{article_a['id']}")
    b_after = client.get(f"/api/articles/{article_b['id']}")
    assert a_after.status_code == 200
    assert b_after.status_code == 200
    assert a_after.get_json()["is_read"] == 1
    assert b_after.get_json()["is_read"] == b_read_before


def test_mark_read_bad_tag_id_returns_400(client):
    resp = client.post(
        "/api/articles/mark_read",
        json={"scope": "all", "tag_id": "abc"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "tag_id 非法"
