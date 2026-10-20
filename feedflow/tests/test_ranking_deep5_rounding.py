import math
from datetime import UTC, datetime, timedelta

from feedflow.ranking import (
    KEYWORD_HIT_CAP,
    RECENCY_HALFLIFE_HOURS,
    SOURCE_NORM,
    WEIGHTS,
    score_article,
)


def _make_article(published_at, cluster_size=3, is_read=0, title="hello", content_text=""):
    return {
        "id": 1,
        "feed_id": 1,
        "guid": "g1",
        "title": title,
        "author": "",
        "link": "",
        "summary": "",
        "content_html": "",
        "content_text": content_text,
        "published_at": published_at,
        "fetched_at": published_at,
        "is_read": is_read,
        "is_starred": 0,
        "cluster_id": None,
    }


def test_score_rounds_to_4():
    now = datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC)
    published = (now - timedelta(hours=1)).isoformat()
    article = _make_article(published_at=published, cluster_size=3, is_read=0)

    info = score_article(
        article,
        now=now,
        cluster_size=3,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )

    recency = 0.5 ** (1 / RECENCY_HALFLIFE_HOURS)
    heat = math.log2(3) / 3.0
    source = 1.0 / SOURCE_NORM
    keyword = 0.0
    unread = 1.0

    expected = round(
        WEIGHTS["recency"] * recency
        + WEIGHTS["heat"] * heat
        + WEIGHTS["source"] * source
        + WEIGHTS["keyword"] * keyword
        + WEIGHTS["unread"] * unread,
        4,
    )

    assert info["score"] == expected


def test_parts_rounded():
    now = datetime(2025, 3, 4, 9, 30, 0, tzinfo=UTC)
    published = (now - timedelta(hours=5)).isoformat()
    article = _make_article(
        published_at=published,
        cluster_size=4,
        is_read=0,
        title="python testing",
        content_text="python pytest coverage",
    )

    keywords = [{"keyword": "python", "weight": 1.0}]

    info = score_article(
        article,
        now=now,
        cluster_size=4,
        feed_weight=1.5,
        learned=1.2,
        keywords=keywords,
    )

    parts = info["parts"]
    for k, v in parts.items():
        assert v == round(v, 4)

    score = info["score"]
    assert score == round(score, 4)
    assert str(score)[::-1].find(".") <= 4
