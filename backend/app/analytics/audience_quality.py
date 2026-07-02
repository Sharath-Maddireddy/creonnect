"""Audience quality heuristics."""

from __future__ import annotations


def calculate_authenticity_score(
    follower_count: int,
    avg_views: int,
    avg_likes: int,
    avg_comments: int,
) -> float:
    """Estimate audience authenticity as a 0-100 score.

    This function always returns values on a 0-100 scale. Brand campaign matching
    assumes this same scale when converting authenticity-like signals into
    `engagement_quality` points.
    """
    if follower_count == 0:
        return 0.0

    score = 100.0

    if (avg_likes / follower_count) < 0.005:
        score -= 30.0

    if (avg_comments / follower_count) < 0.0001:
        score -= 20.0

    if avg_views > 0 and (avg_likes / avg_views) > 0.40:
        score -= 40.0

    return max(0.0, min(100.0, score))
