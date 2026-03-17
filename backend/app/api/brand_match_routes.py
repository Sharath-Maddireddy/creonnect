"""API routes for brand-creator matching."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.analytics.brand_match_engine import score_creator_against_brand
from backend.app.domain.brand_models import BrandProfile, CreatorMatchScore
from backend.app.utils.logger import logger


router = APIRouter(prefix="/api/brand-match", tags=["Brand Match"])


class CreatorInput(BaseModel):
    """One creator's aggregated scoring inputs for brand matching."""

    model_config = ConfigDict(extra="allow")

    account_id: str
    follower_count: int | None = None
    creator_dominant_category: str | None = None
    predicted_engagement_rate: float | None = None
    ahs_score: float | None = None
    avg_visual_quality_score: float | None = None
    avg_brand_safety_score: float | None = None
    adult_content_detected: bool = False


class BrandMatchRequest(BaseModel):
    """Request payload for brand-creator matching."""

    model_config = ConfigDict(extra="forbid")

    brand: BrandProfile
    creators: list[CreatorInput] = Field(min_length=1, max_length=200)


class BrandMatchResponse(BaseModel):
    """Response payload containing ranked creator matches."""

    matches: list[CreatorMatchScore]
    ranked: bool = True
    total_evaluated: int
    disqualified_count: int


@router.post("", response_model=BrandMatchResponse)
def match_creators_to_brand(request: BrandMatchRequest) -> BrandMatchResponse:
    """Score and rank creators against a brand profile."""
    logger.info(
        "[BrandMatch] brand=%s creators=%d",
        request.brand.brand_name,
        len(request.creators),
    )
    matches: list[CreatorMatchScore] = []
    for creator in request.creators:
        try:
            result = score_creator_against_brand(
                account_id=creator.account_id,
                brand=request.brand,
                creator_dominant_category=creator.creator_dominant_category,
                follower_count=creator.follower_count,
                ahs_score=creator.ahs_score,
                predicted_engagement_rate=creator.predicted_engagement_rate,
                visual_quality_score_total=creator.avg_visual_quality_score or 0.0,
                brand_safety_score_total_0_50=creator.avg_brand_safety_score or 50.0,
                adult_content_detected=creator.adult_content_detected,
            )
            matches.append(result)
        except Exception as exc:
            logger.warning("[BrandMatch] Failed scoring creator=%s: %s", creator.account_id, exc)
            raise HTTPException(
                status_code=400,
                detail=f"Failed to score creator '{creator.account_id}': {exc}",
            )

    matches.sort(key=lambda match: (not match.disqualified, match.total_match_score), reverse=True)
    response = BrandMatchResponse(
        matches=matches,
        ranked=True,
        total_evaluated=len(matches),
        disqualified_count=sum(1 for match in matches if match.disqualified),
    )
    logger.info(
        "[BrandMatch] completed evaluated=%d disqualified=%d",
        response.total_evaluated,
        response.disqualified_count,
    )
    return response
