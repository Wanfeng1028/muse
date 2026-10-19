from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from feedflow import db, ranking, store


@pytest.fixture()
def tmp_db(tmp_path):
    path = str(tmp_path / "rank_deep3.db")
    db.init_db(path)
    return path


def _make_feed(db_path, title="f", url="http://f/x/"):
    db.execute_write(
        db_path,
        "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, 0, ?)",
        (title, url, db.utcnow()),
    )
    row = db.query_one(db_path, "SELECT id FROM feeds WHERE feed_url = ?", (url,))
    return int(row["id"])


def _make_article(db_path, feed_id, guid="g1", title="t", summary="", content_text=""):
    store.insert_article(
        db_path,
        feed_id,
        guid,
        title,
        "a",
        "http://x/",
        summary,
        "",
        content_text,
        db.utcnow(),
    )
    row = db.query_one(db_path, "SELECT id FROM articles WHERE guid = ?", (guid,))
    return int(row["id"])


def test_add_keyword_duplicate_case_insensitive_returns_same_id(tmp_db):
    first = ranking.add_keyword(tmp_db, "AI")
    second = ranking.add_keyword(tmp_db, "ai")
    assert first == second
    kws = ranking.get_keywords(tmp_db)
    assert len(kws) == 1
    assert kws[0]["keyword"] == "AI"


def test_add_keyword_none_raises(tmp_db):
    with pytest.raises(ValueError):
        ranking.add_keyword(tmp_db, None)


def test_delete_keyword_missing_false(tmp_db):
    assert ranking.delete_keyword(tmp_db, 12345) is False


def test_set_feed_weight_nonexistent_feed_raises(tmp_db):
    with pytest.raises(ValueError):
        ranking.set_feed_weight(tmp_db, 999999, 1.0)


def test_set_feed_weight_invalid_values_raise(tmp_db):
    fid = _make_feed(tmp_db)
    for bad in ("abc", None, []):
        with pytest.raises(ValueError):
            ranking.set_feed_weight(tmp_db, fid, bad)
    with pytest.raises(ValueError):
        ranking.set_feed_weight(tmp_db, fid, 0.05)
    with pytest.raises(ValueError):
        ranking.set_feed_weight(tmp_db, fid, 5.5)
    ranking.set_feed_weight(tmp_db, fid, 0.1)
    ranking.set_feed_weight(tmp_db, fid, 5.0)


def test_set_feed_weight_preserves_learned(tmp_db):
    fid = _make_feed(tmp_db)
    _make_article(tmp_db, fid, guid="g1", title="a")
    _make_article(tmp_db, fid, guid="g2", title="b")
    db.execute_write(tmp_db, "UPDATE articles SET is_starred = 1 WHERE feed_id = ?", (fid,))
    ranking.learn_source_weights(tmp_db)
    rows = ranking.get_feed_weights(tmp_db)
    assert rows[0]["learned"] == 2.0
    ranking.set_feed_weight(tmp_db, fid, 3.0)
    rows = ranking.get_feed_weights(tmp_db)
    assert rows[0]["weight"] == 3.0
    assert rows[0]["learned"] == 2.0


def test_get_feed_weights_defaults(tmp_db):
    fid = _make_feed(tmp_db)
    rows = ranking.get_feed_weights(tmp_db)
    assert len(rows) == 1
    assert rows[0]["feed_id"] == fid
    assert rows[0]["weight"] == 1.0
    assert rows[0]["learned"] == 1.0


def test_setting_upsert_and_str_coercion(tmp_db):
    ranking.set_setting(tmp_db, "k", 123)
    assert ranking.get_setting(tmp_db, "k") == "123"
    ranking.set_setting(tmp_db, "k", "overwritten")
    assert ranking.get_setting(tmp_db, "k") == "overwritten"


def test_get_digest_n_malformed_and_padded(tmp_db):
    ranking.set_setting(tmp_db, "digest_n", "abc")
    assert ranking.get_digest_n(tmp_db) == 20
    ranking.set_setting(tmp_db, "digest_n", " 15 ")
    assert ranking.get_digest_n(tmp_db) == 15


def test_learn_source_weights_no_articles_no_rows(tmp_db):
    _make_feed(tmp_db)
    ranking.learn_source_weights(tmp_db)
    rows = db.query_all(tmp_db, "SELECT * FROM feed_weights")
    assert rows == []


def test_learn_source_weights_all_starred_clamps(tmp_db):
    fid = _make_feed(tmp_db)
    _make_article(tmp_db, fid, guid="g1", title="a")
    _make_article(tmp_db, fid, guid="g2", title="b")
    db.execute_write(tmp_db, "UPDATE articles SET is_starred = 1 WHERE feed_id = ?", (fid,))
    ranking.learn_source_weights(tmp_db)
    rows = ranking.get_feed_weights(tmp_db)
    assert rows[0]["learned"] == 2.0


