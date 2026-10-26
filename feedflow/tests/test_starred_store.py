import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sqlite3

from feedflow.store import (
    create_feed,
    get_article,
    insert_article,
    list_starred,
    set_starred,
)


def _seed3(tmp_db):
    feed_id = create_feed(tmp_db, "http://example.com/rss", None)
    ids = []
    for i in range(3):
        ids.append(
            insert_article(
                tmp_db, feed_id, f"guid-{i}", f"title-{i}", "author",
                f"http://example.com/{i}", "summary", "<p>html</p>", "text", None,
            )
        )
    return ids


def test_store_starred_sets_time(tmp_db):
    ids = _seed3(tmp_db)
    set_starred(tmp_db, ids[0], 1)
    article = get_article(tmp_db, ids[0])
    assert article["is_starred"] == 1
    assert article["starred_at"]
    starred = list_starred(tmp_db)
    assert [row["article_id"] for row in starred] == [ids[0]]


def test_store_starred_unstar_clears_time(tmp_db):
    ids = _seed3(tmp_db)
    set_starred(tmp_db, ids[0], 1)
    set_starred(tmp_db, ids[0], 0)
    article = get_article(tmp_db, ids[0])
    assert article["is_starred"] == 0
    assert article["starred_at"] is None
    assert list_starred(tmp_db) == []


def test_store_starred_only_starred(tmp_db):
    ids = _seed3(tmp_db)
    set_starred(tmp_db, ids[1], 1)
    starred = list_starred(tmp_db)
    assert [row["article_id"] for row in starred] == [ids[1]]


def test_store_starred_order_by_starred_at(tmp_db):
    ids = _seed3(tmp_db)
    set_starred(tmp_db, ids[0], 1)
    set_starred(tmp_db, ids[1], 1)
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            "UPDATE articles SET starred_at = ? WHERE id = ?",
            ("2026-10-27T10:00:00+00:00", ids[0]),
        )
        conn.execute(
            "UPDATE articles SET starred_at = ? WHERE id = ?",
            ("2026-10-27T09:00:00+00:00", ids[1]),
        )
        conn.commit()
    finally:
        conn.close()
    starred = list_starred(tmp_db)
    assert [row["article_id"] for row in starred] == [ids[0], ids[1]]


def test_store_starred_limit_clamp(tmp_db):
    ids = _seed3(tmp_db)
    for article_id in ids:
        set_starred(tmp_db, article_id, 1)
    assert len(list_starred(tmp_db, limit=1)) == 1
    assert len(list_starred(tmp_db, limit=999)) == 3


def test_store_starred_migration(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 11
        columns = [row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()]
        assert "starred_at" in columns
        indexes = [row[1] for row in conn.execute("PRAGMA index_list(articles)").fetchall()]
        assert "idx_articles_starred_at" in indexes
    finally:
        conn.close()
