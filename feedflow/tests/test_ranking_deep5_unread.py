from datetime import UTC, datetime

from feedflow.ranking import score_article


def _make_article(is_read):
    return {
        "title": "",
        "content_text": "",
        "summary": "",
        "published_at": None,
        "fetched_at": None,
        "is_read": is_read,
    }


def _score(article, now):
    return score_article(
        article,
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )


def test_unread_parts():
    now = datetime(2024, 1, 1, tzinfo=UTC)
    unread_info = _score(_make_article(0), now)
    read_info = _score(_make_article(1), now)
    assert unread_info["parts"]["unread"] == 1.0
    assert read_info["parts"]["unread"] == 0.0


def test_unread_score_gap():
    now = datetime(2024, 1, 1, tzinfo=UTC)
    unread_info = _score(_make_article(0), now)
    read_info = _score(_make_article(1), now)
    gap = unread_info["score"] - read_info["score"]
    assert abs(gap - 0.1) < 1e-9


def test_unread_nonzero_is_read():
    now = datetime(2024, 1, 1, tzinfo=UTC)
    info = _score(_make_article(2), now)
    assert info["parts"]["unread"] == 0.0
