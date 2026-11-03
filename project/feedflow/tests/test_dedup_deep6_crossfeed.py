from feedflow import store
from feedflow.dedup import backfill_clusters


def _read_cluster_id(db_path, guid):
    from feedflow.db import get_conn
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT cluster_id FROM articles WHERE guid = ?", (guid,)
        ).fetchone()
        return row["cluster_id"]
    finally:
        conn.close()


def test_cross_feed_same_event_same_cluster(tmp_db):
    feed_a = store.create_feed(tmp_db, "https://example.com/cross_a.xml")
    feed_b = store.create_feed(tmp_db, "https://example.com/cross_b.xml")
    title = "央行宣布降准"
    body = "中国人民银行今日宣布下调存款准备金率 0.5 个百分点，释放长期资金约 1 万亿元，市场反应积极。"
    store.insert_article(
        tmp_db,
        feed_id=feed_a,
        guid="cross-a-1",
        title=title,
        author="",
        link="",
        summary="",
        content_html="",
        content_text=body,
        published_at=None,
    )
    store.insert_article(
        tmp_db,
        feed_id=feed_b,
        guid="cross-b-1",
        title=title,
        author="",
        link="",
        summary="",
        content_html="",
        content_text=body,
        published_at=None,
    )
    backfill_clusters(tmp_db)
    cid_a = _read_cluster_id(tmp_db, "cross-a-1")
    cid_b = _read_cluster_id(tmp_db, "cross-b-1")
    assert cid_a is not None
    assert cid_b is not None
    assert cid_a == cid_b


def test_unrelated_different_cluster(tmp_db):
    feed_a = store.create_feed(tmp_db, "https://example.com/cross_c.xml")
    feed_b = store.create_feed(tmp_db, "https://example.com/cross_d.xml")
    feed_c = store.create_feed(tmp_db, "https://example.com/cross_e.xml")
    title = "央行宣布降准"
    body = "中国人民银行今日宣布下调存款准备金率 0.5 个百分点，释放长期资金约 1 万亿元，市场反应积极。"
    store.insert_article(
        tmp_db,
        feed_id=feed_a,
        guid="cross-c-1",
        title=title,
        author="",
        link="",
        summary="",
        content_html="",
        content_text=body,
        published_at=None,
    )
    store.insert_article(
        tmp_db,
        feed_id=feed_b,
        guid="cross-d-1",
        title=title,
        author="",
        link="",
        summary="",
        content_html="",
        content_text=body,
        published_at=None,
    )
    store.insert_article(
        tmp_db,
        feed_id=feed_c,
        guid="cross-e-1",
        title="今晚吃什么",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="冰箱里还剩半颗白菜和两个鸡蛋，随便炒一炒凑合一顿。",
        published_at=None,
    )
    backfill_clusters(tmp_db)
    cid_a = _read_cluster_id(tmp_db, "cross-c-1")
    cid_b = _read_cluster_id(tmp_db, "cross-d-1")
    cid_c = _read_cluster_id(tmp_db, "cross-e-1")
    assert cid_a is not None
    assert cid_b is not None
    assert cid_c is not None
    assert cid_a == cid_b
    assert cid_c != cid_a
    assert cid_c != cid_b
