import pytest
from datetime import UTC, datetime
from feedflow.db import get_conn
from feedflow.store import insert_article


def _insert_feed(
    db_path, name="示例源", feed_url="https://example.com/rss", site_url="https://example.com"
):
    conn = get_conn(db_path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(feeds)").fetchall()]
        fill = {}
        for c in cols:
            if c == "id":
                continue
            if c == "name":
                fill[c] = name
            elif c == "feed_url":
                fill[c] = feed_url
            elif c == "site_url":
                fill[c] = site_url
            else:
                fill[c] = ""
        col_names = list(fill.keys())
        placeholders = ",".join("?" for _ in col_names)
        sql = f"INSERT INTO feeds ({','.join(col_names)}) VALUES ({placeholders})"
        cur = conn.execute(sql, [fill[c] for c in col_names])
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


_guid_seq = [0]

def _iso(dt):
    return dt.replace(microsecond=0).isoformat()

def _base_time():
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

def _insert(tmp_db, feed_id, title, content_text="", summary=""):
    # 适配器：把模型写的 (db, feed_id, title, ...) 调用转接到真实签名
    # insert_article(db_path, feed_id, guid, title, author, link, summary, content_html, content_text, published_at)
    _guid_seq[0] += 1
    guid = "g%d" % _guid_seq[0]
    insert_article(
        tmp_db,
        feed_id,
        guid,
        title,
        "",
        "https://example.com/a/" + guid,
        summary,
        "",
        content_text,
        _iso(_base_time()),
    )


def test_empty_q_200(client):
    resp = client.get("/search")
    assert resp.status_code == 200
    resp = client.get("/search?q=%20%20")
    assert resp.status_code == 200


def test_q_no_match_200(client):
    resp = client.get("/search?q=不存在的词xyz")
    assert resp.status_code == 200


def test_q_with_match_shows_title(client, tmp_db):
    feed_id = _insert_feed(tmp_db)
    _insert(tmp_db, feed_id, "苹果发布会")
    resp = client.get("/search?q=苹果")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "苹果发布会" in html


def test_snippet_mark_present(client, tmp_db):
    feed_id = _insert_feed(tmp_db)
    _insert(tmp_db, feed_id, "AI Article", content_text="这是一篇关于人工智能的文章")
    resp = client.get("/search?q=人工智能")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "<mark>" in html


def test_xss_escaped(client, tmp_db):
    feed_id = _insert_feed(tmp_db)
    _insert(tmp_db, feed_id, "<script>alert(1)</script>")
    resp = client.get("/search?q=script")
    assert resp.status_code == 200
    assert b"<script>alert(1)</script>" not in resp.get_data()


def test_q_echoed(client):
    resp = client.get("/search?q=hello")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "hello" in html


def test_special_chars_200(client):
    resp = client.get("/search?q=%22%28%29%5E")
    assert resp.status_code == 200


def test_long_q_200(client):
    q = "a" * 500
    resp = client.get(f"/search?q={q}")
    assert resp.status_code == 200
