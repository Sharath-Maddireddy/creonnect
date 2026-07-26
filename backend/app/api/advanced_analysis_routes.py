"""API routes for advanced account analysis features.

Includes revenue optimization, risk assessment, and brand readiness endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.account_models import (
    BrandReadinessBreakdown,
    RateRecommendation,
    RiskAssessment,
)
from backend.app.utils.logger import logger


router = APIRouter(prefix="/api/account-analysis", tags=["Advanced Analysis"])


# ── Request/Response Models ───────────────────────────────────────────────────


class RateCalculationRequest(BaseModel):
    """Request payload for rate calculation."""

    model_config = ConfigDict(extra="forbid")

    engagement_rate: float = Field(description="Average engagement rate (0.0-1.0)")
    follower_count: int = Field(description="Current follower count")
    niche: str = Field(description="Primary content niche")
    brand_safety_score: float = Field(default=80.0, description="Brand safety score (0-100)")
    content_quality_score: float = Field(default=70.0, description="Content quality score (0-100)")
    save_rate: float = Field(default=0.05, description="Average save rate (0.0-1.0)")
    share_rate: float = Field(default=0.01, description="Average share rate (0.0-1.0)")


class RiskAssessmentRequest(BaseModel):
    """Request payload for risk assessment."""

    model_config = ConfigDict(extra="forbid")

    posts: list[dict[str, Any]] = Field(description="List of posts to analyze")


class BrandReadinessRequest(BaseModel):
    """Request payload for brand readiness calculation."""

    model_config = ConfigDict(extra="forbid")

    posts: list[dict[str, Any]] = Field(description="List of posts to analyze")
    pillar_scores: dict[str, Any] | None = Field(default=None, description="Optional pillar scores")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/revenue", response_model=RateRecommendation)
async def calculate_revenue(request: RateCalculationRequest) -> RateRecommendation:
    """Calculate rate recommendation based on performance metrics.

    Provides dynamic rate pricing with optimization tips and revenue projections.
    """
    try:
        from backend.app.services.revenue_calculator import calculate_rate_recommendation

        result = calculate_rate_recommendation(
            engagement_rate=request.engagement_rate,
            follower_count=request.follower_count,
            niche=request.niche,
            brand_safety_score=request.brand_safety_score,
            content_quality_score=request.content_quality_score,
            save_rate=request.save_rate,
            share_rate=request.share_rate,
        )

        logger.info(
            "[AdvancedAnalysis] Revenue calculated: rate=$%.2f",
            result.recommended_rate,
        )

        return result

    except Exception as exc:
        logger.exception("[AdvancedAnalysis] Revenue calculation failed")
        raise HTTPException(status_code=500, detail="Failed to calculate revenue") from exc


@router.post("/risks", response_model=RiskAssessment)
async def assess_risks(request: RiskAssessmentRequest) -> RiskAssessment:
    """Perform comprehensive risk assessment for an account.

    Identifies engagement declines, brand safety issues, and growth risks.
    """
    try:
        from backend.app.services.risk_assessment import assess_account_risks
        from backend.app.domain.post_models import SinglePostInsights

        # Convert dict posts to SinglePostInsights objects
        posts = []
        for post_dict in request.posts:
            try:
                post = SinglePostInsights.model_validate(post_dict)
                posts.append(post)
            except Exception as e:
                logger.warning("[AdvancedAnalysis] Failed to parse post: %s", e)
                continue

        result = assess_account_risks(posts)

        logger.info(
            "[AdvancedAnalysis] Risk assessment: level=%s risks=%d",
            result.overall_risk_level.value,
            result.risk_count,
        )

        return result

    except Exception as exc:
        logger.exception("[AdvancedAnalysis] Risk assessment failed")
        raise HTTPException(status_code=500, detail="Failed to assess risks") from exc


@router.post("/brand-readiness", response_model=BrandReadinessBreakdown)
async def calculate_brand_readiness(request: BrandReadinessRequest) -> BrandReadinessBreakdown:
    """Calculate detailed brand readiness score with component breakdown.

    Provides scores for content quality, brand safety, engagement, consistency,
    niche clarity, and audience quality with improvement recommendations.
    """
    try:
        from backend.app.services.brand_readiness import calculate_brand_readiness
        from backend.app.domain.post_models import SinglePostInsights

        # Convert dict posts to SinglePostInsights objects
        posts = []
        for post_dict in request.posts:
            try:
                post = SinglePostInsights.model_validate(post_dict)
                posts.append(post)
            except Exception as e:
                logger.warning("[AdvancedAnalysis] Failed to parse post: %s", e)
                continue

        result = calculate_brand_readiness(
            posts=posts,
            pillar_scores=request.pillar_scores,
        )

        logger.info(
            "[AdvancedAnalysis] Brand readiness: score=%s label=%s",
            result.overall_score,
            result.overall_label,
        )

        return result

    except Exception as exc:
        logger.exception("[AdvancedAnalysis] Brand readiness calculation failed")
        raise HTTPException(status_code=500, detail="Failed to calculate brand readiness") from exc
