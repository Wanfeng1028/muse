import sqlite3
from datetime import UTC, datetime

from feedflow import store
from feedflow.ranking import get_digest_clusters


def _insert_raw(db_path, feed_id, guid, title, published_at, fetched_at, cluster_id, is_read):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO articles
                (feed_id, guid, title, author, link, summary, content_html,
                 content_text, published_at, fetched_at, is_read, is_starred, cluster_id)
            VALUES (?, ?, ?, '', '', '', '', '', ?, ?, ?, 0, ?)
            """,
            (feed_id, guid, title, published_at, fetched_at, is_read, cluster_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_latest_at_picks_newest_published(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/latest-newest.xml")
    now_iso = datetime.now(UTC).isoformat()
    _insert_raw(
        tmp_db,
        feed_id,
        "guid-a",
        "A",
        "2026-10-19T10:00:00+00:00",
        now_iso,
        9001,
        0,
    )
    _insert_raw(
        tmp_db,
        feed_id,
        "guid-b",
        "B",
        "2026-10-20T10:00:00+00:00",
        now_iso,
        9001,
        0,
    )
    groups = get_digest_clusters(tmp_db, n=10)
    target = [g for g in groups if g["cluster_id"] == 9001]
    assert len(target) == 1
    assert target[0]["latest_at"] == "2026-10-20T10:00:00+00:00"


def test_latest_at_falls_back_to_fetched(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/latest-fallback.xml")
    now_iso = datetime.now(UTC).isoformat()
    _insert_raw(
        tmp_db,
        feed_id,
        "guid-a",
        "A",
        "2026-10-19T10:00:00+00:00",
        now_iso,
        9002,
        0,
    )
    _insert_raw(
        tmp_db,
        feed_id,
        "guid-b",
        "B",
        None,
        "2026-10-20T12:00:00+00:00",
        9002,
        0,
    )
    groups = get_digest_clusters(tmp_db, n=10)
    target = [g for g in groups if g["cluster_id"] == 9002]
    assert len(target) == 1
    assert target[0]["latest_at"] == "2026-10-20T12:00:00+00:00"
