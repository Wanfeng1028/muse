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


def _first_article(client):
    resp = client.get("/api/articles?scope=all")
    data = resp.get_json()
    assert data["total"] > 0
    return data["articles"][0]

def test_note_empty_get(client):
    r = client.get(f"/api/articles/{_first_article_id(client)}/note")
    assert r.status_code == 200
    data = r.get_json()
    assert data["body"] == ""
    assert data["updated_at"] is None

def test_note_save_and_get(client):
    aid = _first_article_id(client)
    r = client.put(f"/api/articles/{aid}/note", json={"body": "  读后感一则  "})
    assert r.status_code == 200
    assert r.get_json()["body"] == "读后感一则"
    r = client.get(f"/api/articles/{aid}/note")
    assert r.status_code == 200
    data = r.get_json()
    assert data["body"] == "读后感一则"
    assert data["updated_at"] is not None

def test_note_save_empty_400(client):
    r = client.put(f"/api/articles/{_first_article_id(client)}/note", json={"body": "   "})
    assert r.status_code == 400

def test_note_save_missing_404(client):
    r = client.put("/api/articles/999999/note", json={"body": "x"})
    assert r.status_code == 404

def test_note_get_missing_404(client):
    r = client.get("/api/articles/999999/note")
    assert r.status_code == 404

def test_note_update_overwrites(client):
    aid = _first_article_id(client)
    client.put(f"/api/articles/{aid}/note", json={"body": "第一版"})
    client.put(f"/api/articles/{aid}/note", json={"body": "第二版"})
    r = client.get(f"/api/articles/{aid}/note").get_json()
    assert r["body"] == "第二版"

def test_note_delete(client):
    aid = _first_article_id(client)
    client.put(f"/api/articles/{aid}/note", json={"body": "待删"})
    assert client.delete(f"/api/articles/{aid}/note").get_json()["removed"] is True
    assert client.delete(f"/api/articles/{aid}/note").get_json()["removed"] is False
    r = client.get(f"/api/articles/{aid}/note").get_json()
    assert r["body"] == ""

def test_note_delete_missing_404(client):
    assert client.delete("/api/articles/999999/note").status_code == 404

def test_notes_list(client):
    aid = _first_article_id(client)
    r = client.put(f"/api/articles/{aid}/note", json={"body": "列表检查"})
    assert r.status_code == 200
    data = client.get("/api/notes").get_json()
    item = next(n for n in data["notes"] if n["article_id"] == aid)
    assert item["title"] and item["feed_title"]

def test_notes_page_empty(client):
    resp = client.get("/notes")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "我的笔记" in html
    assert "还没有笔记" in html

def test_notes_page_shows_note(client):
    article = _first_article(client)
    resp = client.put(f"/api/articles/{article['id']}/note", json={"body": "页面可见性检查"})
    assert resp.status_code == 200
    html = client.get("/notes").get_data(as_text=True)
    assert "页面可见性检查" in html
    assert article["title"] in html

def test_notes_page_escapes_html(client):
    article = _first_article(client)
    resp = client.put(f"/api/articles/{article['id']}/note", json={"body": "<b>加粗</b>"})
    assert resp.status_code == 200
    html = client.get("/notes").get_data(as_text=True)
    assert "<b>加粗</b>" not in html
    assert "&lt;b&gt;" in html

def test_reader_js_has_note_editor(client):
    resp = client.get("/static/js/app.js")
    assert resp.status_code == 200
    js = resp.get_data(as_text=True)
    for token in ("article-note", "loadArticleNote", "bindNoteEditor", "btn-save-note", "btn-delete-note"):
        assert token in js

def test_reader_page_links_notes(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "/notes" in resp.get_data(as_text=True)
