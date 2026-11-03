"""深度测试：去重聚类阈值边界。"""

from datetime import UTC, datetime, timedelta

import pytest

from feedflow import db as db_mod
from feedflow import dedup, store


def _ensure_feed(db_path, feed_id=1):
    """若不存在则建 feeds 行。"""
    conn = db_mod.get_conn(db_path)
    try:
        cur = conn.execute("SELECT id FROM feeds WHERE id = ?", (feed_id,))
        if cur.fetchone() is None:
            now = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT INTO feeds (id, title, feed_url, created_at) VALUES (?, ?, ?, ?)",
                (feed_id, "test-feed", "http://example.com/feed", now),
            )
            conn.commit()
    finally:
        conn.close()


def _insert(db_path, guid, title, content_text, published_at=None, feed_id=1):
    return store.insert_article(
        db_path,
        feed_id=feed_id,
        guid=guid,
        title=title,
        author="",
        link="http://example.com/" + guid,
        summary="",
        content_html="",
        content_text=content_text,
        published_at=published_at,
    )


def _now_iso():
    return datetime.now(UTC).isoformat()


def test_hamming_非法输入返回64():
    assert dedup.hamming("", "ff") == 64
    assert dedup.hamming("zz", "ff") == 64
    assert dedup.hamming(None, "ff") == 64


def test_is_near_dup_阈值边界():
    a = "ff" * 8  # 64 位全 1
    # 低 3 位置 0：f8 = 1111 1000，与 ff = 1111 1111 差 3 位
    b3 = "ff" * 7 + "f8"
    assert dedup.hamming(a, b3) == 3
    assert dedup.is_near_dup(a, b3) is True
    # 低 4 位置 0：f0 = 1111 0000，与 ff = 1111 1111 差 4 位
    b4 = "ff" * 7 + "f0"
    assert dedup.hamming(a, b4) == 4
    assert dedup.is_near_dup(a, b4) is False


def test_jaccard_空集合为0():
    assert dedup.jaccard_similarity("", "abc") == 0.0
    assert dedup.jaccard_similarity("abc", "") == 0.0


def test_jaccard_阈值0_35边界():
    ta = " ".join([f"w{i}" for i in range(14)])
    tb = " ".join([f"w{i}" for i in range(7)] + [f"z{i}" for i in range(6)])
    # 交集 7，并集 14+13-7=20 → 0.35
    assert dedup.jaccard_similarity(ta, tb) == pytest.approx(0.35)
    tc = tb + " z6"
    # 交集 7，并集 14+14-7=21 → 0.333 < 0.35
    assert dedup.jaccard_similarity(ta, tc) < dedup.JACCARD_THRESHOLD


def test_cluster_空simhash返回None(tmp_db):
    assert dedup.find_or_create_cluster(tmp_db, "", "some text") is None
    assert dedup.find_or_create_cluster(tmp_db, None) is None


def test_cluster_text空纯汉明路径(tmp_db):
    _ensure_feed(tmp_db)
    now = _now_iso()
    conn = db_mod.get_conn(tmp_db)
    try:
        conn.execute(
            "INSERT INTO articles (feed_id, guid, title, content_text, published_at, fetched_at, simhash, cluster_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "g1", "t1", "", now, now, "ff" * 8, 100),
        )
        conn.commit()
    finally:
        conn.close()
    # hamming 3 恰好阈值
    assert dedup.find_or_create_cluster(tmp_db, "ff" * 7 + "f8", text="") == 100
    # hamming 4 超阈值
    assert dedup.find_or_create_cluster(tmp_db, "ff" * 7 + "f0", text="") is None


def test_cluster_jaccard确认边界(tmp_db):
    _ensure_feed(tmp_db)
    now = _now_iso()
    title = "w0 w1 w2 w3 w4 w5 w6 y0 y1 y2 y3 y4 y5 y6"
    same_simhash = dedup.simhash("query-text-placeholder")
    conn = db_mod.get_conn(tmp_db)
    try:
        conn.execute(
            "INSERT INTO articles (feed_id, guid, title, content_text, published_at, fetched_at, simhash, cluster_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "g1", title, "", now, now, same_simhash, 200),
        )
        conn.commit()
    finally:
        conn.close()
    # 候选文本 get_text_for = (title+" ")*2 → token 集仍为 14 词
    query_text_35 = "w0 w1 w2 w3 w4 w5 w6 z0 z1 z2 z3 z4 z5"
    # 交集 7，并集 20 → 0.35
    assert dedup.find_or_create_cluster(tmp_db, same_simhash, text=query_text_35) == 200
    query_text_333 = query_text_35 + " z6"
    # 交集 7，并集 21 → 0.333 < 0.35
    assert dedup.find_or_create_cluster(tmp_db, same_simhash, text=query_text_333) is None


def test_cluster_14天窗口边界(tmp_db):
    _ensure_feed(tmp_db)
    now = datetime.now(UTC)
    a_pub = (now - timedelta(days=13, hours=23)).isoformat()
    b_pub = (now - timedelta(days=14, seconds=1)).isoformat()
    same_simhash = dedup.simhash("window-test")
    title_text = "alpha beta gamma delta"
    conn = db_mod.get_conn(tmp_db)
    try:
        conn.execute(
            "INSERT INTO articles (feed_id, guid, title, content_text, published_at, fetched_at, simhash, cluster_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "gA", title_text, "", a_pub, a_pub, same_simhash, 300),
        )
        conn.execute(
            "INSERT INTO articles (feed_id, guid, title, content_text, published_at, fetched_at, simhash, cluster_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "gB", title_text, "", b_pub, b_pub, same_simhash, 301),
        )
        conn.commit()
    finally:
        conn.close()
    # A 在窗口内，B 在窗口外被过滤
    assert dedup.find_or_create_cluster(tmp_db, same_simhash, text=title_text) == 300


def test_cluster_无published_at回落fetched_at(tmp_db):
    _ensure_feed(tmp_db)
    now = _now_iso()
    same_simhash = dedup.simhash("fallback-test")
    title_text = "alpha beta gamma delta"
    conn = db_mod.get_conn(tmp_db)
    try:
        conn.execute(
            "INSERT INTO articles (feed_id, guid, title, content_text, published_at, fetched_at, simhash, cluster_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "g1", title_text, "", None, now, same_simhash, 400),
        )
        conn.commit()
    finally:
        conn.close()
    assert dedup.find_or_create_cluster(tmp_db, same_simhash, text=title_text) == 400


def test_backfill_幂等不提新簇(tmp_db):
    _ensure_feed(tmp_db)
    _insert(tmp_db, "g1", "title", "content")
    dedup.backfill_clusters(tmp_db)
    second = dedup.backfill_clusters(tmp_db)
    assert second == 0
