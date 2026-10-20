import pytest
from datetime import UTC, datetime, timedelta
from feedflow.ranking import score_article


def _article(published_at, fetched_at=None):
    return {
        "title": "t",
        "is_read": 0,
        "published_at": published_at,
        "fetched_at": fetched_at,
    }


def test_recency_now_is_one():
    now = datetime.now(UTC)
    article = _article(now.isoformat())
    parts = score_article(
        article,
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )["parts"]
    assert parts["recency"] == 1.0


def test_recency_old_rounds_to_zero():
    now = datetime.now(UTC)
    article = _article((now - timedelta(hours=8760)).isoformat())
    parts = score_article(
        article,
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )["parts"]
    assert parts["recency"] == 0.0
    assert 0.5 ** (8760 / 48) > 0


def test_recency_future_clamped():
    now = datetime.now(UTC)
    article = _article((now + timedelta(hours=5)).isoformat())
    parts = score_article(
        article,
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )["parts"]
    assert parts["recency"] == 1.0


def test_recency_no_time_is_one():
    now = datetime.now(UTC)
    article = _article(None, None)
    parts = score_article(
        article,
        now=now,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )["parts"]
    assert parts["recency"] == 1.0
