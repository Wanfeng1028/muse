import math

from feedflow.ranking import score_article


def _call_score(cluster_size):
    article = {
        "title": "t",
        "content_text": "",
        "summary": "",
        "is_read": 0,
        "published_at": None,
        "fetched_at": None,
    }
    return score_article(
        article,
        now=None,
        cluster_size=cluster_size,
        feed_weight=1.0,
        learned=1.0,
        keywords=[],
    )


def test_heat_single_zero():
    info = _call_score(1)
    assert info["parts"]["heat"] == 0.0


def test_heat_two():
    info = _call_score(2)
    assert info["parts"]["heat"] == round(math.log2(2) / 3.0, 4)


def test_heat_eight_full():
    info = _call_score(8)
    assert info["parts"]["heat"] == 1.0


def test_heat_zero_and_cap():
    info_zero = _call_score(0)
    assert info_zero["parts"]["heat"] == 0.0
    info_cap = _call_score(64)
    assert info_cap["parts"]["heat"] == 1.0
