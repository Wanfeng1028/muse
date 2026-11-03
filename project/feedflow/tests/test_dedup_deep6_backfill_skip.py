from datetime import UTC, datetime

from feedflow import store
from feedflow.db import get_conn
from feedflow.dedup import backfill_clusters, simhash


def _insert_prefilled(tmp_db, feed_id, guid, text):
    now = datetime.now(UTC).isoformat()
    sh = simhash(text)
    conn = get_conn(tmp_db)
    try:
        cur = conn.execute(
            """
            INSERT INTO articles
                (feed_id, guid, title, author, link, summary,
                 content_html, content_text, published_at, fetched_at,
                 simhash, cluster_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                feed_id,
                guid,
                "t",
                "a",
                "http://example.com/l",
                "s",
                "<p>x</p>",
                text,
                now,
                now,
                sh,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def test_backfill_skips_prefilled_simhash_null_cluster(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/xxx.xml")
    aid = _insert_prefilled(tmp_db, feed_id, "prefilled-1", "独特文本内容")

    result = backfill_clusters(tmp_db)
    assert result == 0

    conn = get_conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT cluster_id FROM articles WHERE id = ?", (aid,)
        ).fetchone()
    finally:
        conn.close()
    assert row["cluster_id"] is None


def test_null_cluster_invisible_to_clustering(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/xxx.xml")
    first_id = _insert_prefilled(tmp_db, feed_id, "prefilled-1", "独特文本内容")

    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="second-1",
        title="独特文本内容二",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="独特文本内容",
        published_at=None,
    )

    conn = get_conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT id, cluster_id FROM articles WHERE guid = ?", ("second-1",)
        ).fetchone()
    finally:
        conn.close()

    assert row["cluster_id"] == row["id"]
    assert row["cluster_id"] != first_id
