import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from feedflow.store import (
    create_feed,
    dequeue_article,
    insert_article,
    is_queued,
    list_later,
    move_later,
    queue_article,
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


def _ids(tmp_db):
    return [a["article_id"] for a in list_later(tmp_db)]


def test_store_queue_order_and_dup(tmp_db):
    ids = _seed3(tmp_db)
    assert queue_article(tmp_db, ids[0]) is True
    assert queue_article(tmp_db, ids[1]) is True
    assert queue_article(tmp_db, ids[2]) is True
    assert _ids(tmp_db) == ids
    assert queue_article(tmp_db, ids[0]) is False
    assert _ids(tmp_db) == ids


def test_store_queue_missing_false(tmp_db):
    _seed3(tmp_db)
    assert queue_article(tmp_db, 99999) is False
    assert _ids(tmp_db) == []


def test_store_is_queued(tmp_db):
    ids = _seed3(tmp_db)
    assert is_queued(tmp_db, ids[0]) is False
    queue_article(tmp_db, ids[0])
    assert is_queued(tmp_db, ids[0]) is True


def test_store_dequeue(tmp_db):
    ids = _seed3(tmp_db)
    for i in ids:
        queue_article(tmp_db, i)
    assert dequeue_article(tmp_db, ids[1]) is True
    assert dequeue_article(tmp_db, ids[1]) is False
    assert ids[1] not in _ids(tmp_db)
    assert _ids(tmp_db) == [ids[0], ids[2]]


def test_store_move(tmp_db):
    ids = _seed3(tmp_db)
    for i in ids:
        queue_article(tmp_db, i)
    assert move_later(tmp_db, ids[1], "up") is True
    assert _ids(tmp_db) == [ids[1], ids[0], ids[2]]
    assert move_later(tmp_db, ids[1], "up") is False
    assert _ids(tmp_db) == [ids[1], ids[0], ids[2]]
    assert move_later(tmp_db, ids[2], "down") is False
    assert _ids(tmp_db) == [ids[1], ids[0], ids[2]]


def test_store_move_bad_direction(tmp_db):
    ids = _seed3(tmp_db)
    queue_article(tmp_db, ids[0])
    with pytest.raises(ValueError):
        move_later(tmp_db, ids[0], "side")
