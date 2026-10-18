from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from feedflow import db, ranking, store


def _insert_feed(db_path, title="f", url="http://f/x/"):
    return db.execute_write(
        db_path,
        "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, 0, ?)",
        (title, url, db.utcnow()),
    )


def _insert_article(
    db_path,
    feed_id,
    guid,
    title="t",
    summary="s",
    content_text="",
    published_at=None,
    is_read=0,
):
    aid = store.insert_article(
        db_path,
        feed_id,
        guid,
        title,
        "author",
        "http://f/x/a",
        summary,
        "",
        content_text,
        published_at,
    )
    if is_read:
        db.execute_write(
            db_path, "UPDATE articles SET is_read = 1 WHERE id = ?", (int(aid),)
        )
    return aid


def test_score_article_exact_parts_and_score():
    now = datetime.now(UTC)
    published_at = (now - timedelta(hours=48)).isoformat()
    article = {
        "id": 1,
        "title": "Latest AI news",
        "content_text": "",
        "summary": "",
        "published_at": published_at,
        "fetched_at": None,
        "is_read": 1,
    }
    info = ranking.score_article(
        article,
        now=now,
        cluster_size=8,
        feed_weight=1.25,
        learned=2.0,
        keywords=[{"keyword": "ai", "weight": 2.0}],
    )
    parts = info["parts"]
    assert parts["recency"] == pytest.approx(0.5, abs=1e-9)
    assert parts["heat"] == pytest.approx(1.0, abs=1e-9)
    assert parts["source"] == pytest.approx(1.0, abs=1e-9)
    assert parts["keyword"] == pytest.approx(1.0, abs=1e-9)
    assert parts["unread"] == pytest.approx(0.0, abs=1e-9)

    expected = round(
        0.30 * 0.5 + 0.25 * 1.0 + 0.20 * 1.0 + 0.15 * 1.0 + 0.10 * 0.0, 4
    )
    assert info["score"] == pytest.approx(0.75, abs=1e-9)
    assert info["score"] == expected


def test_rank_articles_tie_break_by_id_desc(tmp_db):
    feed_id = _insert_feed(tmp_db)
    now = datetime.now(UTC)
    published_at = (now - timedelta(hours=48)).isoformat()
    a_id = _insert_article(
        tmp_db, feed_id, "g-a", title="same", published_at=published_at, is_read=0
    )
    b_id = _insert_article(
        tmp_db, feed_id, "g-b", title="same", published_at=published_at, is_read=0
    )
    assert a_id != b_id

    articles = [
        {
            "id": a_id,
            "feed_id": feed_id,
            "title": "same",
            "published_at": published_at,
            "fetched_at": None,
            "is_read": 0,
            "content_text": "",
            "summary": "",
        },
        {
            "id": b_id,
            "feed_id": feed_id,
            "title": "same",
            "published_at": published_at,
            "fetched_at": None,
            "is_read": 0,
            "content_text": "",
            "summary": "",
        },
    ]

    ranked = ranking.rank_articles(tmp_db, articles, now=now)
    ids = [r["id"] for r in ranked]
    assert ids == sorted(ids, reverse=True)
    assert ids[0] == max(a_id, b_id)


def test_rank_articles_null_published_at_sorts_last(tmp_db):
    feed_id = _insert_feed(tmp_db)
    now = datetime.now(UTC)
    published_at = (now - timedelta(hours=48)).isoformat()

    a_id = _insert_article(
        tmp_db, feed_id, "g-a", title="same", published_at=published_at, is_read=0
    )
    b_id = _insert_article(
        tmp_db, feed_id, "g-b", title="same", published_at=None, is_read=0
    )
    fetched_iso = (now - timedelta(hours=48)).isoformat()
    db.execute_write(
        tmp_db,
        "UPDATE articles SET fetched_at = ? WHERE id = ?",
        (fetched_iso, int(b_id)),
    )

    articles = [
        {
            "id": a_id,
            "feed_id": feed_id,
            "title": "same",
            "published_at": published_at,
            "fetched_at": None,
            "is_read": 0,
            "content_text": "",
            "summary": "",
        },
        {
            "id": b_id,
            "feed_id": feed_id,
            "title": "same",
            "published_at": None,
            "fetched_at": fetched_iso,
            "is_read": 0,
            "content_text": "",
            "summary": "",
        },
    ]

    ranked = ranking.rank_articles(tmp_db, articles, now=now)
    assert ranked[0]["score_info"]["score"] == pytest.approx(
        ranked[1]["score_info"]["score"], abs=1e-9
    )
    assert ranked[0]["id"] == a_id
    assert ranked[1]["id"] == b_id


