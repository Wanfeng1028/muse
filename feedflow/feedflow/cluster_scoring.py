"""Cluster importance scoring for RSS feed clusters.

This module provides a pure function to compute the importance score of an
article cluster based on the representative article's score, cluster size,
source diversity, unread count, and recency.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone


def cluster_importance_score(
    rep_score: float,
    members: int | None,
    sources: int | None,
    unread: int | None,
    latest_at: str | None,
    now: datetime | None = None,
) -> float:
    """Compute the importance score for an article cluster.

    Args:
        rep_score: Raw score of the representative article. Must be >= 0.
        members: Total number of articles in the cluster. None is treated as 0.
        sources: Number of distinct sources in the cluster. None is treated as 0.
        unread: Number of unread articles in the cluster. None is treated as 0.
        latest_at: ISO 8601 timestamp of the newest article in the cluster.
            Empty string or unparseable values result in a default recency factor.
        now: Current time. If None, uses current UTC time.

    Returns:
        The computed importance score as a float.
    """
    # Clamp rep_score
    try:
        rep_score = float(rep_score)
    except (TypeError, ValueError):
        rep_score = 0.0
    if rep_score < 0:
        rep_score = 0.0

    # Helper to clamp non-negative integers
    def _clamp_non_negative_int(value: int | None) -> int:
        if value is None:
            return 0
        try:
            value = int(value)
        except (TypeError, ValueError):
            return 0
        if value < 0:
            return 0
        return value

    members = _clamp_non_negative_int(members)
    sources = _clamp_non_negative_int(sources)
    unread = _clamp_non_negative_int(unread)

    # Determine current time
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # Determine recency factor
    recency_factor = 0.75
    if latest_at:
        try:
            latest_dt = datetime.fromisoformat(latest_at)
            if latest_dt.tzinfo is None:
                latest_dt = latest_dt.replace(tzinfo=timezone.utc)
            age_hours = (now - latest_dt).total_seconds() / 3600.0
            recency_factor = 0.5 + 0.5 * math.exp(-age_hours / 72.0)
        except (ValueError, TypeError):
            recency_factor = 0.75

    # Compute importance
    base_multiplier = (
        1.0
        + 0.25 * math.log10(1 + members)
        + 0.35 * math.log10(1 + sources)
        + 0.15 * math.log10(1 + unread)
    )
    importance = rep_score * base_multiplier * recency_factor

    return importance
