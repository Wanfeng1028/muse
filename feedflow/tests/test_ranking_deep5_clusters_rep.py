import pytest
from datetime import UTC, datetime, timedelta

from feedflow import store, db
from feedflow.cluster_scoring import cluster_importance_score
from feedflow.ranking import get_digest_clusters


def _now_iso():
    return datetime.now(UTC).isoformat()


def _insert_clustered(tmp_db, feed_id, guid, title, published_at, cluster_id):
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid=guid,
        title=title,
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=published_at,
    )
    db.execute_write(
        tmp_db,
        "UPDATE articles SET cluster_id = ? WHERE feed_id = ? AND guid = ?",
        (cluster_id, feed_id, guid),
    )


def test_representative_is_top_scored(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/rep5a.xml")

    now = datetime.now(UTC)
    _insert_clustered(tmp_db, feed_id, "g-now", "最新进展", now.isoformat(), 555)
    _insert_clustered(
        tmp_db,
        feed_id,
        "g-100h",
        "百小时前",
        (now - timedelta(hours=100)).isoformat(),
        555,
    )
    _insert_clustered(
        tmp_db,
        feed_id,
        "g-200h",
        "两百小时前",
        (now - timedelta(hours=200)).isoformat(),
        555,
    )

    groups = get_digest_clusters(tmp_db, 10)
    assert len(groups) == 1

    g = groups[0]
    assert g["representative"]["title"] == "最新进展"
    assert g["topic"] == "最新进展"
    assert g["members"] == 3
    assert g["sources"] == 1
    assert g["unread"] == 3


def test_cluster_score_matches_rep(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/rep5b.xml")

    now = datetime.now(UTC)
    _insert_clustered(tmp_db, feed_id, "g-now", "最新进展", now.isoformat(), 555)
    _insert_clustered(
        tmp_db,
        feed_id,
        "g-100h",
        "百小时前",
        (now - timedelta(hours=100)).isoformat(),
        555,
    )
    _insert_clustered(
        tmp_db,
        feed_id,
        "g-200h",
        "两百小时前",
        (now - timedelta(hours=200)).isoformat(),
        555,
    )

    groups = get_digest_clusters(tmp_db, 10)
    assert len(groups) == 1

    g = groups[0]
    rep = g["representative"]
    expected = cluster_importance_score(
        float(rep["score_info"]["score"]),
        g["members"],
        g["sources"],
        g["unread"],
        g["latest_at"],
    )
    assert g["cluster_score"] == pytest.approx(expected, abs=1e-9)
