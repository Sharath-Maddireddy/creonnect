"""API routes for brand campaign creator discovery."""

from __future__ import annotations

import os
import re
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.app.analytics.brand_match_engine import score_creator_against_brand
from backend.app.ai.llm_client import LLMClient, LLMClientError
from backend.app.api.instagram_auth_routes import SESSION_USER_ID_KEY
from backend.app.api.rate_limiter import InMemoryRateLimiter
from backend.app.domain.brand_models import BrandProfile, CreatorMatchScore
from backend.app.services.campaign_prompt_service import (
    build_ai_campaign_summary,
    build_brand_profile_from_parsed,
    parse_campaign_prompt,
)
from backend.app.services.brand_chat_service import brand_chat_discover as brand_chat_discover_service
from backend.app.services.creator_pool_service import (
    CreatorPoolUnavailable,
    LookalikeEmbeddingError,
    find_lookalikes,
    query_creator_pool,
)
from backend.app.utils.logger import logger

router = APIRouter(prefix="/api/brand/campaign", tags=["Brand Campaign"])
rate_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)

MAX_MATCH_CANDIDATES = 1000
ACCOUNT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,120}$")


def _campaign_actor(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """Authorize server integrations by key and the first-party UI by session."""
    expected_api_key = (os.getenv("BRAND_API_KEY") or "").strip()
    if x_api_key and expected_api_key and secrets.compare_digest(x_api_key, expected_api_key):
        return f"api-key:{x_api_key}"

    user_id = request.session.get(SESSION_USER_ID_KEY)
    if user_id:
        return f"session:{user_id}"

    raise HTTPException(status_code=401, detail="Sign in or provide a valid API key.")


def _rate_limit_campaign_actor(actor: str = Depends(_campaign_actor)) -> str:
    """Apply campaign route rate limiting using the authenticated actor as the bucket."""
    if rate_limiter.check(actor):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
    return actor


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


class BrandChatRequest(BaseModel):
    """Request for tool-calling brand discovery chat."""

    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=10, max_length=2000)
    brand_name: str | None = None


class BrandChatResponse(BaseModel):
    final_response: str
    results: list[dict[str, Any]]
    tool_calls_made: list[dict[str, Any]]
    clarification: dict[str, Any] | None = None
    total_latency_ms: float


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
                predicted_engagement_rate=creator.get("predicted_engagement_rate"),
                visual_quality_score_total=creator.get("avg_visual_quality_score", 0.0),
                brand_safety_score_total_0_50=creator.get("avg_brand_safety_score"),
                adult_content_detected=creator.get("adult_content_detected"),
            )
            scored_matches.append(match_score)
            if match_score.disqualify_reasons:
                disqualified_count += 1
        except Exception as exc:
            logger.warning(
                "[CampaignRoutes] Failed to score creator %s: %s",
                creator.get("account_id"),
                exc,
            )

    eligible_matches = [match for match in scored_matches if not match.disqualified]
    eligible_matches.sort(key=lambda match: match.total_match_score, reverse=True)
    return eligible_matches[:10], len(candidates), disqualified_count


@router.post("/match", response_model=CampaignMatchResponse)
def manual_campaign_match(
    request: CampaignMatchRequest,
    _actor: str = Depends(_rate_limit_campaign_actor),
):
    """Score the creator pool against a structured brand profile."""
    try:
        brand = request.brand_profile
        candidates = query_creator_pool(
            niche=brand.niche,
            min_followers=brand.min_followers,
            max_followers=brand.max_followers,
            limit=MAX_MATCH_CANDIDATES,
        )

        top_matches, total_eval, disq_count = _process_pool_matching(brand, candidates)

        return CampaignMatchResponse(
            matches=top_matches,
            total_evaluated=total_eval,
            disqualified_count=disq_count,
            brand_profile=brand.model_dump(mode="json"),
        )

    except CreatorPoolUnavailable as exc:
        logger.warning("[CampaignRoutes] Creator pool unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Creator search is temporarily unavailable.") from exc
    except Exception as exc:
        logger.exception("[CampaignRoutes] Error during manual campaign match.")
        raise HTTPException(status_code=500, detail="Internal server error matching creators.") from exc


