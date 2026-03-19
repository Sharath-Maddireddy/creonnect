"""API routes for campaign prompt parsing and creator discovery."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.analytics.brand_match_engine import score_creator_against_brand
from backend.app.domain.brand_models import BrandProfile, CreatorMatchScore
from backend.app.services.creator_pool_service import query_creator_pool
from backend.app.services.campaign_prompt_service import (
    build_brand_profile_from_parsed,
    parse_campaign_prompt,
)
from backend.app.utils.logger import logger


router = APIRouter(prefix="/api/brand/campaign", tags=["Brand Campaign"])


class CampaignMatchRequest(BaseModel):
    """Request body for direct brand-profile matching."""

    model_config = ConfigDict(extra="forbid")

    brand_profile: BrandProfile


class CampaignDiscoverRequest(BaseModel):
    """Request body for prompt-based creator discovery."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=10, max_length=1000)
    brand_name: str | None = None


def _score_pool_for_brand(brand_profile: BrandProfile) -> list[CreatorMatchScore]:
    """Query the creator pool and score all matching creators for a brand profile."""

    creators = query_creator_pool(
        niche=brand_profile.niche,
        min_followers=brand_profile.min_followers,
        max_followers=brand_profile.max_followers,
    )
    matches: list[CreatorMatchScore] = []
    for creator in creators:
        result = score_creator_against_brand(
            account_id=str(creator.get("account_id") or ""),
            brand=brand_profile,
            creator_dominant_category=creator.get("creator_dominant_category"),
            follower_count=creator.get("follower_count"),
            ahs_score=creator.get("ahs_score"),
            predicted_engagement_rate=creator.get("predicted_engagement_rate"),
            visual_quality_score_total=creator.get("avg_visual_quality_score") or 0.0,
            brand_safety_score_total_0_50=creator.get("avg_brand_safety_score") or 50.0,
            adult_content_detected=creator.get("adult_content_detected"),
        )
        matches.append(result)

    matches.sort(key=lambda match: (not match.disqualified, match.total_match_score), reverse=True)
    return matches[:10]


@router.post("/match")
def match_campaign(request: CampaignMatchRequest) -> dict:
    """Score creator-pool matches for a provided brand profile."""

    try:
        matches = _score_pool_for_brand(request.brand_profile)
        return {
            "matches": [match.model_dump() for match in matches],
            "total_evaluated": len(matches),
            "disqualified_count": sum(1 for match in matches if match.disqualified),
            "brand_profile": request.brand_profile.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[CampaignRoutes] /match failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to match campaign creators: {exc}") from exc


@router.post("/discover")
async def discover_campaign(request: CampaignDiscoverRequest) -> dict:
    """Parse a natural-language campaign brief and return top creator matches."""

    try:
        parsed_brief = await parse_campaign_prompt(request.prompt, request.brand_name)
        brand_profile = build_brand_profile_from_parsed(parsed_brief)
        matches = _score_pool_for_brand(brand_profile)

        ai_explanation = (
            f"Extracted niche '{brand_profile.niche}' for brand '{brand_profile.brand_name}'"
            f" with follower range {brand_profile.min_followers} to {brand_profile.max_followers}"
            f" and minimum engagement rate {brand_profile.min_engagement_rate}."
        )

        return {
            "parsed_brief": parsed_brief,
            "matches": [match.model_dump() for match in matches],
            "total_evaluated": len(matches),
            "disqualified_count": sum(1 for match in matches if match.disqualified),
            "ai_explanation": ai_explanation,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[CampaignRoutes] /discover failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to discover campaign creators: {exc}") from exc
