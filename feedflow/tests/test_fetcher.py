# tests/test_fetcher.py
from pathlib import Path

import pytest
import trafilatura

from feedflow import db as db_mod
from feedflow import fetcher, store


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    db_mod.init_db(str(db_path))
    return str(db_path)


FIXTURES = Path(__file__).parent / "fixtures"


def _make_feed(db_path, feed_url):
    conn = db_mod.get_conn(db_path)
    try:
        with db_mod.write_lock:
            cur = conn.execute(
                "INSERT INTO feeds (title, site_url, feed_url, description, "
                "interval_min, enabled, etag, modified, position, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("", "", feed_url, "", 0, 1, "", "", 0,
                 "2024-01-01T00:00:00+00:00"),
            )
            conn.commit()
            feed_id = cur.lastrowid
    finally:
        conn.close()
    return store.get_feed(db_path, feed_id)


def test_parse_feed_info(tmp_db):
    sample = str(FIXTURES / "sample.xml")
    info = fetcher.parse_feed_info(sample)
    assert info["title"] == "测试博客"


def test_fetch_feed_added_and_dedup(tmp_db):
    sample = str(FIXTURES / "sample.xml")
    feed = _make_feed(tmp_db, sample)

    result = fetcher.fetch_feed(tmp_db, feed, "FeedFlow-test")
    assert result["status"] == "ok"
    assert result["added"] == 3

    feed2 = store.get_feed(tmp_db, feed["id"])
    result2 = fetcher.fetch_feed(tmp_db, feed2, "FeedFlow-test")
    assert result2["added"] == 0

    conn = db_mod.get_conn(tmp_db)
    try:
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM articles WHERE feed_id=?", (feed["id"],)
        ).fetchone()["c"]
    finally:
        conn.close()
    assert n == 3


def test_fetch_feed_error(tmp_db, tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("this is not xml at all <<<>>>", encoding="utf-8")
    feed = _make_feed(tmp_db, str(bad))
    result = fetcher.fetch_feed(tmp_db, feed, "FeedFlow-test")
    assert result["status"] == "error"
    assert result["added"] == 0
    assert result["error"]


def test_extract_text_chinese():
    html = (FIXTURES / "article.html").read_text(encoding="utf-8")
    text = trafilatura.extract(html, favor_recall=True)
    assert text is not None
    assert "正文" in text or "内容" in text
    assert "导航" not in text
    assert "菜单" not in text


def test_html_to_text():
    html = "<p>Hello <b>世界</b>&amp; more</p>"
    out = fetcher._html_to_text(html)
    assert "Hello" in out
    assert "世界" in out
    assert "&" in out
    assert "<" not in out
    assert ">" not in out

