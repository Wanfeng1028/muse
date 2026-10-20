import pytest

from feedflow import db
from feedflow.ranking import rank_articles


def _make_art(art_id, title, published_at):
    return {
        "id": art_id,
        "title": title,
        "published_at": published_at,
        "fetched_at": published_at,
        "is_read": 0,
        "feed_id": None,
        "cluster_id": None,
    }


def test_cold_start_deterministic(tmp_db):
    arts = [
        _make_art(1, "alpha", "2024-01-01T00:00:00+00:00"),
        _make_art(2, "beta", "2024-01-01T00:00:00+00:00"),
    ]
    r1 = rank_articles(tmp_db, arts)
    r2 = rank_articles(tmp_db, arts)
    assert [a["id"] for a in r1] == [a["id"] for a in r2]


def test_cold_start_no_feed_weights(tmp_db):
    arts = [
        _make_art(1, "alpha", "2024-01-01T00:00:00+00:00"),
        _make_art(2, "beta", "2024-01-01T00:00:00+00:00"),
    ]
    rank_articles(tmp_db, arts)
    rows = db.query_all(tmp_db, "SELECT * FROM feed_weights")
    assert rows == []


def test_cold_start_keyword_zero(tmp_db):
    arts = [
        _make_art(1, "alpha", "2024-01-01T00:00:00+00:00"),
        _make_art(2, "beta", "2024-01-01T00:00:00+00:00"),
    ]
    ranked = rank_articles(tmp_db, arts)
    for art in ranked:
        assert art["score_info"]["parts"]["keyword"] == 0.0
