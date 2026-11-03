"""Tests for feedflow full-text search (store.search_articles)."""


import pytest

from feedflow import db as db_module
from feedflow import store


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "feedflow_test.db")
    db_module.init_db(db_path)
    return db_path


def _insert_feed(db_path, feed_url, title="测试源"):
    conn = db_module.get_conn(db_path)
    try:
        with db_module.write_lock:
            cur = conn.execute(
                "INSERT INTO feeds (title, site_url, feed_url, description, interval_min,"
                " enabled, last_fetched_at, last_status, last_error, etag, modified,"
                " position, created_at)"
                " VALUES (?, '', ?, '', 0, 1, NULL, NULL, '', '', '', 0, ?)",
                (title, feed_url, "2024-01-01T00:00:00+00:00"),
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def test_search_chinese_article(tmp_db):
    feed_id = _insert_feed(tmp_db, "https://example.com/feed.xml")

    store.insert_article(
        tmp_db,
        feed_id,
        "guid-zh-1",
        "人工智能的进展",
        "作者甲",
        "https://example.com/a1",
        "关于人工智能的摘要",
        "<p>人工智能正在改变世界</p>",
        "人工智能正在改变世界，深度学习推动了人工智能的发展。",
        "2024-05-01T10:00:00+00:00",
    )
    store.insert_article(
        tmp_db,
        feed_id,
        "guid-en-1",
        "Machine Learning Basics",
        "Author B",
        "https://example.com/a2",
        "An intro to machine learning",
        "<p>Machine learning is fun</p>",
        "Machine learning is a field of study in computer science.",
        "2024-05-02T10:00:00+00:00",
    )

    results = store.search_articles(tmp_db, "人工智能")
    assert len(results) == 1
    assert results[0]["title"] == "人工智能的进展"


def test_search_english_article(tmp_db):
    feed_id = _insert_feed(tmp_db, "https://example.com/feed.xml")

    store.insert_article(
        tmp_db,
        feed_id,
        "guid-zh-1",
        "人工智能的进展",
        "作者甲",
        "https://example.com/a1",
        "关于人工智能的摘要",
        "<p>人工智能正在改变世界</p>",
        "人工智能正在改变世界，深度学习推动了人工智能的发展。",
        "2024-05-01T10:00:00+00:00",
    )
    store.insert_article(
        tmp_db,
        feed_id,
        "guid-en-1",
        "Machine Learning Basics",
        "Author B",
        "https://example.com/a2",
        "An intro to machine learning",
        "<p>Machine learning is fun</p>",
        "Machine learning is a field of study in computer science.",
        "2024-05-02T10:00:00+00:00",
    )

    results = store.search_articles(tmp_db, "learning")
    assert len(results) == 1
    assert results[0]["title"] == "Machine Learning Basics"


def test_search_no_match(tmp_db):
    feed_id = _insert_feed(tmp_db, "https://example.com/feed.xml")

    store.insert_article(
        tmp_db,
        feed_id,
        "guid-zh-1",
        "人工智能的进展",
        "作者甲",
        "https://example.com/a1",
        "关于人工智能的摘要",
        "<p>人工智能正在改变世界</p>",
        "人工智能正在改变世界，深度学习推动了人工智能的发展。",
        "2024-05-01T10:00:00+00:00",
    )

    results = store.search_articles(tmp_db, "不存在的词xyz")
    assert results == []


def test_search_empty_query(tmp_db):
    feed_id = _insert_feed(tmp_db, "https://example.com/feed.xml")

    store.insert_article(
        tmp_db,
        feed_id,
        "guid-zh-1",
        "人工智能的进展",
        "作者甲",
        "https://example.com/a1",
        "关于人工智能的摘要",
        "<p>人工智能正在改变世界</p>",
        "人工智能正在改变世界，深度学习推动了人工智能的发展。",
        "2024-05-01T10:00:00+00:00",
    )

    assert store.search_articles(tmp_db, "") == []
    assert store.search_articles(tmp_db, "   ") == []
