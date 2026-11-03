from datetime import UTC, datetime

from feedflow.ranking import (
    KEYWORD_HIT_CAP,
    add_keyword,
    score_article,
)


def test_hits_capped(tmp_db):
    add_keyword(tmp_db, "k1")
    add_keyword(tmp_db, "k2")
    add_keyword(tmp_db, "k3")

    keywords = [
        {"keyword": "k1", "weight": 1.0},
        {"keyword": "k2", "weight": 1.0},
        {"keyword": "k3", "weight": 1.0},
    ]

    article = {
        "title": "k1 k2 k3",
        "content_text": "",
        "summary": "",
        "is_read": 0,
        "published_at": None,
        "fetched_at": None,
    }

    info = score_article(
        article,
        now=datetime.now(UTC),
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=keywords,
    )

    assert KEYWORD_HIT_CAP == 4.0
    assert info["parts"]["keyword"] == 1.0


def test_reasons_top_two(tmp_db):
    add_keyword(tmp_db, "k1")
    add_keyword(tmp_db, "k2")
    add_keyword(tmp_db, "k3")

    keywords = [
        {"keyword": "k1", "weight": 1.0},
        {"keyword": "k2", "weight": 1.0},
        {"keyword": "k3", "weight": 1.0},
    ]

    article = {
        "title": "k1 k2 k3",
        "content_text": "",
        "summary": "",
        "is_read": 0,
        "published_at": None,
        "fetched_at": None,
    }

    info = score_article(
        article,
        now=datetime.now(UTC),
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=keywords,
    )

    assert "命中关键词「k1」「k2」" in info["reasons"]
    assert all("k3" not in reason for reason in info["reasons"])