def test_learn_source_weights_half_read(tmp_db):
    fid = _make_feed(tmp_db)
    _make_article(tmp_db, fid, guid="g1", title="a")
    _make_article(tmp_db, fid, guid="g2", title="b")
    db.execute_write(tmp_db, "UPDATE articles SET is_read = 1 WHERE guid = 'g1'")
    ranking.learn_source_weights(tmp_db)
    rows = ranking.get_feed_weights(tmp_db)
    assert rows[0]["learned"] == 1.15


def test_score_article_title_boost_vs_body(tmp_db):
    now = datetime.now(UTC)
    kw = [{"keyword": "rust", "weight": 1.0}]
    title_hit = ranking.score_article(
        {"title": "Rust is great", "summary": "x", "is_read": 0},
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=kw,
    )
    assert title_hit["parts"]["keyword"] == 0.5
    body_hit = ranking.score_article(
        {"title": "other", "summary": "rust everywhere", "is_read": 0},
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=kw,
    )
    assert body_hit["parts"]["keyword"] == 0.25


def test_score_article_hit_cap(tmp_db):
    now = datetime.now(UTC)
    keywords = [{"keyword": f"k{i}", "weight": 1.0} for i in range(5)]
    title = " ".join(f"k{i}" for i in range(5))
    info = ranking.score_article(
        {"title": title, "summary": "", "is_read": 0},
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=keywords,
    )
    assert info["parts"]["keyword"] == 1.0


def test_score_article_kw_invalid_weight_falls_back(tmp_db):
    now = datetime.now(UTC)
    info = ranking.score_article(
        {"title": "x here", "summary": "", "is_read": 0},
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[{"keyword": "x", "weight": "bad"}],
    )
    assert info["parts"]["keyword"] == 0.5


def test_score_article_cluster_size_zero_treated_as_1(tmp_db):
    now = datetime.now(UTC)
    info = ranking.score_article(
        {"title": "t", "summary": "", "is_read": 0},
        now=now,
        cluster_size=0,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )
    assert info["cluster_size"] == 1
    assert info["parts"]["heat"] == 0.0


def test_score_article_reasons_top2_keywords(tmp_db):
    now = datetime.now(UTC)
    keywords = [
        {"keyword": "aa", "weight": 1.0},
        {"keyword": "bb", "weight": 1.0},
        {"keyword": "cc", "weight": 1.0},
    ]
    info = ranking.score_article(
        {"title": "aa bb cc", "summary": "", "is_read": 0},
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=keywords,
    )
    kw_reasons = [r for r in info["reasons"] if r.startswith("命中关键词")]
    assert len(kw_reasons) == 1
    assert "aa" in kw_reasons[0]
    assert "bb" in kw_reasons[0]
    assert "cc" not in kw_reasons[0]


def test_score_article_read_unread_zero(tmp_db):
    now = datetime.now(UTC)
    common = {
        "title": "t",
        "summary": "",
        "published_at": (now - timedelta(hours=1)).isoformat(),
    }
    unread_info = ranking.score_article(
        {**common, "is_read": 0},
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )
    read_info = ranking.score_article(
        {**common, "is_read": 1},
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )
    assert read_info["parts"]["unread"] == 0.0
    assert unread_info["parts"]["unread"] == 1.0
    assert read_info["score"] < unread_info["score"]


def test_parse_iso_bad_and_naive():
    assert ranking._parse_iso("not-a-date") is None
    parsed = ranking._parse_iso("2026-01-01T00:00:00")
    assert parsed is not None
    assert parsed.tzinfo == UTC


def test_age_hours_future_zero_and_prefers_published(tmp_db):
    now = datetime.now(UTC)
    future = (now + timedelta(hours=5)).isoformat()
    assert ranking._age_hours(future, None, now) == 0.0
    published = (now - timedelta(hours=10)).isoformat()
    fetched = (now - timedelta(hours=1)).isoformat()
    age = ranking._age_hours(published, fetched, now)
    assert 9.9 < age < 10.1


def test_get_digest_excludes_read_and_n_zero(tmp_db):
    fid = _make_feed(tmp_db)
    _make_article(tmp_db, fid, guid="g1", title="unread one")
    _make_article(tmp_db, fid, guid="g2", title="read one")
    db.execute_write(tmp_db, "UPDATE articles SET is_read = 1 WHERE guid = 'g2'")
    digest = ranking.get_digest(tmp_db, n=10)
    guids = [a["guid"] for a in digest]
    assert "g1" in guids
    assert "g2" not in guids
    assert ranking.get_digest(tmp_db, n=0) == []


def test_rank_articles_unknown_feed_defaults(tmp_db):
    art = {
        "id": 1,
        "feed_id": 999999,
        "title": "orphan",
        "summary": "",
        "is_read": 0,
        "published_at": None,
        "cluster_id": None,
    }
    ranked = ranking.rank_articles(tmp_db, [art])
    assert len(ranked) == 1
    info = ranked[0]["score_info"]
    assert "parts" in info
    for key in ("recency", "heat", "source", "keyword", "unread"):
        assert key in info["parts"]