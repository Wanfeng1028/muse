import pytest
from feedflow.dedup import (
    find_or_create_cluster,
    hamming,
)
from feedflow import store


def test_threshold0_exact_match(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/deep6_thr0_exact.xml")
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="g-deep6-thr0-exact",
        title="hello world",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="hello world content",
        published_at=None,
    )
    conn = store.get_conn(tmp_db) if hasattr(store, "get_conn") else None
    from feedflow.db import get_conn
    conn = get_conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT simhash, cluster_id FROM articles WHERE feed_id = ? AND guid = ?",
            (feed_id, "g-deep6-thr0-exact"),
        ).fetchone()
    finally:
        conn.close()
    s0 = row["simhash"]
    c0 = row["cluster_id"]
    assert c0 is not None
    assert find_or_create_cluster(tmp_db, s0, "", threshold=0) == c0


def test_threshold0_one_bit_diff_missed(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/deep6_thr0_miss.xml")
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="g-deep6-thr0-miss",
        title="hello world",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="hello world content",
        published_at=None,
    )
    from feedflow.db import get_conn
    conn = get_conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT simhash FROM articles WHERE feed_id = ? AND guid = ?",
            (feed_id, "g-deep6-thr0-miss"),
        ).fetchone()
    finally:
        conn.close()
    s0 = row["simhash"]
    s1 = format(int(s0, 16) ^ 1, "016x")
    assert hamming(s0, s1) == 1
    assert find_or_create_cluster(tmp_db, s1, "", threshold=0) is None


def test_default_threshold_allows_one_bit(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/deep6_default_ok.xml")
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="g-deep6-default-ok",
        title="hello world",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="hello world content",
        published_at=None,
    )
    from feedflow.db import get_conn
    conn = get_conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT simhash, cluster_id FROM articles WHERE feed_id = ? AND guid = ?",
            (feed_id, "g-deep6-default-ok"),
        ).fetchone()
    finally:
        conn.close()
    s0 = row["simhash"]
    c0 = row["cluster_id"]
    s1 = format(int(s0, 16) ^ 1, "016x")
    assert find_or_create_cluster(tmp_db, s1, "") == c0
