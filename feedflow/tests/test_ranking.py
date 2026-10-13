import datetime as _dt

import pytest

from feedflow import db, ranking, store


def _make_feed(tmp_db, feed_url="https://example.com/x.xml"):
    return store.create_feed(tmp_db, feed_url)


def _make_article(
    tmp_db, feed_id, guid, title="t", published_at=None, content_html="<p>body</p>", summary="s"
):
    return store.insert_article(
        tmp_db,
        feed_id,
        guid,
        title,
        "author",
        "https://example.com/a",
        summary,
        content_html,
        "body",
        published_at,
    )


def _article_row(tmp_db, aid):
    return dict(db.query_one(tmp_db, "SELECT * FROM articles WHERE id=?", (aid,)))


def _score(tmp_db, aid, now, cluster_size=1):
    # 统一按真实签名调用 score_article
    return ranking.score_article(
        _article_row(tmp_db, aid),
        now=now,
        cluster_size=cluster_size,
        feed_weight=1.0,
        learned=1.0,
        keywords=ranking.get_keywords(tmp_db),
    )


def test_score_deterministic(tmp_db):
    # 同一篇文章、固定 now，score_article 两次结果完全相等
    fid = _make_feed(tmp_db)
    aid = _make_article(tmp_db, fid, "g1", "标题", db.utcnow())
    row = _article_row(tmp_db, aid)
    now = _dt.datetime(2030, 1, 1, tzinfo=_dt.UTC)
    a = ranking.score_article(
        row,
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )
    b = ranking.score_article(
        row,
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )
    assert a == b


def test_digest_empty_db(tmp_db):
    # 空库返回空列表
    assert ranking.get_digest(tmp_db) == []


def test_digest_single_article(tmp_db):
    # 一篇未读，返回 1 篇且带 score_info
    fid = _make_feed(tmp_db)
    _make_article(tmp_db, fid, "g1", "唯一", db.utcnow())
    digest = ranking.get_digest(tmp_db)
    assert len(digest) == 1
    item = digest[0]
    assert "score_info" in item
    si = item["score_info"]
    assert "score" in si and "parts" in si and "reasons" in si


def test_recency_monotonic(tmp_db):
    # 同源两篇，仅 published_at 不同，新文章分数与 recency 分项更高
    fid = _make_feed(tmp_db)
    now = _dt.datetime.now(_dt.UTC)
    new_pub = (now - _dt.timedelta(hours=1)).isoformat()
    old_pub = (now - _dt.timedelta(days=3)).isoformat()
    new_id = _make_article(tmp_db, fid, "new", "同标题", new_pub)
    old_id = _make_article(tmp_db, fid, "old", "同标题", old_pub)
    new_s = _score(tmp_db, new_id, now)
    old_s = _score(tmp_db, old_id, now)
    assert new_s["score"] > old_s["score"]
    assert new_s["parts"]["recency"] > old_s["parts"]["recency"]


def test_keyword_boost(tmp_db):
    # 加关键词后，标题含关键词的文章分数更高
    fid = _make_feed(tmp_db)
    pub = db.utcnow()
    hit = _make_article(tmp_db, fid, "hit", "量子计算突破", pub)
    miss = _make_article(tmp_db, fid, "miss", "普通新闻", pub)
    now = _dt.datetime.now(_dt.UTC)
    hit_s = _score(tmp_db, hit, now)
    miss_s = _score(tmp_db, miss, now)
    assert hit_s["score"] == miss_s["score"]  # 加关键词前两者分数相同
    ranking.add_keyword(tmp_db, "量子")
    hit_s2 = _score(tmp_db, hit, now)
    miss_s2 = _score(tmp_db, miss, now)
    assert hit_s2["score"] > miss_s2["score"]
    assert hit_s2["score"] >= hit_s["score"]


def test_unread_bonus(tmp_db):
    # 同内容，未读分数高于已读
    fid = _make_feed(tmp_db)
    pub = db.utcnow()
    a = _make_article(tmp_db, fid, "a", "内容相同", pub)
    b = _make_article(tmp_db, fid, "b", "内容相同", pub)
    store.set_read(tmp_db, a, True)
    now = _dt.datetime.now(_dt.UTC)
    a_s = _score(tmp_db, a, now)
    b_s = _score(tmp_db, b, now)
    assert b_s["score"] > a_s["score"]


def test_heat_cluster(tmp_db):
    # 簇内 3 篇 heat 分项 > 单篇
    fid = _make_feed(tmp_db)
    pub = db.utcnow()
    ids = [_make_article(tmp_db, fid, f"c{i}", f"簇文{i}", pub) for i in range(3)]
    single = _make_article(tmp_db, fid, "s", "单篇", pub)
    for aid in ids:
        db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (99, aid))
    now = _dt.datetime.now(_dt.UTC)
    cluster_s = _score(tmp_db, ids[0], now, cluster_size=3)
    single_s = _score(tmp_db, single, now, cluster_size=1)
    assert cluster_s["parts"]["heat"] > single_s["parts"]["heat"]


