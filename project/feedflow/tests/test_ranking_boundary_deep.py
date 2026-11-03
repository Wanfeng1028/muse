"""重要性排序空数据/全已读边界深测。编排手工编写（模型输出碎片化且编造列名，弃用）。"""

from datetime import UTC, datetime

from feedflow import db as db_mod
from feedflow import ranking, store


def _ensure_feed(db_path, feed_id=1):
    conn = db_mod.get_conn(db_path)
    try:
        if conn.execute("SELECT id FROM feeds WHERE id = ?", (feed_id,)).fetchone() is None:
            now = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT INTO feeds (id, title, feed_url, created_at) VALUES (?, ?, ?, ?)",
                (feed_id, "test-feed", "http://example.com/feed", now),
            )
            conn.commit()
    finally:
        conn.close()


def _insert(db_path, guid, title, feed_id=1):
    return store.insert_article(
        db_path,
        feed_id=feed_id,
        guid=guid,
        title=title,
        author="",
        link="http://example.com/" + guid,
        summary="",
        content_html="",
        content_text="正文内容",
        published_at=datetime.now(UTC).isoformat(),
    )


def test_get_digest_空库(tmp_db):
    assert ranking.get_digest(tmp_db, 20) == []


def test_get_digest_n非法(tmp_db):
    assert ranking.get_digest(tmp_db, 0) == []
    assert ranking.get_digest(tmp_db, -3) == []
    assert ranking.get_digest(tmp_db, None) == []
    assert ranking.get_digest(tmp_db, "abc") == []


def test_get_digest_全已读为空(tmp_db):
    _ensure_feed(tmp_db)
    ids = [_insert(tmp_db, f"g{i}", f"标题{i}") for i in range(3)]
    for i in ids:
        store.set_read(tmp_db, i, True)
    assert ranking.get_digest(tmp_db, 20) == []


def test_get_digest_只取未读(tmp_db):
    _ensure_feed(tmp_db)
    ids = [_insert(tmp_db, f"g{i}", f"标题{i}") for i in range(3)]
    store.set_read(tmp_db, ids[0], True)
    got = ranking.get_digest(tmp_db, 20)
    assert len(got) == 2
    assert all(a["is_read"] == 0 for a in got)
    assert len(ranking.get_digest(tmp_db, 1)) == 1


def test_rank_articles_空列表(tmp_db):
    assert ranking.rank_articles(tmp_db, []) == []


def test_rank_articles_feed_id缺失默认权重(tmp_db):
    arts = [{"id": 1, "feed_id": None, "title": "t", "published_at": None, "cluster_id": None}]
    got = ranking.rank_articles(tmp_db, arts)
    assert len(got) == 1
    assert "score_info" in got[0]


def test_rank_articles_cluster_id缺失(tmp_db):
    arts = [{"id": 2, "feed_id": None, "title": "t", "published_at": None, "cluster_id": None}]
    got = ranking.rank_articles(tmp_db, arts)
    assert got[0]["score_info"]["cluster_size"] == 1


def test_age_hours_边界():
    from datetime import timedelta

    now = datetime.now(UTC)
    # 未来时间钳制为 0
    future = (now + timedelta(hours=5)).isoformat()
    assert ranking._age_hours(future, None, now) == 0.0
    # 非法字符串回 0
    assert ranking._age_hours("not-a-date", None, now) == 0.0
    # 全空回 0
    assert ranking._age_hours(None, None, now) == 0.0


def test_get_digest_clusters_空库与非法n(tmp_db):
    assert ranking.get_digest_clusters(tmp_db, 10) == []
    assert ranking.get_digest_clusters(tmp_db, 0) == []
    assert ranking.get_digest_clusters(tmp_db, None) == []
    assert ranking.get_digest_clusters(tmp_db, "x") == []


def test_score_article_关键词大小写():
    now = datetime.now(UTC)
    art = {"title": "ai 新闻", "content_text": "", "is_read": 0, "published_at": now.isoformat()}
    info = ranking.score_article(
        art,
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[{"keyword": "AI", "weight": 1.0}],
    )
    assert info["parts"]["keyword"] > 0
    assert any("AI" in r for r in info["reasons"])
    # 空关键词不崩
    info2 = ranking.score_article(
        art, now=now, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[]
    )
    assert info2["parts"]["keyword"] == 0


def _mark_all_read(db_path):
    conn = db_mod.get_conn(db_path)
    try:
        conn.execute("UPDATE articles SET is_read = 1")
        conn.commit()
    finally:
        conn.close()


def test_digest_page_空未读空态(client, tmp_db):
    _mark_all_read(tmp_db)
    resp = client.get("/digest")
    assert resp.status_code == 200
    assert "今天没有未读文章" in resp.get_data(as_text=True)


def test_digest_page_正常渲染(client):
    resp = client.get("/digest")
    assert resp.status_code == 200
    assert "<html" in resp.get_data(as_text=True).lower()


def test_digest_clusters_page_空态不崩(client, tmp_db):
    _mark_all_read(tmp_db)
    resp = client.get("/digest/clusters")
    assert resp.status_code == 200
