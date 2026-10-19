"""feedflow.ranking 深度测试。"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from feedflow import db as db_mod
from feedflow import ranking


def _mk_feed(tmp_db, url="https://example.com/feed.xml", title="F", position=0):
    conn = db_mod.get_conn(tmp_db)
    cur = conn.execute(
        "INSERT INTO feeds (feed_url, title, position, created_at) VALUES (?, ?, ?, ?)",
        (url, title, position, db_mod.utcnow()),
    )
    conn.commit()
    return int(cur.lastrowid)


def _mk_article(
    tmp_db,
    feed_id,
    guid,
    *,
    title="t",
    content_text="",
    summary="",
    published_at=None,
    fetched_at=None,
    is_read=0,
    is_starred=0,
    cluster_id=None,
):
    conn = db_mod.get_conn(tmp_db)
    now = db_mod.utcnow()
    cur = conn.execute(
        """
        INSERT INTO articles
            (feed_id, guid, title, content_text, summary, published_at, fetched_at,
             is_read, is_starred, cluster_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            feed_id,
            guid,
            title,
            content_text,
            summary,
            published_at,
            fetched_at if fetched_at is not None else now,
            is_read,
            is_starred,
            cluster_id,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


NOW = datetime(2025, 1, 10, 12, 0, 0, tzinfo=UTC)


def _expected_score(recency, heat, source, keyword, unread):
    return round(
        0.30 * recency
        + 0.25 * heat
        + 0.20 * source
        + 0.15 * keyword
        + 0.10 * unread,
        4,
    )


# ---------------- 1. 时间衰减 ----------------


def test_recency_at_age_zero_is_one():
    art = {"published_at": NOW.isoformat(), "is_read": 0}
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[]
    )
    assert info["parts"]["recency"] == 1.0
    assert info["age_hours"] == 0.0
    # heat = log2(1)/3 = 0 ; source = 1.0*1.0/2.5 = 0.4 ; keyword=0 ; unread=1.0
    expected = _expected_score(1.0, 0.0, 0.4, 0.0, 1.0)
    assert info["score"] == expected


def test_recency_at_age_48_is_half():
    pub = (NOW - timedelta(hours=48)).isoformat()
    art = {"published_at": pub, "is_read": 0}
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[]
    )
    assert info["parts"]["recency"] == 0.5
    assert info["age_hours"] == 48.0
    expected = _expected_score(0.5, 0.0, 0.4, 0.0, 1.0)
    assert info["score"] == expected


def test_recency_at_age_96_is_quarter():
    pub = (NOW - timedelta(hours=96)).isoformat()
    art = {"published_at": pub, "is_read": 1}
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[]
    )
    assert info["parts"]["recency"] == 0.25
    assert info["age_hours"] == 96.0
    # unread=0.0
    expected = _expected_score(0.25, 0.0, 0.4, 0.0, 0.0)
    assert info["score"] == expected


# ---------------- 2. 未来时间 ----------------


def test_future_published_clamps_age_to_zero():
    pub = (NOW + timedelta(hours=10)).isoformat()
    art = {"published_at": pub, "is_read": 0}
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[]
    )
    assert info["age_hours"] == 0.0
    assert info["parts"]["recency"] == 1.0
    expected = _expected_score(1.0, 0.0, 0.4, 0.0, 1.0)
    assert info["score"] == expected


# ---------------- 3. 非法时间 ----------------


def test_invalid_published_falls_back_to_fetched_at():
    fetched = (NOW - timedelta(hours=24)).isoformat()
    art = {"published_at": "not-a-date", "fetched_at": fetched, "is_read": 0}
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[]
    )
    assert info["age_hours"] == 24.0
    assert info["parts"]["recency"] == round(0.5 ** (24 / 48), 4)
    expected = _expected_score(0.5 ** 0.5, 0.0, 0.4, 0.0, 1.0)
    assert info["score"] == expected


def test_both_invalid_times_gives_age_zero():
    art = {"published_at": "not-a-date", "fetched_at": "also-bad", "is_read": 0}
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[]
    )
    assert info["age_hours"] == 0.0
    assert info["parts"]["recency"] == 1.0


