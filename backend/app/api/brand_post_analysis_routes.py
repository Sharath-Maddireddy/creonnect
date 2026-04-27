"""API route for brand-context post analysis."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.analytics.brand_match_engine import score_creator_against_brand
from backend.app.api.auth import verify_api_key
from backend.app.api.post_analysis_routes import PostAnalysisRequest
from backend.app.api.rate_limiter import InMemoryRateLimiter
from backend.app.domain.brand_models import BrandProfile, CreatorMatchScore
from backend.app.domain.post_models import SinglePostInsights
from backend.app.services.post_insights_service import build_single_post_insights
from backend.app.utils.logger import logger


router = APIRouter(prefix="/api/v1/brand", tags=["Brand Post Analysis"])
rate_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)


def _rate_limit_by_api_key(api_key: str = Depends(verify_api_key)) -> str:
    if rate_limiter.check(api_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    return api_key


class BrandPostAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_profile: BrandProfile
    post: dict[str, Any]
    account_id: str | None = None
    creator_dominant_category: str | None = None
    follower_count: int | None = None


class BrandPostAnalysisResponse(BaseModel):
    post_analysis: dict[str, Any]
    brand_fit: CreatorMatchScore
    brand_profile: dict[str, Any]


async def _run_post_insights(post_payload: dict[str, Any]) -> SinglePostInsights | None:
    request = PostAnalysisRequest.model_validate(post_payload)
    creator_post = CreatorPostAIInput(
        post_id=request.post_id,
        creator_id=request.account_id or request.creator_id or "",
        platform=request.platform,
        post_type=request.post_type,
        media_url=request.media_url,
        thumbnail_url=request.thumbnail_url,
        caption_text=request.caption_text,
        hashtags=request.hashtags,
        likes=request.likes,
        comments=request.comments,
        views=request.views,
        audio_name=request.audio_name,
        posted_at=request.posted_at,
    )
    pipeline_result = await build_single_post_insights(
        target_post=creator_post,
        historical_posts=[],
        run_ai=True,
        run_advanced_caption_ai=True,
        run_advanced_audience_ai=True,
    )
    raw_post = pipeline_result.get("post")
    if raw_post is None:
        return None
    return raw_post if isinstance(raw_post, SinglePostInsights) else SinglePostInsights.model_validate(raw_post)


@router.post("/post-analysis", response_model=BrandPostAnalysisResponse)
async def brand_post_analysis(
    request: BrandPostAnalysisRequest,
    api_key: str = Depends(_rate_limit_by_api_key),
):
    """
    Run full AI post analysis on a creator post and score it
    against a brand profile in a single request.
    """
    del api_key

    try:
        post_insights = await _run_post_insights(request.post)
    except Exception as exc:
        logger.exception("[BrandPostAnalysis] Post analysis pipeline failed.")
        raise HTTPException(status_code=500, detail="Post analysis failed.") from exc

    visual_quality = 0.0
    brand_safety = 50.0
    predicted_er = None
    ahs_proxy = None
    adult_content = None

    if post_insights is not None:
        vq = getattr(post_insights, "visual_quality_score", None)
        if vq is not None:
            visual_quality = float(getattr(vq, "total", 0.0) or 0.0)

        bs = getattr(post_insights, "brand_safety_score", None)
        if bs is not None:
            brand_safety = float(getattr(bs, "total_0_50", 50.0) or 50.0)

        predicted_er = getattr(post_insights, "predicted_engagement_rate", None)

        wps = getattr(post_insights, "weighted_post_score", None)
        if wps is not None:
            ahs_proxy = float(getattr(wps, "score", 50.0) or 50.0)

        vs = getattr(post_insights, "vision_analysis", None)
        if vs and getattr(vs, "signals", None):
            first_signal = vs.signals[0]
            adult_content = getattr(first_signal, "adult_content_detected", None)

    account_id = request.account_id or "unknown"
    brand_fit = score_creator_against_brand(
        account_id=account_id,
        brand=request.brand_profile,
        creator_dominant_category=request.creator_dominant_category,
        follower_count=request.follower_count,
        ahs_score=ahs_proxy,
        predicted_engagement_rate=predicted_er,
        visual_quality_score_total=visual_quality,
        brand_safety_score_total_0_50=brand_safety,
        adult_content_detected=adult_content,
    )

    return BrandPostAnalysisResponse(
        post_analysis=post_insights.model_dump(mode="json") if post_insights is not None else {},
        brand_fit=brand_fit,
        brand_profile=request.brand_profile.model_dump(mode="json"),
    )
