import math
from datetime import datetime

from feedflow.cluster_scoring import cluster_importance_score


def test_deterministic_same_args():
    now = datetime(2024, 1, 1)
    latest_at = "2023-12-31T00:00:00"
    args = (1.5, 10, 5, 2, latest_at)
    kwargs = {"now": now}
    r1 = cluster_importance_score(*args, **kwargs)
    r2 = cluster_importance_score(*args, **kwargs)
    assert r1 == r2


def test_members_monotonic_increasing():
    now = datetime(2024, 1, 1)
    latest_at = "2023-12-31T00:00:00"
    score_low = cluster_importance_score(1.0, 1, 5, 2, latest_at, now=now)
    score_high = cluster_importance_score(1.0, 10, 5, 2, latest_at, now=now)
    assert score_high > score_low


def test_sources_monotonic_increasing():
    now = datetime(2024, 1, 1)
    latest_at = "2023-12-31T00:00:00"
    score_low = cluster_importance_score(1.0, 10, 1, 2, latest_at, now=now)
    score_high = cluster_importance_score(1.0, 10, 5, 2, latest_at, now=now)
    assert score_high > score_low


def test_latest_at_recency_and_empty_string():
    now = datetime(2024, 1, 10)
    recent = "2024-01-09T00:00:00"
    old = "2024-01-01T00:00:00"
    score_recent = cluster_importance_score(1.0, 10, 5, 2, recent, now=now)
    score_old = cluster_importance_score(1.0, 10, 5, 2, old, now=now)
    assert score_recent > score_old

    rep_score = 2.0
    members = 10
    sources = 5
    unread = 3
    expected = (
        rep_score
        * (
            1
            + 0.25 * math.log10(1 + members)
            + 0.35 * math.log10(1 + sources)
            + 0.15 * math.log10(1 + unread)
        )
        * 0.75
    )
    actual = cluster_importance_score(
        rep_score, members, sources, unread, "", now=now
    )
    assert math.isclose(actual, expected, rel_tol=1e-9)


def test_members_none_or_negative_finite():
    now = datetime(2024, 1, 1)
    latest_at = "2023-12-31T00:00:00"
    r_none = cluster_importance_score(1.0, None, 5, 2, latest_at, now=now)
    assert math.isfinite(r_none)
    r_neg = cluster_importance_score(1.0, -5, 5, 2, latest_at, now=now)
    assert math.isfinite(r_neg)


def test_solo_lower_than_cluster():
    now = datetime(2024, 1, 1)
    latest_at = "2023-12-31T00:00:00"
    solo = cluster_importance_score(1.0, 1, 1, 2, latest_at, now=now)
    cluster = cluster_importance_score(1.0, 5, 3, 2, latest_at, now=now)
    assert solo < cluster