# ---------------- 4. 权重边界 ----------------


def test_set_feed_weight_accepts_bounds(tmp_db):
    fid = _mk_feed(tmp_db)
    ranking.set_feed_weight(tmp_db, fid, 0.1)
    ranking.set_feed_weight(tmp_db, fid, 5.0)
    rows = ranking.get_feed_weights(tmp_db)
    assert len(rows) == 1
    assert rows[0]["feed_id"] == fid
    assert rows[0]["weight"] == 5.0


@pytest.mark.parametrize("bad", [0.09, 5.1, "abc", None])
def test_set_feed_weight_rejects_bad_values(tmp_db, bad):
    fid = _mk_feed(tmp_db)
    with pytest.raises(ValueError):
        ranking.set_feed_weight(tmp_db, fid, bad)


def test_set_feed_weight_missing_feed_raises(tmp_db):
    with pytest.raises(ValueError):
        ranking.set_feed_weight(tmp_db, 99999, 1.0)


# ---------------- 5. learned 钳制 ----------------


def test_learn_source_weights_clamps_high_to_max(tmp_db):
    fid = _mk_feed(tmp_db)
    for i in range(4):
        _mk_article(tmp_db, fid, f"g{i}", is_read=1, is_starred=1)
    ranking.learn_source_weights(tmp_db)
    rows = ranking.get_feed_weights(tmp_db)
    assert rows[0]["learned"] == 2.0


def test_learn_source_weights_unread_unstarred_is_one(tmp_db):
    fid = _mk_feed(tmp_db)
    _mk_article(tmp_db, fid, "g0", is_read=0, is_starred=0)
    ranking.learn_source_weights(tmp_db)
    rows = ranking.get_feed_weights(tmp_db)
    # star_rate=0, read_rate=0 -> val=1.0
    assert rows[0]["learned"] == 1.0


# ---------------- 6. 冷启动 ----------------


def test_get_digest_empty_db_returns_empty(tmp_db):
    assert ranking.get_digest(tmp_db, n=10, now=NOW) == []


def test_no_keywords_keyword_component_is_zero():
    art = {
        "published_at": NOW.isoformat(),
        "title": "hello world",
        "content_text": "hello world body",
        "is_read": 0,
    }
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[]
    )
    assert info["parts"]["keyword"] == 0.0


def test_missing_feed_weights_defaults_to_one(tmp_db):
    fid = _mk_feed(tmp_db)
    aid = _mk_article(tmp_db, fid, "g0", published_at=NOW.isoformat())
    art = {
        "id": aid,
        "feed_id": fid,
        "published_at": NOW.isoformat(),
        "is_read": 0,
        "title": "x",
    }
    ranked = ranking.rank_articles(tmp_db, [art], now=NOW)
    assert len(ranked) == 1
    # 无 feed_weights 行时 learned=1.0, weight=1.0 -> source=1.0*1.0/2.5=0.4
    assert ranked[0]["score_info"]["parts"]["source"] == 0.4


# ---------------- 7. 关键词命中 ----------------


def test_keyword_title_boost_doubles_weight():
    art = {
        "published_at": NOW.isoformat(),
        "title": "Python rocks",
        "content_text": "",
        "is_read": 0,
    }
    kws = [{"keyword": "python", "weight": 1.0}]
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=kws
    )
    # hits = 1.0 * 2.0 = 2.0 ; keyword = 2.0/4.0 = 0.5
    assert info["parts"]["keyword"] == 0.5


def test_keyword_body_accumulates_by_weight():
    art = {
        "published_at": NOW.isoformat(),
        "title": "no match here",
        "content_text": "alpha and beta",
        "is_read": 0,
    }
    kws = [
        {"keyword": "alpha", "weight": 1.0},
        {"keyword": "beta", "weight": 0.5},
    ]
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=kws
    )
    # hits = 1.0 + 0.5 = 1.5 ; keyword = 1.5/4.0 = 0.375
    assert info["parts"]["keyword"] == 0.375