def test_get_digest_n_none_defaults_to_20(tmp_db):
    feed_id = _insert_feed(tmp_db)
    now = datetime.now(UTC)
    published_at = (now - timedelta(hours=1)).isoformat()
    for i in range(3):
        _insert_article(
            tmp_db,
            feed_id,
            f"g-{i}",
            title=f"t{i}",
            published_at=published_at,
            is_read=0,
        )
    result = ranking.get_digest(tmp_db, n=None, now=now)
    assert len(result) == 3


def test_get_digest_n_zero_and_negative(tmp_db):
    feed_id = _insert_feed(tmp_db)
    now = datetime.now(UTC)
    published_at = (now - timedelta(hours=1)).isoformat()
    _insert_article(tmp_db, feed_id, "g-0", title="t0", published_at=published_at, is_read=0)

    assert ranking.get_digest(tmp_db, n=0, now=now) == []
    assert ranking.get_digest(tmp_db, n=-5, now=now) == []


def test_format_age_boundaries():
    assert ranking._format_age(0.0) == "刚刚"
    assert ranking._format_age(0.5) == "30 分钟前"
    assert ranking._format_age(47.9) == "47 小时前"
    assert ranking._format_age(48.0) == "2 天前"


def test_add_keyword_whitespace_only_raises(tmp_db):
    with pytest.raises(ValueError):
        ranking.add_keyword(tmp_db, "   ")


def test_rank_articles_deterministic(tmp_db):
    feed_id = _insert_feed(tmp_db)
    now = datetime.now(UTC)
    articles = []
    for i in range(4):
        published_at = (now - timedelta(hours=i + 1)).isoformat()
        aid = _insert_article(
            tmp_db,
            feed_id,
            f"g-{i}",
            title=f"t{i}",
            published_at=published_at,
            is_read=0,
        )
        articles.append(
            {
                "id": aid,
                "feed_id": feed_id,
                "title": f"t{i}",
                "published_at": published_at,
                "fetched_at": None,
                "is_read": 0,
                "content_text": "",
                "summary": "",
            }
        )

    first = ranking.rank_articles(tmp_db, articles, now=now)
    second = ranking.rank_articles(tmp_db, articles, now=now)
    assert [r["id"] for r in first] == [r["id"] for r in second]


def test_rank_articles_empty_list(tmp_db):
    assert ranking.rank_articles(tmp_db, [], now=datetime.now(UTC)) == []


def test_learn_source_weights_clamped_to_max(tmp_db):
    feed_id = _insert_feed(tmp_db)
    now = datetime.now(UTC)
    published_at = (now - timedelta(hours=1)).isoformat()
    ids = []
    for i in range(3):
        aid = _insert_article(
            tmp_db,
            feed_id,
            f"g-{i}",
            title=f"t{i}",
            published_at=published_at,
            is_read=0,
        )
        ids.append(aid)
    for aid in ids:
        db.execute_write(
            tmp_db,
            "UPDATE articles SET is_read = 1, is_starred = 1 WHERE id = ?",
            (int(aid),),
        )

    ranking.learn_source_weights(tmp_db)

    row = db.query_one(
        tmp_db,
        "SELECT learned FROM feed_weights WHERE feed_id = ?",
        (int(feed_id),),
    )
    assert row is not None
    assert float(row["learned"]) == pytest.approx(ranking.LEARNED_MAX, abs=1e-9)
    assert ranking.LEARNED_MAX == 2.0


def test_reasons_source_frequently_read_and_rarely_read():
    now = datetime.now(UTC)
    article = {
        "id": 1,
        "title": "plain",
        "content_text": "",
        "summary": "",
        "published_at": (now - timedelta(hours=1)).isoformat(),
        "fetched_at": None,
        "is_read": 0,
    }

    info_high = ranking.score_article(
        article,
        now=now,
        cluster_size=1,
        feed_weight=2.0,
        learned=1.0,
        keywords=[],
    )
    assert "这个源你常看" in info_high["reasons"]

    info_low = ranking.score_article(
        article,
        now=now,
        cluster_size=1,
        feed_weight=0.1,
        learned=1.0,
        keywords=[],
    )
    assert "这个源平时看得少" in info_low["reasons"]