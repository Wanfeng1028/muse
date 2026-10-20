import pytest

from feedflow.ranking import score_article


def _article():
    return {
        "title": "hello",
        "summary": "",
        "content_text": "",
        "published_at": None,
        "fetched_at": None,
        "is_read": 0,
    }


def test_source_high():
    info = score_article(
        _article(),
        now=None,
        cluster_size=1,
        feed_weight=5.0,
        learned=2.0,
        keywords=[],
    )
    assert info["parts"]["source"] == 1.0
    assert "这个源你常看" in info["reasons"]


def test_source_low():
    info = score_article(
        _article(),
        now=None,
        cluster_size=1,
        feed_weight=0.1,
        learned=0.5,
        keywords=[],
    )
    assert info["parts"]["source"] == 0.02
    assert "这个源平时看得少" in info["reasons"]


def test_source_neutral():
    info = score_article(
        _article(),
        now=None,
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )
    assert info["parts"]["source"] == 0.4
    assert "这个源你常看" not in info["reasons"]
    assert "这个源平时看得少" not in info["reasons"]


def test_source_reason_boundaries():
    high = score_article(
        _article(),
        now=None,
        cluster_size=1,
        feed_weight=1.5,
        learned=1.0,
        keywords=[],
    )
    assert "这个源你常看" in high["reasons"]

    low = score_article(
        _article(),
        now=None,
        cluster_size=1,
        feed_weight=0.7,
        learned=1.0,
        keywords=[],
    )
    assert "这个源平时看得少" in low["reasons"]
