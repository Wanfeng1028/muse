from datetime import UTC, datetime

from feedflow import db, store
from feedflow.dedup import find_or_create_cluster, get_text_for, hamming


def test_hamming_construction():
    assert hamming("0000000000000000", "00000000000fffff") == 20
    assert hamming("0000000000000000", "00000000001fffff") == 21


def test_prefilter_boundary_20_recalled(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/boundary20.xml")
    now_iso = datetime.now(UTC).isoformat()
    conn = db.get_conn(tmp_db)
    try:
        conn.execute(
            """
            INSERT INTO articles
                (feed_id, guid, title, author, link, summary, content_html,
                 content_text, published_at, fetched_at, simhash, cluster_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feed_id,
                "guid-boundary-20",
                "边界测试标题",
                "",
                "",
                "",
                "",
                "边界测试正文内容用于确认。",
                now_iso,
                now_iso,
                "00000000000fffff",
                77,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    text = get_text_for(
        {"title": "边界测试标题", "content_text": "边界测试正文内容用于确认。"}
    )
    assert find_or_create_cluster(tmp_db, "0000000000000000", text) == 77


def test_prefilter_boundary_21_missed(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/boundary21.xml")
    now_iso = datetime.now(UTC).isoformat()
    conn = db.get_conn(tmp_db)
    try:
        conn.execute(
            """
            INSERT INTO articles
                (feed_id, guid, title, author, link, summary, content_html,
                 content_text, published_at, fetched_at, simhash, cluster_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feed_id,
                "guid-boundary-21",
                "边界测试标题",
                "",
                "",
                "",
                "",
                "边界测试正文内容用于确认。",
                now_iso,
                now_iso,
                "00000000001fffff",
                78,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    text = get_text_for(
        {"title": "边界测试标题", "content_text": "边界测试正文内容用于确认。"}
    )
    assert find_or_create_cluster(tmp_db, "0000000000000000", text) is None
