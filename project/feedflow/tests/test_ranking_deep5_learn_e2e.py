
from feedflow import db, store
from feedflow.ranking import (
    SOURCE_NORM,
    rank_articles,
    score_article,
)


def _insert_article(db_path, feed_id, guid):
    return store.insert_article(
        db_path,
        feed_id=feed_id,
        guid=guid,
        title="",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )


def test_learn_all_starred_max(tmp_db):
    fid = store.create_feed(tmp_db, "https://example.com/all_starred.xml")
    for i in range(4):
        aid = _insert_article(tmp_db, fid, f"all-star-{i}")
        db.execute_write(
            tmp_db,
            "UPDATE articles SET is_read = 1, is_starred = 1 WHERE id = ?",
            (aid,),
        )

    rank_articles(tmp_db, [])

    row = db.query_one(
        tmp_db,
        "SELECT learned FROM feed_weights WHERE feed_id = ?",
        (fid,),
    )
    assert row is not None
    assert row["learned"] == 2.0


def test_learn_unread_unstarred_one(tmp_db):
    fid = store.create_feed(tmp_db, "https://example.com/none_engaged.xml")
    for i in range(4):
        _insert_article(tmp_db, fid, f"none-{i}")

    rank_articles(tmp_db, [])

    row = db.query_one(
        tmp_db,
        "SELECT learned FROM feed_weights WHERE feed_id = ?",
        (fid,),
    )
    assert row is not None
    assert row["learned"] == 1.0


def test_learned_affects_source():
    from datetime import UTC, datetime

    art = {
        "id": 1,
        "feed_id": 1,
        "title": "",
        "summary": "",
        "content_text": "",
        "published_at": None,
        "fetched_at": None,
        "is_read": 0,
        "cluster_id": None,
    }
    now = datetime.now(UTC)

    high = score_article(
        art,
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=2.0,
        keywords=[],
    )
    assert high["parts"]["source"] == round(min(1.0, 1.0 * 2.0 / SOURCE_NORM), 4)
    assert high["parts"]["source"] == 0.8

    low = score_article(
        art,
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )
    assert low["parts"]["source"] == round(min(1.0, 1.0 * 1.0 / SOURCE_NORM), 4)
    assert low["parts"]["source"] == 0.4
