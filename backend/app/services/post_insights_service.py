"""Service orchestration for full single-post insights assembly."""

from __future__ import annotations

from typing import Any, TypedDict

from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.analytics.benchmark_engine import compute_benchmark_metrics
from backend.app.analytics.caption_s2_engine import compute_s2_caption_effectiveness
from backend.app.analytics.content_score import compute_content_score
from backend.app.analytics.derived_metrics import compute_derived_metrics
from backend.app.analytics.s4_audience_relevance_engine import compute_s4_audience_relevance
from backend.app.domain.post_models import (
    BenchmarkMetrics,
    CoreMetrics,
    DerivedMetrics,
    SinglePostInsights,
)
from backend.app.services.ai_analysis_service import (
    analyze_single_post_ai,
)
from backend.app.services.post_snapshot_store import write_post_insights_snapshot
from backend.app.utils.logger import logger


class SinglePostInsightsResponse(TypedDict):
    """Typed response payload for single-post insights orchestration."""

    post: SinglePostInsights
    content_score: dict[str, int | str]
    ai_analysis: dict[str, Any] | None


def _coerce_single_post_insights(post: SinglePostInsights | CreatorPostAIInput) -> SinglePostInsights:
    if isinstance(post, SinglePostInsights):
        return post

    media_type = "REEL" if post.post_type == "REEL" else "IMAGE"
    reach = getattr(post, "reach", None)
    impressions = getattr(post, "impressions", None)
    views = getattr(post, "views", None)
    # Preserve metric semantics: only backfill impressions from views when explicit fields are missing.
    if impressions is None and views is not None:
        impressions = views
    core_metrics = CoreMetrics(
        reach=reach,
        impressions=impressions,
        likes=post.likes,
        comments=post.comments,
        shares=None,
        saves=None,
        profile_visits=None,
        website_taps=None,
        source_engagement_rate=None,
    )
    return SinglePostInsights(
        account_id=post.creator_id if post.creator_id is not None else None,
        media_id=post.post_id,
        media_url=post.media_url if post.media_url is not None else None,
        media_type=media_type,
        caption_text=post.caption_text,
        follower_count=None,
        published_at=post.posted_at,
        core_metrics=core_metrics,
        derived_metrics=DerivedMetrics(),
        benchmark_metrics=BenchmarkMetrics(),
    )


async def build_single_post_insights(
    target_post: SinglePostInsights | CreatorPostAIInput,
    historical_posts: list[SinglePostInsights | CreatorPostAIInput],
    run_ai: bool = False,
) -> SinglePostInsightsResponse:
    """Build a fully populated single-post insights payload.

    The pipeline computes deterministic derived metrics, benchmark metrics,
    and content score for the target post. Optionally, it also runs async AI
    analysis and attaches the result.
    """
    target_post_model = _coerce_single_post_insights(target_post)
    historical_models = [_coerce_single_post_insights(post) for post in historical_posts]
    logger.info(
        "[PostInsights] Start media_id=%s account_id=%s history_count=%d run_ai=%s",
        target_post_model.media_id,
        target_post_model.account_id,
        len(historical_models),
        run_ai,
    )

    if target_post_model.core_metrics is None:
        raise ValueError("target_post.core_metrics must not be None")
    if target_post_model.media_id is None:
        raise ValueError("target_post.media_id must not be None")

    filtered_history = [
        post for post in historical_models if post.media_id != target_post_model.media_id
    ]
    logger.debug(
        "[PostInsights] Filtered history media_id=%s historical_count=%d comparable_count=%d",
        target_post_model.media_id,
        len(historical_models),
        len(filtered_history),
    )

    post_copy = target_post_model.model_copy(update={})

    derived_metrics = compute_derived_metrics(post_copy.core_metrics)
    post_copy = post_copy.model_copy(update={"derived_metrics": derived_metrics})
    logger.debug(
        "[PostInsights] Derived metrics media_id=%s engagement_rate=%s",
        post_copy.media_id,
        getattr(derived_metrics, "engagement_rate", None),
    )

    logger.debug("[PostInsights] Using deterministic caption scoring media_id=%s", post_copy.media_id)
    caption_effectiveness_score = compute_s2_caption_effectiveness(post_copy.caption_text)
    post_copy = post_copy.model_copy(update={"caption_effectiveness_score": caption_effectiveness_score})

    logger.debug("[PostInsights] Using deterministic audience scoring media_id=%s", post_copy.media_id)
    audience_relevance_score = compute_s4_audience_relevance(
        post_copy.post_category,
        post_copy.creator_dominant_category,
    )
    post_copy = post_copy.model_copy(update={"audience_relevance_score": audience_relevance_score})

    benchmark_metrics = compute_benchmark_metrics(post_copy, filtered_history)
    post_copy = post_copy.model_copy(update={"benchmark_metrics": benchmark_metrics})
    logger.debug(
        "[PostInsights] Benchmarks media_id=%s tier_avg_er=%s percentile_rank=%s",
        post_copy.media_id,
        getattr(benchmark_metrics, "tier_avg_engagement_rate", None),
        getattr(benchmark_metrics, "percentile_engagement_rank", None),
    )

    content_score = compute_content_score(
        post_copy.derived_metrics,
        post_copy.benchmark_metrics,
    )

    ai_analysis: dict[str, Any] | None = None
    if run_ai:
        logger.info("[PostInsights] Running post AI analysis media_id=%s", post_copy.media_id)
        ai_analysis = await analyze_single_post_ai(post_copy)

    if isinstance(post_copy.media_id, str) and post_copy.media_id.strip():
        write_post_insights_snapshot(
            post_copy.media_id,
            post=post_copy,
            ai_analysis=ai_analysis,
        )
        logger.debug("[PostInsights] Snapshot persisted media_id=%s", post_copy.media_id)

    logger.info(
        "[PostInsights] Completed media_id=%s content_score=%s ai_analysis=%s",
        post_copy.media_id,
        content_score.get("content_score") if isinstance(content_score, dict) else None,
        ai_analysis is not None,
    )
    return {
        "post": post_copy,
        "content_score": content_score,
        "ai_analysis": ai_analysis,
    }
