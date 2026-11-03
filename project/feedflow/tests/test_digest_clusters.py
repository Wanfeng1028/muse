
import datetime as _dt

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


def _set_cluster(tmp_db, aid, cid):
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (cid, aid))


def _mark_read(tmp_db, aid):
    db.execute_write(tmp_db, "UPDATE articles SET is_read=1 WHERE id=?", (aid,))


def _fixed_now():
    return _dt.datetime(2030, 1, 1, tzinfo=_dt.UTC)


def _pub(now, hours=1):
    return (now - _dt.timedelta(hours=hours)).isoformat()


def test_clusters_empty_db(tmp_db):
    assert ranking.get_digest_clusters(tmp_db, n=10) == []


def test_clusters_same_cluster_two_unread(tmp_db):
    now = _fixed_now()
    fid1 = _make_feed(tmp_db, "https://example.com/a.xml")
    fid2 = _make_feed(tmp_db, "https://example.com/b.xml")
    a1 = _make_article(tmp_db, fid1, "g1", "低分标题", _pub(now, 48))
    a2 = _make_article(tmp_db, fid2, "g2", "高分标题", _pub(now, 1))
    _set_cluster(tmp_db, a1, 7)
    _set_cluster(tmp_db, a2, 7)

    clusters = ranking.get_digest_clusters(tmp_db, n=10, now=now)
    assert len(clusters) == 1
    c = clusters[0]
    assert c["cluster_id"] == 7
    assert c["members"] == 2
    assert c["sources"] == 2
    assert c["topic"] == "高分标题"
    assert c["unread"] == 2


def test_clusters_null_cluster_ids_separate(tmp_db):
    now = _fixed_now()
    fid = _make_feed(tmp_db)
    a1 = _make_article(tmp_db, fid, "g1", "标题一", _pub(now, 1))
    a2 = _make_article(tmp_db, fid, "g2", "标题二", _pub(now, 2))
    # insert_article 入库即自动聚类；显式置 NULL 才能走到 solo 分支
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=NULL WHERE id IN (?, ?)", (a1, a2))
    clusters = ranking.get_digest_clusters(tmp_db, n=10, now=now)
    # cluster_id 为 NULL 的文章各自成组，组 cluster_id 取文章 id
    assert len(clusters) == 2
    ids = {c["cluster_id"] for c in clusters}
    assert ids == {a1, a2}
    for c in clusters:
        assert c["members"] == 1
        assert c["unread"] == 1


def test_clusters_read_counted_in_members_not_unread(tmp_db):
    now = _fixed_now()
    fid1 = _make_feed(tmp_db, "https://example.com/a.xml")
    fid2 = _make_feed(tmp_db, "https://example.com/b.xml")
    a1 = _make_article(tmp_db, fid1, "g1", "未读标题", _pub(now, 1))
    a2 = _make_article(tmp_db, fid2, "g2", "已读标题", _pub(now, 2))
    _set_cluster(tmp_db, a1, 42)
    _set_cluster(tmp_db, a2, 42)
    _mark_read(tmp_db, a2)

    clusters = ranking.get_digest_clusters(tmp_db, n=10, now=now)
    assert len(clusters) == 1
    c = clusters[0]
    assert c["cluster_id"] == 42
    assert c["members"] == 2
    assert c["unread"] == 1


def test_clusters_n_truncates_and_sorted_desc(tmp_db):
    now = _fixed_now()
    fid = _make_feed(tmp_db)
    pairs = [
        ("a", 1, 1),
        ("b", 2, 20),
        ("c", 3, 40),
    ]
    for guid, cid, hours in pairs:
        aid = _make_article(tmp_db, fid, guid, "标题" + guid, _pub(now, hours))
        _set_cluster(tmp_db, aid, cid)

    clusters = ranking.get_digest_clusters(tmp_db, n=2, now=now)
    assert len(clusters) == 2
    scores = [c["cluster_score"] for c in clusters]
    assert scores == sorted(scores, reverse=True)


def test_clusters_n_non_positive_returns_empty(tmp_db):
    now = _fixed_now()
    fid = _make_feed(tmp_db)
    aid = _make_article(tmp_db, fid, "g1", "标题", _pub(now, 1))
    _set_cluster(tmp_db, aid, 1)
    assert ranking.get_digest_clusters(tmp_db, n=0, now=now) == []
    assert ranking.get_digest_clusters(tmp_db, n=-3, now=now) == []


def test_clusters_reasons_include_same_event_no_dup(tmp_db):
    now = _fixed_now()
    fid1 = _make_feed(tmp_db, "https://example.com/a.xml")
    fid2 = _make_feed(tmp_db, "https://example.com/b.xml")
    a1 = _make_article(tmp_db, fid1, "g1", "标题一", _pub(now, 1))
    a2 = _make_article(tmp_db, fid2, "g2", "标题二", _pub(now, 2))
    _set_cluster(tmp_db, a1, 5)
    _set_cluster(tmp_db, a2, 5)

    clusters = ranking.get_digest_clusters(tmp_db, n=10, now=now)
    assert len(clusters) == 1
    reasons = clusters[0]["cluster_reasons"]
    assert isinstance(reasons, list)
    same_event = [r for r in reasons if "同事件" in r]
    assert len(same_event) >= 1
    assert len(same_event) == len(set(same_event))


def test_clusters_source_titles_dedup_cap_5(tmp_db):
    now = _fixed_now()
    fid1 = _make_feed(tmp_db, "https://example.com/a.xml")
    fid2 = _make_feed(tmp_db, "https://example.com/b.xml")
    ids = []
    for i in range(4):
        aid = _make_article(tmp_db, fid1, f"ga{i:d}", f"同源标题{i:d}", _pub(now, i + 1))
        ids.append(aid)
    aid2 = _make_article(tmp_db, fid2, "gb", "另一源标题", _pub(now, 1))
    ids.append(aid2)
    for aid in ids:
        _set_cluster(tmp_db, aid, 9)

    clusters = ranking.get_digest_clusters(tmp_db, n=10, now=now)
    assert len(clusters) == 1
    titles = clusters[0]["source_titles"]
    assert len(titles) == len(set(titles))
    assert len(titles) <= 5


def test_clusters_representative_score_info_matches_rank_articles(tmp_db):
    now = _fixed_now()
    fid1 = _make_feed(tmp_db, "https://example.com/a.xml")
    fid2 = _make_feed(tmp_db, "https://example.com/b.xml")
    a1 = _make_article(tmp_db, fid1, "g1", "标题一", _pub(now, 1))
    a2 = _make_article(tmp_db, fid2, "g2", "标题二", _pub(now, 2))
    _set_cluster(tmp_db, a1, 11)
    _set_cluster(tmp_db, a2, 11)

    clusters = ranking.get_digest_clusters(tmp_db, n=10, now=now)
    assert len(clusters) == 1
    rep = clusters[0]["representative"]
    assert "score_info" in rep

    ranked = ranking.get_digest(tmp_db, n=10, now=now)
    match = [r for r in ranked if r["id"] == rep["id"]]
    assert len(match) == 1
    assert match[0]["score_info"]["score"] == rep["score_info"]["score"]
