import sqlite3

import pytest

from feedflow import store


def _seed_feed(db_path, title="Feed One", site_url="https://a.example.com",
               feed_url="https://a.example.com/rss"):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO feeds (title, site_url, feed_url, created_at) "
            "VALUES (?, ?, ?, ?)",
            (title, site_url, feed_url, "2024-01-01T00:00:00"),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _seed_article(db_path, feed_id, guid, title="T", link="https://a.example.com/1",
                  summary="", content_text="", published_at="2024-01-01T00:00:00",
                  fetched_at="2024-01-01T00:00:00", is_read=0, is_starred=0):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO articles (feed_id, guid, title, link, summary, content_text, "
            "published_at, fetched_at, is_read, is_starred) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (feed_id, guid, title, link, summary, content_text,
             published_at, fetched_at, is_read, is_starred),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


@pytest.fixture()
def seeded(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute("DELETE FROM articles")
        conn.execute("DELETE FROM feeds")
        conn.commit()
    finally:
        conn.close()
    fid = _seed_feed(tmp_db)
    for i in range(5):
        _seed_article(
            tmp_db, fid, guid=f"g{i}", title=f"Article {i}",
            link=f"https://a.example.com/{i}",
            content_text=f"body {i}",
            published_at=f"2024-01-0{i + 1}T00:00:00",
        )
    return tmp_db


def test_pagination_limit2_offset0(client, seeded):
    resp = client.get("/api/articles?scope=all&limit=2&offset=0")
    data = resp.get_json()
    assert data["total"] == 5
    assert len(data["articles"]) == 2


def test_pagination_offset4_returns_one(client, seeded):
    resp = client.get("/api/articles?scope=all&limit=10&offset=4")
    data = resp.get_json()
    assert data["total"] == 5
    assert len(data["articles"]) == 1


def test_pagination_offset_beyond_total(client, seeded):
    resp = client.get("/api/articles?scope=all&limit=10&offset=999")
    data = resp.get_json()
    assert data["total"] == 5
    assert data["articles"] == []


def test_pagination_limit_zero_returns_400(client, seeded):
    resp = client.get("/api/articles?scope=all&limit=0&offset=0")
    assert resp.status_code == 400
    assert "limit 参数非法" in resp.get_json()["error"]


def test_pagination_limit_over_200_clamped(client, seeded):
    resp = client.get("/api/articles?scope=all&limit=999&offset=0")
    data = resp.get_json()
    assert data["total"] == 5
    assert len(data["articles"]) == 5


def test_pagination_negative_offset_returns_400(client, seeded):
    resp = client.get("/api/articles?scope=all&limit=2&offset=-5")
    assert resp.status_code == 400
    assert "offset 参数非法" in resp.get_json()["error"]


def test_invalid_scope_falls_back_to_unread(client, tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute("DELETE FROM articles")
        conn.execute("DELETE FROM feeds")
        conn.commit()
    finally:
        conn.close()
    fid = _seed_feed(tmp_db)
    _seed_article(tmp_db, fid, guid="r1", title="Read One", is_read=1)
    _seed_article(tmp_db, fid, guid="u1", title="Unread One", is_read=0)

    resp = client.get("/api/articles?scope=illegal")
    data = resp.get_json()
    assert data["total"] == 1
    titles = [a["title"] for a in data["articles"]]
    assert titles == ["Unread One"]


def test_scope_unread_all_starred(client, tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute("DELETE FROM articles")
        conn.execute("DELETE FROM feeds")
        conn.commit()
    finally:
        conn.close()
    fid = _seed_feed(tmp_db)
    _seed_article(tmp_db, fid, guid="r1", title="Read One", is_read=1)
    _seed_article(tmp_db, fid, guid="u1", title="Unread One", is_read=0)
    _seed_article(tmp_db, fid, guid="s1", title="Star One", is_read=1, is_starred=1)

    unread = client.get("/api/articles?scope=unread").get_json()
    assert unread["total"] == 1
    assert unread["articles"][0]["title"] == "Unread One"

    all_resp = client.get("/api/articles?scope=all").get_json()
    assert all_resp["total"] == 3

    starred = client.get("/api/articles?scope=starred").get_json()
    assert starred["total"] == 1
    assert starred["articles"][0]["title"] == "Star One"


def test_feed_id_filter(client, tmp_db):
    f1 = _seed_feed(tmp_db, title="Feed A", feed_url="https://a.example.com/rss")
    f2 = _seed_feed(tmp_db, title="Feed B", site_url="https://b.example.com",
                    feed_url="https://b.example.com/rss")
    _seed_article(tmp_db, f1, guid="a1", title="From A")
    _seed_article(tmp_db, f2, guid="b1", title="From B")

    resp = client.get(f"/api/articles?scope=all&feed_id={f1}")
    data = resp.get_json()
    assert data["total"] == 1
    assert data["articles"][0]["title"] == "From A"
    assert data["articles"][0]["feed_id"] == f1


def test_search_special_or_does_not_crash(client, tmp_db):
    fid = _seed_feed(tmp_db)
    _seed_article(tmp_db, fid, guid="g1", title="Hello", content_text="alpha beta")
    resp = client.get("/search?q=%22OR%22")
    assert resp.status_code == 200


def test_search_colon_query_ok(client, tmp_db):
    fid = _seed_feed(tmp_db)
    _seed_article(tmp_db, fid, guid="g1", title="Hello", content_text="foo:bar baz")
    resp = client.get("/search?q=a%3Ab")
    assert resp.status_code == 200


def test_search_script_tag_escaped(client, tmp_db):
    fid = _seed_feed(tmp_db)
    _seed_article(tmp_db, fid, guid="g1", title="x",
                  content_text="<script>alert(1)</script> payload")
    resp = client.get("/search?q=%3Cscript%3Ealert%281%29%3C%2Fscript%3E")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body


def test_search_short_query_uses_like(client, tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute("DELETE FROM articles")
        conn.execute("DELETE FROM feeds")
        conn.commit()
    finally:
        conn.close()
    fid = _seed_feed(tmp_db)
    _seed_article(tmp_db, fid, guid="g1", title="ab testing guide",
                  content_text="a short note about ab")
    resp = client.get("/search?q=ab")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<mark>ab</mark>" in body


def test_search_chinese_highlight(client, tmp_db):
    fid = _seed_feed(tmp_db)
    _seed_article(tmp_db, fid, guid="g1", title="中文标题",
                  content_text="这是一段包含中文关键词的内容")
    resp = client.get("/search?q=中文关键词")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<mark>中文关键词</mark>" in body


def test_search_empty_q_no_mark(client, tmp_db):
    fid = _seed_feed(tmp_db)
    _seed_article(tmp_db, fid, guid="g1", title="Something",
                  content_text="something body")
    resp = client.get("/search")
    assert resp.status_code == 200
    assert "<mark>" not in resp.get_data(as_text=True)

    resp2 = client.get("/search?q=%20%20%20")
    assert resp2.status_code == 200
    assert "<mark>" not in resp2.get_data(as_text=True)


def test_search_title_only_hit_when_body_empty(client, tmp_db):
    fid = _seed_feed(tmp_db)
    _seed_article(tmp_db, fid, guid="g1", title="UniqueTitleWord",
                  summary="", content_text="")
    resp = client.get("/search?q=UniqueTitleWord")
    assert resp.status_code == 200


def test_search_articles_empty_q_returns_empty(tmp_db):
    fid = _seed_feed(tmp_db)
    _seed_article(tmp_db, fid, guid="g1", title="Hello", content_text="world")
    assert store.search_articles(tmp_db, "") == []
    assert store.search_articles(tmp_db, "   ") == []


def test_search_articles_only_quotes_returns_empty(tmp_db):
    fid = _seed_feed(tmp_db)
    _seed_article(tmp_db, fid, guid="g1", title="Hello", content_text="world")
    assert store.search_articles(tmp_db, '"') == []