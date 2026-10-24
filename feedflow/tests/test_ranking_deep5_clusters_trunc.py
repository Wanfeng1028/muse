from datetime import UTC, datetime, timedelta

import pytest

from feedflow import db, store
from feedflow.ranking import get_digest_clusters


def _now_iso():
    return datetime.now(UTC).isoformat()


def _iso_hours_ago(hours):
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _insert_solo_article(db_path, feed_id, guid, title, published_at):
    now = db.utcnow()
    with db.write_lock:
        conn = db.get_conn(db_path)
        cur = conn.execute(
            """
            INSERT INTO articles (
                feed_id, guid, title, author, link, summary,
                content_html, content_text, published_at, fetched_at,
                is_read, is_starred, cluster_id
            ) VALUES (?, ?, ?, '', '', '', '', '', ?, ?, 0, 0, NULL)
            """,
            (feed_id, guid, title, published_at, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def test_truncation_and_score_order(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/trunc.xml")

    _insert_solo_article(tmp_db, feed_id, "g-now", "fresh one", _iso_hours_ago(0))
    _insert_solo_article(tmp_db, feed_id, "g-100h", "mid one", _iso_hours_ago(100))
    _insert_solo_article(tmp_db, feed_id, "g-200h", "old one", _iso_hours_ago(200))

    groups = get_digest_clusters(tmp_db, 2)

    assert len(groups) == 2
    assert groups[0]["cluster_score"] >= groups[1]["cluster_score"]


def test_score_tie_larger_cluster_first(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/tie.xml")

    pub = _iso_hours_ago(0)
    id1 = _insert_solo_article(tmp_db, feed_id, "tie-1", "same title", pub)
    id2 = _insert_solo_article(tmp_db, feed_id, "tie-2", "same title", pub)

    groups = get_digest_clusters(tmp_db, 10)

    assert len(groups) == 2
    # 两篇同标题同发布时间：分数仅差 fetched_at 微秒级时效因子，用近似相等
    assert groups[0]["cluster_score"] == pytest.approx(groups[1]["cluster_score"], abs=1e-6)
    assert groups[0]["cluster_id"] > groups[1]["cluster_id"]
    assert {groups[0]["cluster_id"], groups[1]["cluster_id"]} == {id1, id2}
