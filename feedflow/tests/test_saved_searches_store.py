import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sqlite3

from feedflow.store import list_saved_searches, save_search


def test_store_saved_search_normalizes(tmp_db):
    row = save_search(tmp_db, "  AI   新闻 ")
    assert row["query"] == "AI 新闻"
    assert isinstance(row["id"], int)


def test_store_saved_search_duplicate_reuses(tmp_db):
    first = save_search(tmp_db, "  机器  学习 ")
    second = save_search(tmp_db, "机器 学习")
    assert second["id"] == first["id"]
    rows = list_saved_searches(tmp_db)
    assert len(rows) == 1
    assert rows[0]["query"] == "机器 学习"


def test_store_saved_search_empty_raises(tmp_db):
    try:
        save_search(tmp_db, "   ")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for whitespace-only query")


def test_store_saved_search_order_newest_first(tmp_db):
    save_search(tmp_db, "甲")
    save_search(tmp_db, "乙")
    rows = list_saved_searches(tmp_db)
    assert [r["query"] for r in rows] == ["乙", "甲"]


def test_store_saved_search_limit_clamped(tmp_db):
    for query in ("一", "二", "三"):
        save_search(tmp_db, query)
    assert len(list_saved_searches(tmp_db, limit=500)) == 3
    assert len(list_saved_searches(tmp_db, limit=0)) == 1


def test_store_saved_searches_migration(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 14
        columns = {row[1] for row in conn.execute("PRAGMA table_info(saved_searches)")}
        assert {"id", "query", "created_at"} <= columns
        indexes = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        assert "idx_saved_searches_created" in indexes
    finally:
        conn.close()
