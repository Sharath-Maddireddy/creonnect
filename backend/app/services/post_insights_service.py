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
    AudienceRelevanceScore,
    BenchmarkMetrics,
    CaptionEffectivenessScore,
    CoreMetrics,
    DerivedMetrics,
    SinglePostInsights,
)
from backend.app.services.ai_analysis_service import (
    analyze_single_post_ai,
    run_audience_relevance_llm,
    run_caption_analysis_llm,
)


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
    run_advanced_caption_ai: bool = False,
    run_advanced_audience_ai: bool = False,
) -> SinglePostInsightsResponse:
    """Build a fully populated single-post insights payload.

    The pipeline computes deterministic derived metrics, benchmark metrics,
    and content score for the target post. Optionally, it also runs async AI
    analysis and attaches the result.
    """
    target_post_model = _coerce_single_post_insights(target_post)
    historical_models = [_coerce_single_post_insights(post) for post in historical_posts]

    if target_post_model.core_metrics is None:
        raise ValueError("target_post.core_metrics must not be None")
    if target_post_model.media_id is None:
        raise ValueError("target_post.media_id must not be None")

    filtered_history = [
        post for post in historical_models if post.media_id != target_post_model.media_id
    ]

    post_copy = target_post_model.model_copy(update={})

    derived_metrics = compute_derived_metrics(post_copy.core_metrics)
    post_copy = post_copy.model_copy(update={"derived_metrics": derived_metrics})

    caption_effectiveness_score: CaptionEffectivenessScore | None = None
    if run_advanced_caption_ai and isinstance(post_copy.caption_text, str) and post_copy.caption_text.strip():
        s2_payload = await run_caption_analysis_llm(post_copy.caption_text)
        print("DEBUG S2 PAYLOAD:", s2_payload)
        if isinstance(s2_payload, dict):
            try:
                caption_effectiveness_score = CaptionEffectivenessScore.model_validate(s2_payload)
            except Exception as e:
                import traceback
                print("DEBUG MODEL VALIDATION ERROR:")
                traceback.print_exc()
                caption_effectiveness_score = None
    if caption_effectiveness_score is None:
        caption_effectiveness_score = compute_s2_caption_effectiveness(post_copy.caption_text)
    post_copy = post_copy.model_copy(update={"caption_effectiveness_score": caption_effectiveness_score})

    audience_relevance_score: AudienceRelevanceScore | None = None
    creator_cat = post_copy.creator_dominant_category
    post_cat = post_copy.post_category
    if run_advanced_audience_ai and (creator_cat or post_cat):
        s4_payload = await run_audience_relevance_llm(creator_cat, post_cat)
        if isinstance(s4_payload, dict):
            affinity = s4_payload.get("affinity_band", "UNKNOWN")
            s4_raw = s4_payload.get("s4_raw_0_100", 50)
            explanation = s4_payload.get("audience_overlap_explanation")
            notes = []
            if isinstance(explanation, str) and explanation.strip():
                notes.append(explanation.strip()[:160])
            if isinstance(affinity, str):
                affinity = affinity.strip().upper()
            else:
                affinity = "UNKNOWN"
            s4_raw_value = float(s4_raw) if isinstance(s4_raw, (int, float)) else 50.0
            audience_relevance_score = AudienceRelevanceScore(
                post_category=post_cat,
                creator_dominant_category=creator_cat,
                affinity_band=affinity,
                s4_raw_0_100=int(s4_raw_value),
                total_0_50=round(s4_raw_value / 2.0, 1),
                notes=notes,
            )
    if audience_relevance_score is None:
        audience_relevance_score = compute_s4_audience_relevance(post_cat, creator_cat)
    post_copy = post_copy.model_copy(update={"audience_relevance_score": audience_relevance_score})

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
