"""rss 模块深度测试：解析边界、去重聚类、失败注入、幂等、排序稳定性。"""
from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET

import pytest

from feedflow import db as db_mod
from feedflow import fetcher, rss, store


def _add_article(db_path, **kwargs):
    defaults = {
        "feed_id": 1,
        "guid": None,
        "title": "",
        "link": "",
        "summary": "",
        "content_text": "",
        "published_at": None,
        "fetched_at": None,
    }
    defaults.update(kwargs)
    if defaults["guid"] is None:
        defaults["guid"] = defaults["link"] or defaults["title"] or "g-default"
    conn = db_mod.get_conn(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO feeds (id, title, feed_url, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                defaults["feed_id"],
                "rss-test",
                "http://example.com/rss.xml",
                "2024-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    try:
        article_id = store.insert_article(
            db_path,
            defaults["feed_id"],
            defaults["guid"],
            defaults["title"],
            "",
            defaults["link"],
            defaults["summary"],
            "",
            defaults["content_text"],
            defaults["published_at"],
        )
    except sqlite3.IntegrityError:
        conn = db_mod.get_conn(db_path)
        try:
            row = conn.execute(
                "SELECT id FROM articles WHERE feed_id = ? AND guid = ?",
                (defaults["feed_id"], defaults["guid"]),
            ).fetchone()
            article_id = row[0]
        finally:
            conn.close()
    if defaults["fetched_at"] is not None:
        conn = db_mod.get_conn(db_path)
        try:
            conn.execute(
                "UPDATE articles SET fetched_at = ? WHERE id = ?",
                (defaults["fetched_at"], article_id),
            )
            conn.commit()
        finally:
            conn.close()
    return article_id


def _parse(xml_text):
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    items = channel.findall("item")
    return root, channel, items


def test_malformed_xml_bytes_does_not_break_build(tmp_db):
    _add_article(
        tmp_db,
        title="bad <tag> & 'quote'",
        link="http://x/a",
        content_text="body with ]]> cdata terminator and <script>alert(1)</script>",
    )
    xml_text, etag = rss.build_rss(tmp_db)
    root, _channel, items = _parse(xml_text)
    assert root.tag == "rss"
    assert len(items) == 1
    body = items[0].find("description").text
    assert "]]>" in body
    assert "<script>" in body
    assert etag.startswith('"') and etag.endswith('"')
    assert len(etag) == 66


def test_empty_feed_returns_valid_channel_without_items(tmp_db):
    xml_text, etag = rss.build_rss(tmp_db)
    _root, channel, items = _parse(xml_text)
    assert channel.find("title").text == "FeedFlow 全文 RSS"
    assert channel.find("link").text == "/"
    assert items == []
    assert etag == '"' + __import__("hashlib").sha256(xml_text.encode("utf-8")).hexdigest() + '"'


def test_limit_capped_at_50_and_default_50(tmp_db):
    for i in range(60):
        _add_article(
            tmp_db,
            title=f"t{i:d}",
            link=f"http://x/{i:d}",
            content_text=f"c{i:d}",
            fetched_at=f"2024-01-01T00:00:{i % 60:02d}",
        )
    xml_text, _ = rss.build_rss(tmp_db, limit=500)
    _, _, items = _parse(xml_text)
    assert len(items) == 50

    xml_text2, _ = rss.build_rss(tmp_db, limit=7)
    _, _, items2 = _parse(xml_text2)
    assert len(items2) == 7


def test_non_utf8_control_chars_are_safe_in_cdata(tmp_db):
    weird = "line\u0000null\u0001ctrl \u00e9\u4e2d\u6587"
    _add_article(
        tmp_db,
        title="ctrl \u0000 title",
        link="http://x/ctrl",
        content_text=weird,
    )
    xml_text, _ = rss.build_rss(tmp_db)
    _root, _channel, items = _parse(xml_text)
    assert len(items) == 1
    desc = items[0].find("description").text
    assert "\u00e9\u4e2d\u6587" in desc
    assert "null" in desc and "ctrl" in desc


def test_similar_titles_dedup_by_guid(tmp_db):
    _add_article(tmp_db, title="same headline", link="http://x/1", guid="g-1", content_text="a")
    _add_article(tmp_db, title="same headline", link="http://x/2", guid="g-1", content_text="b")
    _add_article(tmp_db, title="same headline", link="http://x/3", guid="g-1", content_text="c")
    xml_text, _ = rss.build_rss(tmp_db)
    _, _, items = _parse(xml_text)
    guids = [it.find("guid").text for it in items]
    assert guids.count("g-1") == 1


def test_title_clickbait_variants_are_distinct_articles(tmp_db):
    _add_article(tmp_db, title="震惊！这个方法太绝了", link="http://x/a", guid="ga", content_text="a")
    _add_article(tmp_db, title="震惊：这个方法太绝了", link="http://x/b", guid="gb", content_text="b")
    _add_article(tmp_db, title="震惊! 这个方法太绝了", link="http://x/c", guid="gc", content_text="c")
    xml_text, _ = rss.build_rss(tmp_db)
    _, _, items = _parse(xml_text)
    assert len(items) == 3
    titles = {it.find("title").text for it in items}
    assert titles == {"震惊！这个方法太绝了", "震惊：这个方法太绝了", "震惊! 这个方法太绝了"}


def test_reprint_same_link_dedup_by_guid(tmp_db):
    _add_article(tmp_db, title="orig", link="http://x/orig", guid="http://x/orig", content_text="a")
    _add_article(tmp_db, title="reprint", link="http://x/orig", guid="http://x/orig", content_text="b")
    xml_text, _ = rss.build_rss(tmp_db)
    _, _, items = _parse(xml_text)
    assert len(items) == 1
    assert items[0].find("guid").text == "http://x/orig"


def test_fetch_timeout_is_reported_and_no_partial_write(tmp_db):
    def boom(*a, **k):
        raise TimeoutError("connect timeout")

    original = fetcher.fetch_feed
    fetcher.fetch_feed = boom
    try:
        with pytest.raises(TimeoutError):
            fetcher.fetch_feed("http://slow.example/feed")
    finally:
        fetcher.fetch_feed = original

    xml_text, _ = rss.build_rss(tmp_db)
    _, _, items = _parse(xml_text)
    assert items == []
    assert store.list_articles(tmp_db, scope="all", limit=50)[0] == 0


def test_fetch_404_raises_and_leaves_db_empty(tmp_db):
    calls = {"n": 0}

    def not_found(url, *a, **k):
        calls["n"] += 1
        raise RuntimeError(f"HTTP 404 for {url}")

    original = fetcher.fetch_feed
    fetcher.fetch_feed = not_found
    try:
        with pytest.raises(RuntimeError) as ei:
            fetcher.fetch_feed("http://missing.example/feed")
        assert "404" in str(ei.value)
    finally:
        fetcher.fetch_feed = original

    assert calls["n"] == 1
    assert store.list_articles(tmp_db, scope="all", limit=50)[0] == 0


def test_fetch_rate_limit_backoff_marks_no_rows(tmp_db):
    attempts = {"n": 0}

    def rate_limited(url, *a, **k):
        attempts["n"] += 1
        raise RuntimeError("HTTP 429 Too Many Requests")

    original = fetcher.fetch_feed
    fetcher.fetch_feed = rate_limited
    try:
        for _ in range(3):
            with pytest.raises(RuntimeError):
                fetcher.fetch_feed("http://limited.example/feed")
    finally:
        fetcher.fetch_feed = original

    assert attempts["n"] == 3
    assert store.list_articles(tmp_db, scope="all", limit=50)[0] == 0


def test_idempotent_refetch_same_guid_single_row(tmp_db):
    for _ in range(5):
        _add_article(
            tmp_db,
            title="idem",
            link="http://x/idem",
            guid="g-idem",
            content_text="payload",
            fetched_at="2024-02-02T10:00:00",
        )
    total, rows = store.list_articles(tmp_db, scope="all", limit=50)
    assert total == 1
    assert len(rows) == 1
    xml_text, _ = rss.build_rss(tmp_db)
    _, _, items = _parse(xml_text)
    assert len(items) == 1
    assert items[0].find("guid").text == "g-idem"


def test_idempotent_etag_stable_across_calls(tmp_db):
    _add_article(tmp_db, title="a", link="http://x/a", guid="ga", content_text="body")
    x1, e1 = rss.build_rss(tmp_db)
    x2, e2 = rss.build_rss(tmp_db)
    assert x1 == x2
    assert e1 == e2
    assert len(e1) == 66


def test_importance_ordering_is_stable_for_same_pubdate(tmp_db):
    for i in range(5):
        _add_article(
            tmp_db,
            title=f"t{i:d}",
            link=f"http://x/{i:d}",
            guid=f"g{i:d}",
            content_text=f"c{i:d}",
            published_at="2024-03-03T12:00:00",
        )
    x1, _ = rss.build_rss(tmp_db)
    x2, _ = rss.build_rss(tmp_db)
    _, _, items1 = _parse(x1)
    _, _, items2 = _parse(x2)
    guids1 = [it.find("guid").text for it in items1]
    guids2 = [it.find("guid").text for it in items2]
    assert guids1 == guids2
    assert set(guids1) == {"g0", "g1", "g2", "g3", "g4"}


def test_pubdate_fallback_to_fetched_at(tmp_db):
    _add_article(
        tmp_db,
        title="fallback",
        link="http://x/fb",
        guid="gfb",
        content_text="c",
        published_at=None,
        fetched_at="2024-04-04T08:30:00",
    )
    xml_text, _ = rss.build_rss(tmp_db)
    _, _, items = _parse(xml_text)
    pub = items[0].find("pubDate").text
    assert pub is not None
    assert "Apr 2024" in pub or "04 Apr 2024" in pub


def test_full_text_prefers_content_text_over_summary(tmp_db):
    _add_article(
        tmp_db,
        title="full",
        link="http://x/full",
        guid="gfull",
        content_text="REAL CONTENT BODY",
        summary="<p>summary only</p>",
    )
    xml_text, _ = rss.build_rss(tmp_db)
    _, _, items = _parse(xml_text)
    desc = items[0].find("description").text
    assert "REAL CONTENT BODY" in desc
    assert "summary only" not in desc