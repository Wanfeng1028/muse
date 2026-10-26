import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sqlite3

from feedflow.store import (
    create_feed,
    get_article,
    insert_article,
    list_archived,
    set_archived,
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


def test_store_archived_sets_time(tmp_db):
    ids = _seed3(tmp_db)
    set_archived(tmp_db, ids[0], 1)
    article = get_article(tmp_db, ids[0])
    assert article["is_archived"] == 1
    assert article["archived_at"]
    archived = list_archived(tmp_db)
    assert [row["article_id"] for row in archived] == [ids[0]]


def test_store_archived_unarchive_clears_time(tmp_db):
    ids = _seed3(tmp_db)
    set_archived(tmp_db, ids[0], 1)
    set_archived(tmp_db, ids[0], 0)
    article = get_article(tmp_db, ids[0])
    assert article["is_archived"] == 0
    assert article["archived_at"] is None
    assert list_archived(tmp_db) == []


def test_store_archived_only_archived(tmp_db):
    ids = _seed3(tmp_db)
    set_archived(tmp_db, ids[1], 1)
    archived = list_archived(tmp_db)
    assert [row["article_id"] for row in archived] == [ids[1]]


def test_store_archived_order_by_time(tmp_db):
    ids = _seed3(tmp_db)
    set_archived(tmp_db, ids[0], 1)
    set_archived(tmp_db, ids[1], 1)
    archived = list_archived(tmp_db)
    assert [row["article_id"] for row in archived] == [ids[1], ids[0]]


def test_store_archived_limit_clamped(tmp_db):
    ids = _seed3(tmp_db)
    for article_id in ids:
        set_archived(tmp_db, article_id, 1)
    assert len(list_archived(tmp_db, limit=500)) == 3
    assert len(list_archived(tmp_db, limit=0)) == 1


def test_store_archived_migration(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 12
        columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
        assert "is_archived" in columns
        assert "archived_at" in columns
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(articles)")}
        assert "idx_articles_archived_at" in indexes
    finally:
        conn.close()
