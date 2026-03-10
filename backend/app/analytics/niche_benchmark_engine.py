"""Deterministic niche benchmark context utilities for premium-tier users."""

from __future__ import annotations

from typing import TypedDict

from backend.app.domain.post_models import SinglePostInsights


class NicheBenchmarkContext(TypedDict):
    """Structured niche benchmark context payload."""

    category: str | None
    follower_band: str | None
    avg_engagement_rate: float | None
    avg_save_rate: float | None
    post_engagement_rate: float | None
    post_save_rate: float | None
    commentary: str


def _resolve_follower_band(follower_count: int | None) -> str | None:
    """Map follower count into a deterministic follower band."""
    if follower_count is None or follower_count < 0:
        return None
    if follower_count < 10_000:
        return "0-10k"
    if follower_count < 100_000:
        return "10k-100k"
    if follower_count < 1_000_000:
        return "100k-1M"
    return "1M+"


def _build_commentary(
    post_engagement_rate: float | None,
    niche_avg_engagement_rate: float | None,
    post_save_rate: float | None,
    niche_avg_save_rate: float | None,
) -> str:
    """Build deterministic commentary from engagement and save-rate comparisons."""

    engagement_comparable = (
        post_engagement_rate is not None
        and niche_avg_engagement_rate is not None
    )

    save_comparable = (
        post_save_rate is not None
        and niche_avg_save_rate is not None
    )

    if not engagement_comparable and not save_comparable:
        return "Insufficient data to compare this post against niche benchmarks."

    engagement_above = (
        engagement_comparable
        and post_engagement_rate > niche_avg_engagement_rate
    )
    engagement_below = (
        engagement_comparable
        and post_engagement_rate < niche_avg_engagement_rate
    )

    save_above = (
        save_comparable
        and post_save_rate > niche_avg_save_rate
    )
    save_below = (
        save_comparable
        and post_save_rate < niche_avg_save_rate
    )

    if engagement_above and save_above:
        return "This post is strongly outperforming niche averages on engagement and saves."

    if engagement_below and save_above:
        return "Mixed signal: engagement is below niche average, but save rate is above niche average."

    if engagement_above and save_below:
        return "Mixed signal: engagement is above niche average, but save rate is below niche average."

    if engagement_below and save_below:
        return "This post is underperforming versus niche averages for both engagement and saves."

    if engagement_above and not save_comparable:
        return "Engagement is above niche average."

    if engagement_below and not save_comparable:
        return "Engagement is below niche average."

    if save_above and not engagement_comparable:
        return "Save rate is above niche average."

    if save_below and not engagement_comparable:
        return "Save rate is below niche average."

    return "This post is performing in line with niche benchmark expectations."


def compute_niche_benchmark_context(
    target_post: SinglePostInsights,
    niche_avg_engagement_rate: float | None,
    niche_avg_save_rate: float | None,
    category: str | None,
) -> NicheBenchmarkContext:
    """Compute deterministic niche benchmark context for a single post."""
    if target_post.derived_metrics is None:
        post_engagement_rate = None
        post_save_rate = None
    else:
        post_engagement_rate = target_post.derived_metrics.engagement_rate
        post_save_rate = target_post.derived_metrics.save_rate

    follower_count = getattr(target_post, "follower_count", None)
    follower_count_value = follower_count if isinstance(follower_count, int) else None
    follower_band = _resolve_follower_band(follower_count_value)

    commentary = _build_commentary(
        post_engagement_rate,
        niche_avg_engagement_rate,
        post_save_rate,
        niche_avg_save_rate,
    )

    return {
        "category": category,
        "follower_band": follower_band,
        "avg_engagement_rate": niche_avg_engagement_rate,
        "avg_save_rate": niche_avg_save_rate,
        "post_engagement_rate": post_engagement_rate,
        "post_save_rate": post_save_rate,
        "commentary": commentary,
    }