@router.post("/discover", response_model=CampaignDiscoverResponse)
def ai_campaign_discover(
    campaign_request: CampaignDiscoverRequest,
    _actor: str = Depends(_rate_limit_campaign_actor),
):
    """Use AI to parse a prompt, build a profile, and find creator matches."""
    try:
        parsed_brief = parse_campaign_prompt(
            prompt=campaign_request.prompt,
            brand_name=campaign_request.brand_name,
        )

        try:
            brand = build_brand_profile_from_parsed(parsed_brief)
        except ValueError as exc:
            logger.warning("[CampaignRoutes] Invalid parsed brief: %s", exc)
            raise HTTPException(
                status_code=422,
                detail="The campaign brief contains incompatible requirements. Please refine the follower range and try again.",
            ) from exc

        llm = LLMClient()
        try:
            brand_search_embedding = llm.embed(campaign_request.prompt)
        except LLMClientError as exc:
            logger.warning("[CampaignRoutes] Brand search embedding failed; continuing without vector: %s", exc)
            brand_search_embedding = None

        candidates = query_creator_pool(
            niche=brand.niche,
            min_followers=brand.min_followers,
            max_followers=brand.max_followers,
            limit=MAX_MATCH_CANDIDATES,
        )

        top_matches, total_eval, disq_count = _process_pool_matching(
            brand,
            candidates,
            brand_search_embedding=brand_search_embedding,
        )

        summary = build_ai_campaign_summary(campaign_request.prompt, parsed_brief, brand)

        return CampaignDiscoverResponse(
            parsed_brief=parsed_brief,
            matches=top_matches,
            total_evaluated=total_eval,
            disqualified_count=disq_count,
            ai_explanation=summary,
        )

    except HTTPException:
        raise
    except CreatorPoolUnavailable as exc:
        logger.warning("[CampaignRoutes] Creator pool unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Creator search is temporarily unavailable.") from exc
    except Exception as exc:
        logger.exception("[CampaignRoutes] Error during AI campaign discovery.")
        raise HTTPException(
            status_code=500,
            detail="Internal server error extracting brief and matching creators.",
        ) from exc


@router.post("/chat", response_model=BrandChatResponse)
def brand_chat_discover(
    request: BrandChatRequest,
    _actor: str = Depends(_rate_limit_campaign_actor),
):
    """Use tool-calling workflow for conversational brand discovery."""
    try:
        logger.info("[CampaignRoutes] Processing brand chat discovery request.")
        service_response = brand_chat_discover_service(request.prompt, request.brand_name)

        return BrandChatResponse(
            final_response=service_response.final_response,
            results=service_response.results,
            tool_calls_made=service_response.tool_calls_made,
            clarification=service_response.clarification,
            total_latency_ms=service_response.total_latency_ms,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[CampaignRoutes] Error during brand chat discovery.")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during brand chat discovery.",
        ) from exc


@router.get("/lookalikes/{account_id}", response_model=LookalikeResponse)
def get_creator_lookalikes(
    account_id: str,
    _actor: str = Depends(_rate_limit_campaign_actor),
):
    """Return semantic lookalikes for a creator account."""
    if not ACCOUNT_ID_PATTERN.fullmatch(account_id):
        raise HTTPException(status_code=422, detail="Invalid account_id format.")

    try:
        lookalikes = find_lookalikes(account_id, k=5)
    except (CreatorPoolUnavailable, LookalikeEmbeddingError) as exc:
        logger.warning("[CampaignRoutes] Lookalike lookup failed for %s: %s", account_id, exc)
        raise HTTPException(status_code=503, detail="Lookalike search is temporarily unavailable.")

    if lookalikes is None:
        raise HTTPException(status_code=404, detail="Creator not found.")

    return LookalikeResponse(account_id=account_id, lookalikes=lookalikes)
