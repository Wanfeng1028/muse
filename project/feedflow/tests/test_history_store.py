import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from feedflow.store import (
    clear_history,
    create_feed,
    insert_article,
    list_history,
    record_history,
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


def test_store_history_record_new(tmp_db):
    ids = _seed3(tmp_db)
    row = record_history(tmp_db, ids[0])
    assert row is not None
    assert row["article_id"] == ids[0]
    assert row["read_count"] == 1
    assert row["last_read_at"]
    history = list_history(tmp_db)
    assert [item["article_id"] for item in history] == [ids[0]]


def test_store_history_record_again_increments(tmp_db):
    ids = _seed3(tmp_db)
    record_history(tmp_db, ids[0])
    again = record_history(tmp_db, ids[0])
    assert again is not None
    assert again["read_count"] == 2
    assert len(list_history(tmp_db)) == 1


def test_store_history_record_missing(tmp_db):
    _seed3(tmp_db)
    assert record_history(tmp_db, 99999) is None
    assert list_history(tmp_db) == []


def test_store_history_order_by_recent(tmp_db):
    ids = _seed3(tmp_db)
    record_history(tmp_db, ids[0])
    record_history(tmp_db, ids[1])
    record_history(tmp_db, ids[0])
    rows = list_history(tmp_db)
    assert [row["article_id"] for row in rows] == [ids[0], ids[1]]


def test_store_history_limit_clamp(tmp_db):
    ids = _seed3(tmp_db)
    for aid in ids:
        record_history(tmp_db, aid)
    assert len(list_history(tmp_db, limit=1)) == 1
    assert len(list_history(tmp_db, limit=999)) == 3


def test_store_history_clear(tmp_db):
    ids = _seed3(tmp_db)
    record_history(tmp_db, ids[0])
    record_history(tmp_db, ids[1])
    assert clear_history(tmp_db) == 2
    assert list_history(tmp_db) == []
    assert clear_history(tmp_db) == 0