def test_tiebreak_deterministic(tmp_db):
    # 完全相同的两篇，排序稳定（按 id 降序）
    fid = _make_feed(tmp_db)
    pub = "2025-01-01T00:00:00+00:00"
    a = _make_article(tmp_db, fid, "ta", "相同", pub)
    b = _make_article(tmp_db, fid, "tb", "相同", pub)
    d1 = ranking.get_digest(tmp_db)
    d2 = ranking.get_digest(tmp_db)
    ids1 = [x["id"] for x in d1]
    ids2 = [x["id"] for x in d2]
    assert ids1 == ids2
    assert ids1.index(max(a, b)) < ids1.index(min(a, b))


def test_learned_cold_start(tmp_db):
    # 冷启动 learned==1.0；有反馈后 >1.0
    fid = _make_feed(tmp_db)
    ranking.learn_source_weights(tmp_db)
    w = next(x for x in ranking.get_feed_weights(tmp_db) if x["feed_id"] == fid)
    assert w["learned"] == 1.0
    pub = db.utcnow()
    ids = [_make_article(tmp_db, fid, f"l{i}", f"文章{i}", pub) for i in range(4)]
    for aid in ids[:2]:
        db.execute_write(tmp_db, "UPDATE articles SET is_starred=1 WHERE id=?", (aid,))
    db.execute_write(tmp_db, "UPDATE articles SET is_read=1 WHERE id=?", (ids[2],))
    ranking.learn_source_weights(tmp_db)
    w2 = next(x for x in ranking.get_feed_weights(tmp_db) if x["feed_id"] == fid)
    assert w2["learned"] > 1.0


def test_set_feed_weight_validation(tmp_db):
    # 非法值抛 ValueError；不存在的 feed 抛 ValueError；合法值可读回
    fid = _make_feed(tmp_db)
    with pytest.raises(ValueError):
        ranking.set_feed_weight(tmp_db, fid, 99)
    with pytest.raises(ValueError):
        ranking.set_feed_weight(tmp_db, 999999, 2.0)
    ranking.set_feed_weight(tmp_db, fid, 2.0)
    w = next(x for x in ranking.get_feed_weights(tmp_db) if x["feed_id"] == fid)
    assert w["weight"] == 2.0


def test_keywords_crud(tmp_db):
    # add 返回 id，重复返回同一 id，空串抛错，delete 后可清空，删不存在返回 False
    kid = ranking.add_keyword(tmp_db, "ai")
    assert isinstance(kid, int)
    kid2 = ranking.add_keyword(tmp_db, "ai")
    assert kid == kid2
    with pytest.raises(ValueError):
        ranking.add_keyword(tmp_db, "")
    assert ranking.delete_keyword(tmp_db, kid) is True
    assert ranking.get_keywords(tmp_db) == []
    assert ranking.delete_keyword(tmp_db, 123456) is False


def test_settings_roundtrip(tmp_db):
    # 设置读写与默认值
    assert ranking.get_digest_n(tmp_db) == 20
    ranking.set_setting(tmp_db, "digest_n", "5")
    assert ranking.get_digest_n(tmp_db) == 5
    ranking.set_setting(tmp_db, "digest_n", "abc")
    assert ranking.get_digest_n(tmp_db) == 20


def test_digest_limit(tmp_db):
    # n 限制生效，且按 score 降序
    fid = _make_feed(tmp_db)
    now_dt = _dt.datetime.now(_dt.UTC)
    for i in range(5):
        pub = (now_dt - _dt.timedelta(hours=i)).isoformat()
        _make_article(tmp_db, fid, f"d{i}", f"文章{i}", pub)
    d = ranking.get_digest(tmp_db, n=2)
    assert len(d) == 2
    scores = [x["score_info"]["score"] for x in d]
    assert scores == sorted(scores, reverse=True)


def test_migration_v2_tables(tmp_db):
    # 迁移后新表存在，且幂等
    conn = db.get_conn(tmp_db)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r[0] for r in rows}
        assert {"keywords", "feed_weights", "settings"} <= names
        db.run_migrations(conn)
    finally:
        conn.close()


def test_digest_page(client, tmp_db):
    # /digest 页面渲染并含文章标题
    rv = client.get("/digest")
    assert rv.status_code == 200
    assert "今日必读" in rv.get_data(as_text=True)
    fid = _make_feed(tmp_db)
    _make_article(tmp_db, fid, "pg1", "页面标题X", db.utcnow())
    rv2 = client.get("/digest")
    assert rv2.status_code == 200
    assert "页面标题X" in rv2.get_data(as_text=True)


def test_interests_page(client, tmp_db):
    # 兴趣设置页与表单提交
    rv = client.get("/settings/interests")
    assert rv.status_code == 200
    assert "关键词" in rv.get_data(as_text=True)

    rv = client.post("/settings/interests/keywords", data={"keyword": "测试词"})
    assert rv.status_code == 302
    kws = ranking.get_keywords(tmp_db)
    assert any(k.get("keyword") == "测试词" for k in kws)

    rv = client.post("/settings/interests/digest_n", data={"n": "10"})
    assert rv.status_code in (200, 302)
    assert ranking.get_digest_n(tmp_db) == 10

    rv = client.post("/settings/interests/digest_n", data={"n": "0"})
    loc = rv.headers.get("Location", "")
    if rv.status_code in (301, 302, 303, 307, 308):
        assert "err=n" in loc
    else:
        assert rv.status_code == 200
