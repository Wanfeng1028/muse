
from feedflow import db, store
from feedflow.ranking import get_digest


def _insert_three_unread(tmp_db, feed_id):
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="g1",
        title="t1",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="g2",
        title="t2",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="g3",
        title="t3",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )


def test_digest_n_truncation(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/n_trunc.xml")
    _insert_three_unread(tmp_db, feed_id)

    assert len(get_digest(tmp_db, 1)) == 1
    assert len(get_digest(tmp_db, 99)) == 3
    assert len(get_digest(tmp_db, "2")) == 2
    assert len(get_digest(tmp_db, None)) == 3


def test_digest_n_invalid_and_read(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/n_invalid.xml")
    _insert_three_unread(tmp_db, feed_id)

    assert get_digest(tmp_db, 0) == []
    assert get_digest(tmp_db, -5) == []

    row = db.query_one(
        tmp_db,
        "SELECT id FROM articles WHERE feed_id = ? ORDER BY id ASC LIMIT 1",
        (feed_id,),
    )
    article_id = int(row["id"])
    db.execute_write(
        tmp_db,
        "UPDATE articles SET is_read = 1 WHERE id = ?",
        (article_id,),
    )

    assert len(get_digest(tmp_db, 99)) == 2
