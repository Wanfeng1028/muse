from feedflow import store
from feedflow.db import get_conn
from feedflow.dedup import find_or_create_cluster, get_text_for, simhash, tokenize


def test_emoji_tokens_identical():
    text_a = "今天发布了全新产品，欢迎体验。"
    text_b = "今天发布了全新产品，欢迎体验。"
    assert tokenize(text_a) == tokenize(text_b)


def test_emoji_simhash_identical():
    text_a = "今天发布了全新产品，欢迎体验。"
    text_b = "今天发布了全新产品，欢迎体验。"
    assert simhash(text_a) == simhash(text_b)


def test_emoji_same_cluster(tmp_db):
    feed_id = "feed-emoji"
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="emoji-article-a",
        title="新品发布啦",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="今天发布了全新产品，欢迎体验。",
        published_at=None,
    )
    conn = get_conn(tmp_db)
    try:
        row_a = conn.execute(
            "SELECT id, title, content_text FROM articles WHERE guid = ?",
            ("emoji-article-a",),
        ).fetchone()
    finally:
        conn.close()
    assert row_a is not None

    text_a = get_text_for({"title": row_a["title"], "content_text": row_a["content_text"]})
    sh_a = simhash(text_a)

    cluster_id = find_or_create_cluster(tmp_db, sh_a, text_a)
    assert cluster_id is not None

    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="emoji-article-b",
        title="新品发布啦",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="今天发布了全新产品，欢迎体验。",
        published_at=None,
    )
    conn = get_conn(tmp_db)
    try:
        row_b = conn.execute(
            "SELECT id, title, content_text FROM articles WHERE guid = ?",
            ("emoji-article-b",),
        ).fetchone()
    finally:
        conn.close()
    assert row_b is not None

    text_b = get_text_for({"title": row_b["title"], "content_text": row_b["content_text"]})
    sh_b = simhash(text_b)

    cluster_id_b = find_or_create_cluster(tmp_db, sh_b, text_b)
    assert cluster_id_b == cluster_id
