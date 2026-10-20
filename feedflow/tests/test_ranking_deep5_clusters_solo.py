import pytest

from feedflow import store, db
from feedflow.ranking import get_digest_clusters


EXPECTED_KEYS = {
    "cluster_id",
    "topic",
    "members",
    "sources",
    "source_titles",
    "unread",
    "representative",
    "cluster_score",
    "cluster_reasons",
    "latest_at",
}


def _insert_solo_article(db_path, feed_id, guid, title):
    with db.write_lock:
        conn = db.get_conn(db_path)
        cur = conn.execute(
            """
            INSERT INTO articles
                (feed_id, guid, title, author, link, summary,
                 content_html, content_text, published_at, fetched_at,
                 is_read, is_starred, cluster_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL)
            """,
            (
                feed_id,
                guid,
                title,
                "",
                "",
                "",
                "",
                "",
                None,
                "2024-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def test_solo_group_shape(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/solo_shape.xml")
    aid1 = _insert_solo_article(tmp_db, feed_id, "solo-shape-1", "Solo One")
    aid2 = _insert_solo_article(tmp_db, feed_id, "solo-shape-2", "Solo Two")

    groups = get_digest_clusters(tmp_db, 10)

    assert len(groups) == 2
    cids = {g["cluster_id"] for g in groups}
    assert cids == {aid1, aid2}
    for g in groups:
        assert g["members"] == 1
        assert g["sources"] == 1
        assert g["unread"] == 1
        assert set(g.keys()) == EXPECTED_KEYS


def test_solo_source_titles(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/solo_titles.xml")
    _insert_solo_article(tmp_db, feed_id, "solo-titles-1", "Titles One")
    _insert_solo_article(tmp_db, feed_id, "solo-titles-2", "Titles Two")

    feed = store.get_feed(tmp_db, feed_id)
    feed_title = feed["title"]

    groups = get_digest_clusters(tmp_db, 10)

    assert len(groups) == 2
    for g in groups:
        assert g["source_titles"] == [feed_title]
