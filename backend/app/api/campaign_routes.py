"""API routes for brand campaign creator discovery."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.app.analytics.brand_match_engine import score_creator_against_brand
from backend.app.ai.llm_client import LLMClient
from backend.app.api.auth import verify_api_key
from backend.app.api.rate_limiter import InMemoryRateLimiter
from backend.app.domain.brand_models import BrandProfile, CreatorMatchScore
from backend.app.services.campaign_prompt_service import (
    build_brand_profile_from_parsed,
    parse_campaign_prompt,
)
from backend.app.services.creator_pool_service import find_lookalikes, query_creator_pool
from backend.app.utils.logger import logger

router = APIRouter(prefix="/api/brand/campaign", tags=["Brand Campaign"])
rate_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)


class CampaignMatchRequest(BaseModel):
    """Request for manual matcher using a structured profile."""
    model_config = ConfigDict(extra="forbid")
    brand_profile: BrandProfile


class CampaignMatchResponse(BaseModel):
    matches: list[CreatorMatchScore]
    total_evaluated: int
    disqualified_count: int
    brand_profile: dict[str, Any]


class CampaignDiscoverRequest(BaseModel):
    """Request for AI discovery using a natural language prompt."""
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=10, max_length=1000)
    brand_name: str | None = None


class CampaignDiscoverResponse(BaseModel):
    parsed_brief: dict[str, Any]
    matches: list[CreatorMatchScore]
    total_evaluated: int
    disqualified_count: int
    ai_explanation: str


class LookalikeResponse(BaseModel):
    account_id: str
    lookalikes: list[dict]


def _process_pool_matching(
    brand: BrandProfile,
    candidates: list[dict],
    brand_search_embedding: list[float] | None = None,
) -> tuple[list[CreatorMatchScore], int, int]:
    """Score candidates against the brand profile and return top 10."""
    scored_matches: list[CreatorMatchScore] = []
    disqualified_count = 0

    for creator in candidates:
        try:
            match_score = score_creator_against_brand(
                account_id=creator.get("account_id", ""),
                brand=brand,
                creator_dominant_category=creator.get("creator_dominant_category", ""),
                brand_search_embedding=brand_search_embedding,
                creator_embedding=creator.get("embedding"),
                follower_count=creator.get("follower_count", 0),
                avg_views=creator.get("avg_views", 0),
                avg_likes=creator.get("avg_likes", 0),
                avg_comments=creator.get("avg_comments", 0),
                ahs_score=creator.get("ahs_score", 0.0),
                predicted_engagement_rate=creator.get("predicted_engagement_rate", 0.0),
                visual_quality_score_total=creator.get("avg_visual_quality_score", 0.0),
                brand_safety_score_total_0_50=creator.get("avg_brand_safety_score", 0.0),
                adult_content_detected=creator.get("adult_content_detected"),
            )
            scored_matches.append(match_score)
            if match_score.disqualify_reasons:
                disqualified_count += 1
        except Exception as e:
            logger.warning(f"[CampaignRoutes] Failed to score creator {creator.get('account_id')}: {e}")

    # Sort so qualified matches are first, then sort by score descending
    scored_matches.sort(
        key=lambda x: (not bool(x.disqualify_reasons), x.total_match_score), 
        reverse=True
    )
    
    return scored_matches[:10], len(candidates), disqualified_count


@router.post("/match", response_model=CampaignMatchResponse)
def manual_campaign_match(
    request: CampaignMatchRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Score the creator pool against a structured brand profile (manual form submission).
    """
    try:
        brand = request.brand_profile
        candidates = query_creator_pool(
            niche=brand.niche,
            min_followers=brand.min_followers,
            max_followers=brand.max_followers
        )
        
        top_matches, total_eval, disq_count = _process_pool_matching(brand, candidates)

        return CampaignMatchResponse(
            matches=top_matches,
            total_evaluated=total_eval,
            disqualified_count=disq_count,
            brand_profile=brand.model_dump(mode="json")
        )

    except Exception as e:
        logger.exception("[CampaignRoutes] Error during manual campaign match.")
        raise HTTPException(status_code=500, detail="Internal server error matching creators.")


@router.post("/discover", response_model=CampaignDiscoverResponse)
def ai_campaign_discover(
    request: Request,
    campaign_request: CampaignDiscoverRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Use AI to parse a natural language prompt, build a brand profile, and find matches.
    """
    try:
        client_ip = request.client.host if request.client else "unknown"
        if rate_limiter.check(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

        # 1. Parse prompt
        parsed_brief = parse_campaign_prompt(
            prompt=campaign_request.prompt,
            brand_name=campaign_request.brand_name,
        )
        
        # 2. Build profile validation
        try:
            brand = build_brand_profile_from_parsed(parsed_brief)
        except ValueError as ve:
            # Fallback if AI gave us an invalid combo like min > max
            logger.warning(f"[CampaignRoutes] Invalid parsed brief: {ve}. Falling back.")
            parsed_brief["min_followers"] = None
            parsed_brief["max_followers"] = None
            brand = build_brand_profile_from_parsed(parsed_brief)

        llm = LLMClient()
        brand_search_embedding = llm.embed(campaign_request.prompt)

        # 3. Query candidate pool
        candidates = query_creator_pool(
            niche=brand.niche,
            min_followers=brand.min_followers,
            max_followers=brand.max_followers
        )
        
        # 4. Score and sort matches
        top_matches, total_eval, disq_count = _process_pool_matching(
            brand,
            candidates,
            brand_search_embedding=brand_search_embedding,
        )
        
        # 5. Build friendly summary
        summary = (
            f"Extracted mission: find a {brand.niche} creator "
            f"with at least {brand.min_followers or 0} followers for {brand.brand_name}."
        )

        return CampaignDiscoverResponse(
            parsed_brief=parsed_brief,
            matches=top_matches,
            total_evaluated=total_eval,
            disqualified_count=disq_count,
            ai_explanation=summary
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[CampaignRoutes] Error during AI campaign discovery.")
        raise HTTPException(status_code=500, detail="Internal server error extracting brief and matching creators.")


@router.get("/lookalikes/{account_id}", response_model=LookalikeResponse)
def get_creator_lookalikes(
    account_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Return semantic lookalikes for a creator account."""
    lookalikes = find_lookalikes(account_id, k=5)
    if not lookalikes:
        raise HTTPException(status_code=404, detail="Creator not found or no lookalikes available.")

    return LookalikeResponse(account_id=account_id, lookalikes=lookalikes)
