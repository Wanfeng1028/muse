import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import sqlite3

from feedflow.store import (
    add_article_to_list,
    create_feed,
    create_reading_list,
    delete_reading_list,
    insert_article,
    list_reading_list_articles,
    list_reading_lists,
    remove_article_from_list,
)


def _seed3(tmp_db):
    feed_id = create_feed(tmp_db, "http://example.com/rss", None)
    ids = []
    for i in range(3):
        ids.append(insert_article(tmp_db, feed_id, f"guid-{i}", f"title-{i}", "author", f"http://example.com/{i}", "summary", "<p>html</p>", "text", None))
    return ids


def test_store_reading_list_normalizes(tmp_db):
    row = create_reading_list(tmp_db, "  周末   深读 ")
    assert row["name"] == "周末 深读"
    row2 = create_reading_list(tmp_db, "ABC 清单")
    assert row2["name"] == "ABC 清单"


def test_store_reading_list_duplicate_reuses(tmp_db):
    first = create_reading_list(tmp_db, "周末深读")
    second = create_reading_list(tmp_db, "周末深读")
    assert second["id"] == first["id"]
    assert len(list_reading_lists(tmp_db)) == 1


def test_store_reading_list_empty_raises(tmp_db):
    try:
        create_reading_list(tmp_db, "   ")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty reading list name")


def test_store_reading_list_order_newest_first(tmp_db):
    create_reading_list(tmp_db, "甲")
    create_reading_list(tmp_db, "乙")
    rows = list_reading_lists(tmp_db)
    assert [r["name"] for r in rows] == ["乙", "甲"]


def test_store_reading_list_limit_clamped(tmp_db):
    for name in ("甲", "乙", "丙"):
        create_reading_list(tmp_db, name)
    assert len(list_reading_lists(tmp_db, limit=500)) == 3
    assert len(list_reading_lists(tmp_db, limit=0)) == 1


def test_store_reading_lists_migration(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 14
        list_cols = {row[1] for row in conn.execute("PRAGMA table_info(reading_lists)")}
        assert {"id", "name", "created_at"} <= list_cols
        item_cols = {row[1] for row in conn.execute("PRAGMA table_info(reading_list_items)")}
        assert {"id", "list_id", "article_id", "added_at"} <= item_cols
        index_names = set()
        for table in ("reading_lists", "reading_list_items"):
            index_names |= {row[1] for row in conn.execute(f"PRAGMA index_list({table})")}
        assert {"idx_reading_lists_created", "idx_reading_list_items_list", "idx_reading_list_items_article"} <= index_names
    finally:
        conn.close()


def test_store_reading_list_add_and_list_members(tmp_db):
    ids = _seed3(tmp_db)
    lst = create_reading_list(tmp_db, "周末深读")
    add_article_to_list(tmp_db, lst["id"], ids[0])
    add_article_to_list(tmp_db, lst["id"], ids[1])
    members = list_reading_list_articles(tmp_db, lst["id"])
    assert [m["article_id"] for m in members] == [ids[1], ids[0]]
    rows = list_reading_lists(tmp_db)
    assert len(rows) == 1
    assert rows[0]["article_count"] == 2


def test_store_reading_list_add_duplicate_reuses(tmp_db):
    ids = _seed3(tmp_db)
    lst = create_reading_list(tmp_db, "周末深读")
    first = add_article_to_list(tmp_db, lst["id"], ids[0])
    second = add_article_to_list(tmp_db, lst["id"], ids[0])
    assert second["id"] == first["id"]
    assert len(list_reading_list_articles(tmp_db, lst["id"])) == 1


def test_store_reading_list_add_missing_returns_none(tmp_db):
    ids = _seed3(tmp_db)
    lst = create_reading_list(tmp_db, "周末深读")
    assert add_article_to_list(tmp_db, 999999, ids[0]) is None
    assert add_article_to_list(tmp_db, lst["id"], 999999) is None


def test_store_reading_list_remove_and_delete(tmp_db):
    ids = _seed3(tmp_db)
    lst = create_reading_list(tmp_db, "周末深读")
    add_article_to_list(tmp_db, lst["id"], ids[0])
    add_article_to_list(tmp_db, lst["id"], ids[1])
    assert remove_article_from_list(tmp_db, lst["id"], ids[0]) is True
    assert remove_article_from_list(tmp_db, lst["id"], ids[0]) is False
    assert delete_reading_list(tmp_db, lst["id"]) is True
    assert delete_reading_list(tmp_db, lst["id"]) is False
    assert list_reading_list_articles(tmp_db, lst["id"]) is None