def test_keyword_hits_capped_at_four():
    art = {
        "published_at": NOW.isoformat(),
        "title": "a b c d e f",
        "content_text": "",
        "is_read": 0,
    }
    kws = [{"keyword": t, "weight": 1.0} for t in ["a", "b", "c", "d", "e", "f"]]
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=kws
    )
    # 标题命中每个 *2.0，最少 12.0，被截到 KEYWORD_HIT_CAP=4.0 -> keyword=1.0
    assert info["parts"]["keyword"] == 1.0


def test_keyword_case_insensitive():
    art = {
        "published_at": NOW.isoformat(),
        "title": "PYTHON",
        "content_text": "",
        "is_read": 0,
    }
    kws = [{"keyword": "python", "weight": 1.0}]
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=kws
    )
    assert info["parts"]["keyword"] == 0.5


# ---------------- 8. 确定性 ----------------


def test_score_article_deterministic():
    art = {
        "published_at": (NOW - timedelta(hours=10)).isoformat(),
        "title": "Python",
        "content_text": "body python",
        "is_read": 0,
    }
    kws = [{"keyword": "python", "weight": 1.0}]
    a = ranking.score_article(
        art, now=NOW, cluster_size=3, feed_weight=2.0, learned=1.5, keywords=kws
    )
    b = ranking.score_article(
        art, now=NOW, cluster_size=3, feed_weight=2.0, learned=1.5, keywords=kws
    )
    assert a == b
    assert a["score"] == b["score"]


# ---------------- 9. 排序 ----------------


def test_rank_articles_orders_by_score_desc(tmp_db):
    fid = _mk_feed(tmp_db)
    a1 = _mk_article(tmp_db, fid, "a1", published_at=NOW.isoformat(), is_read=1)
    a2 = _mk_article(tmp_db, fid, "a2", published_at=NOW.isoformat(), is_read=0)
    art1 = {
        "id": a1,
        "feed_id": fid,
        "published_at": NOW.isoformat(),
        "is_read": 1,
        "title": "x",
    }
    art2 = {
        "id": a2,
        "feed_id": fid,
        "published_at": NOW.isoformat(),
        "is_read": 0,
        "title": "x",
    }
    ranked = ranking.rank_articles(tmp_db, [art1, art2], now=NOW)
    assert ranked[0]["id"] == a2
    assert ranked[0]["score_info"]["score"] > ranked[1]["score_info"]["score"]


def test_rank_articles_tie_broken_by_published_desc(tmp_db):
    fid = _mk_feed(tmp_db)
    older = (NOW - timedelta(hours=24)).isoformat()
    newer = (NOW - timedelta(hours=1)).isoformat()
    a_old = _mk_article(tmp_db, fid, "g-old", published_at=older, is_read=0)
    a_new = _mk_article(tmp_db, fid, "g-new", published_at=newer, is_read=0)
    art_old = {
        "id": a_old,
        "feed_id": fid,
        "published_at": older,
        "is_read": 0,
        "title": "same",
    }
    art_new = {
        "id": a_new,
        "feed_id": fid,
        "published_at": newer,
        "is_read": 0,
        "title": "same",
    }
    ranked = ranking.rank_articles(tmp_db, [art_old, art_new], now=NOW)
    assert ranked[0]["id"] == a_new
    assert ranked[1]["id"] == a_old


# ---------------- 10. reasons ----------------


def test_reasons_include_publish_when_recency_high():
    art = {"published_at": NOW.isoformat(), "is_read": 0}
    info = ranking.score_article(
        art, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[]
    )
    assert info["parts"]["recency"] >= 0.5
    assert any("发布" in r for r in info["reasons"])


def test_reasons_include_cluster_when_size_ge_two():
    art = {"published_at": NOW.isoformat(), "is_read": 0}
    info = ranking.score_article(
        art, now=NOW, cluster_size=2, feed_weight=1.0, learned=1.0, keywords=[]
    )
    assert any("同事件" in r for r in info["reasons"])
