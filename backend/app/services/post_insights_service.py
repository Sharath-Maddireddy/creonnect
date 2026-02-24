"""Service orchestration for full single-post insights assembly."""

from __future__ import annotations

from typing import Any, TypedDict

from backend.app.analytics.benchmark_engine import compute_benchmark_metrics
from backend.app.analytics.content_score import compute_content_score
from backend.app.analytics.derived_metrics import compute_derived_metrics
from backend.app.domain.post_models import SinglePostInsights
from backend.app.services.ai_analysis_service import analyze_single_post_ai


class SinglePostInsightsResponse(TypedDict):
    """Typed response payload for single-post insights orchestration."""

    post: SinglePostInsights
    content_score: dict[str, int | str]
    ai_analysis: dict[str, Any] | None


async def build_single_post_insights(
    target_post: SinglePostInsights,
    historical_posts: list[SinglePostInsights],
    run_ai: bool = False,
) -> SinglePostInsightsResponse:
    """Build a fully populated single-post insights payload.

    The pipeline computes deterministic derived metrics, benchmark metrics,
    and content score for the target post. Optionally, it also runs async AI
    analysis and attaches the result.
    """
    if target_post.core_metrics is None:
        raise ValueError("target_post.core_metrics must not be None")
    if target_post.media_id is None:
        raise ValueError("target_post.media_id must not be None")

    filtered_history = [
        post for post in historical_posts if post.media_id != target_post.media_id
    ]

    post_copy = target_post.model_copy(update={})

    derived_metrics = compute_derived_metrics(post_copy.core_metrics)
    post_copy = post_copy.model_copy(update={"derived_metrics": derived_metrics})

    benchmark_metrics = compute_benchmark_metrics(post_copy, filtered_history)
    post_copy = post_copy.model_copy(update={"benchmark_metrics": benchmark_metrics})

    content_score = compute_content_score(
        post_copy.derived_metrics,
        post_copy.benchmark_metrics,
    )

    ai_analysis: dict[str, Any] | None = None
    if run_ai:
        ai_analysis = await analyze_single_post_ai(post_copy)

    return {
        "post": post_copy,
        "content_score": content_score,
        "ai_analysis": ai_analysis,
    }
