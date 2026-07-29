"""API routes for content suggestions feature."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.content_suggestion_models import (
    ConflictResponse,
    ConflictItem,
    CreateCollectionRequest,
    GenerateCaptionRequest,
    GenerateCaptionResponse,
    GenerateIdeasRequest,
    GenerateIdeasResponse,
    GenerateScriptRequest,
    GenerateScriptResponse,
    IdeaReasoningResponse,
    ImproveIdeaRequest,
    ImproveIdeaResponse,
    ImproveScriptBlockRequest,
    PaginatedIdeasResponse,
    PaginationMeta,
    PlannerResponse,
    PersistQuickIdeaRequest,
    UpdateIdeaRequest,
    DaySchedule,
    RegenerateRequest,
    RegenerateResponse,
    SaveIdeaRequest,
    ScheduleIdeaRequest,
    ScheduledItemResponse,
    VariationsRequest,
    VariationsResponse,
    MultiSaveRequest,
    CaptionVariantsRequest,
    AssistantRequest,
    AssistantResponse,
)
from backend.app.infra.database import get_db
from backend.app.api.instagram_auth_routes import require_current_account
from backend.app.infra.models import (
    Collection,
    CollectionIdea,
    Idea,
    IdeaGenerationJob,
    CreatorTrendResult,
    ScheduledItem,
)
from backend.app.services.content_suggestion_jobs import (
    enqueue_idea_generation,
    enqueue_idea_improve,
    enqueue_idea_variations,
    enqueue_idea_regenerate,
    get_idea_generation_status,
)
from backend.app.utils.logger import logger
from backend.app.utils.env import is_feature_enabled
from backend.app.utils.telemetry import emit_counter, emit_histogram, emit_event, timed

router = APIRouter(
    prefix="/api/v1/accounts",
    tags=["content-suggestions"],
    dependencies=[Depends(require_current_account)],
)


def _clamp_int(value: float | int | None, default: int) -> int:
    if not isinstance(value, (int, float)):
        return default
    return max(0, min(100, int(round(value))))


def _build_reasoning_factors(idea: Idea) -> list[dict[str, Any]]:
    metadata = idea.generation_metadata or {}
    trend_snapshot = metadata.get("trend_snapshot") if isinstance(metadata.get("trend_snapshot"), dict) else {}
    recommendation_snapshot = metadata.get("recommendation_snapshot") if isinstance(metadata.get("recommendation_snapshot"), dict) else {}
    base_score = float(idea.opportunity_score or idea.engagement_score or 75.0)

    trend_type = str(trend_snapshot.get("trend_type") or "").strip().lower()
    momentum = str(trend_snapshot.get("momentum") or "").strip().lower()
    difficulty = str(idea.difficulty or recommendation_snapshot.get("difficulty") or "").strip().lower()
    content_style = str(metadata.get("content_style") or recommendation_snapshot.get("content_style") or "").strip().lower()
    content_type = str(idea.content_type or "").strip().lower()

    audience_match_raw = trend_snapshot.get("audience_match_pct")
    if isinstance(audience_match_raw, (int, float)):
        audience_match = _clamp_int(audience_match_raw, 72)
    elif isinstance(recommendation_snapshot.get("opportunity_score"), (int, float)):
        audience_match = _clamp_int(float(recommendation_snapshot["opportunity_score"]) * 0.92, 72)
    else:
        audience_match = _clamp_int(base_score * 0.88, 72)

    momentum_value = {
        "rising": 88,
        "peaking": 80,
        "falling": 52,
    }.get(momentum, _clamp_int(base_score * 0.8, 66))

    timing_value = 86 if isinstance(idea.best_time_to_post, str) and idea.best_time_to_post.strip() else 58

    difficulty_value = {
        "easy": 84,
        "medium": 69,
        "hard": 54,
    }.get(difficulty, 66)

    content_type_value = {
        "reel": 84,
        "carousel": 76,
        "photo": 67,
    }.get(content_type, 72)
    if content_style in {"educational", "how-to", "storytelling", "pov/lifestyle", "brand friendly"}:
        content_type_value = min(100, content_type_value + 6)
    if trend_type == "format":
        content_type_value = min(100, content_type_value + 4)

    performance_source = idea.engagement_score if isinstance(idea.engagement_score, (int, float)) else base_score * 0.93
    post_performance = _clamp_int(performance_source, 70)

    niche_reference_score = recommendation_snapshot.get("opportunity_score")
    if isinstance(niche_reference_score, (int, float)):
        niche_relevance = _clamp_int(float(niche_reference_score), 74)
    else:
        niche_relevance = _clamp_int(base_score * 0.9, 74)

    return [
        {
            "key": "niche_relevance",
            "value": niche_relevance,
            "tooltip": "How strongly this idea aligns with the creator's niche and recommendation fit.",
        },
        {
            "key": "audience_match",
            "value": audience_match,
            "tooltip": "How well the underlying trend appears to match this creator's audience interests.",
        },
        {
            "key": "momentum_score",
            "value": momentum_value,
            "tooltip": "How strong the attached trend momentum is right now.",
        },
        {
            "key": "content_type_match",
            "value": content_type_value,
            "tooltip": "How appropriate the selected content format and style are for this opportunity.",
        },
        {
            "key": "best_timing",
            "value": timing_value,
            "tooltip": "Whether the backend has a concrete best posting time for this idea.",
        },
        {
            "key": "post_performance",
            "value": post_performance,
            "tooltip": "How much prior or predicted performance evidence supports this idea.",
        },
        {
            "key": "competitive_score",
            "value": difficulty_value,
            "tooltip": "A practical execution/competition proxy based on the idea's difficulty.",
        },
    ]


async def _compute_idea_percentile_rank(account_id: str, db: AsyncSession, score: float) -> int | None:
    result = await db.execute(
        select(Idea.opportunity_score)
        .where(Idea.account_id == account_id, Idea.opportunity_score.is_not(None))
    )
    raw_scores = [float(value) for value in result.scalars().all() if isinstance(value, (int, float))]
    if not raw_scores:
        return None
    less_or_equal = sum(1 for value in raw_scores if value <= score)
    percentile = round((less_or_equal / len(raw_scores)) * 100)
    return max(1, min(100, percentile))


async def _get_account_idea_or_404(db: AsyncSession, account_id: str, idea_id: str) -> Idea:
    """Load an idea only when it belongs to the account in the route."""
    result = await db.execute(select(Idea).where(Idea.id == idea_id, Idea.account_id == account_id))
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    return idea


async def _get_account_collection_or_404(db: AsyncSession, account_id: str, collection_id: str) -> Collection:
    """Load a collection only when it belongs to the account in the route."""
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.account_id == account_id)
    )
    collection = result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


def _compute_reasoning_confidence(idea: Idea, factors: list[dict[str, Any]]) -> int:
    metadata = idea.generation_metadata or {}
    evidence_points = 0
    if isinstance(idea.best_time_to_post, str) and idea.best_time_to_post.strip():
        evidence_points += 1
    if isinstance(idea.engagement_score, (int, float)):
        evidence_points += 1
    if isinstance(idea.trend_reference, str) and idea.trend_reference.strip():
        evidence_points += 1
    if isinstance(metadata.get("rationale"), str) and metadata.get("rationale", "").strip():
        evidence_points += 1
    if isinstance(metadata.get("trend_snapshot"), dict) and metadata["trend_snapshot"].get("momentum"):
        evidence_points += 1
    if isinstance(metadata.get("recommendation_snapshot"), dict) and metadata["recommendation_snapshot"].get("opportunity_score") is not None:
        evidence_points += 1
    factor_strength = round(sum(item["value"] for item in factors) / max(len(factors), 1))
    return max(45, min(95, 42 + evidence_points * 7 + round((factor_strength - 50) * 0.15)))


# ── Idea Generation ────────────────────────────────────────────────────────────


@router.post("/{account_id}/trends/generate-ideas", response_model=GenerateIdeasResponse)
async def start_idea_generation(
    account_id: str,
    request: GenerateIdeasRequest,
    db: AsyncSession = Depends(get_db),
) -> GenerateIdeasResponse:
    """Start idea generation job."""
    if not is_feature_enabled("TREND_RECOMMENDATIONS_V2"):
        raise HTTPException(status_code=503, detail="Trend Recommendations V2 is not yet available. Check back soon.")
    logger.info("[ContentSuggestionRoutes] Starting idea generation for account=%s", account_id)
    emit_event("trend_generate_clicked", account_id=account_id, properties={"count": request.count, "content_type": request.content_type})
    emit_counter("trends_generation_started", account_id=account_id)
    job_id = await asyncio.to_thread(enqueue_idea_generation, account_id, request)
    return GenerateIdeasResponse(
        job_id=job_id,
        status="processing",
        estimated_seconds=15,
    )


@router.get("/{account_id}/trends/generate-ideas/{job_id}/status")
async def get_generation_status(
    account_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Poll idea generation progress."""
    job_result = await db.execute(
        select(IdeaGenerationJob).where(
            IdeaGenerationJob.id == job_id,
            IdeaGenerationJob.account_id == account_id,
        )
    )
    if not job_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")
    status = await asyncio.to_thread(get_idea_generation_status, job_id)
    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Job not found")
    if status.get("status") == "completed":
        emit_event("trend_generate_succeeded", account_id=account_id, properties={"job_id": job_id, "idea_count": len(status.get("ideas", []))})
        emit_counter("trends_generation_completed", account_id=account_id)
    elif status.get("status") == "failed":
        emit_event("trend_generate_failed", account_id=account_id, properties={"job_id": job_id, "error": status.get("error")})
        emit_counter("trends_generation_failed", account_id=account_id)
    return status


@router.get("/{account_id}/ideas/jobs/{job_id}/status")
async def get_idea_job_status(
    account_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Poll an account-owned asynchronous idea action."""
    result = await db.execute(
        select(IdeaGenerationJob).where(
            IdeaGenerationJob.id == job_id,
            IdeaGenerationJob.account_id == account_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")

    return await asyncio.to_thread(get_idea_generation_status, job_id)


# ── Paginated Ideas List ──────────────────────────────────────────────────────


@router.get("/{account_id}/trends/ideas", response_model=PaginatedIdeasResponse)
async def list_ideas(
    account_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=50),
    sort: str = Query(default="created_at", enum=["created_at", "updated_at", "engagement_score", "opportunity_score"]),
    order: str = Query(default="desc", enum=["asc", "desc"]),
    platform: str | None = Query(default=None),
    status: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    min_score: float | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedIdeasResponse:
    """Get paginated list of ideas with filtering and sorting."""
    # Build query
    stmt = select(Idea).where(Idea.account_id == account_id)

    if platform:
        stmt = stmt.where(Idea.platform == platform)
    if status:
        stmt = stmt.where(Idea.status == status)
    if content_type:
        stmt = stmt.where(Idea.content_type == content_type)
    if min_score is not None:
        stmt = stmt.where(Idea.opportunity_score >= min_score)

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = (await db.execute(count_stmt)).scalar() or 0

    # Apply sorting
    sort_column = getattr(Idea, sort, Idea.created_at)
    if order == "desc":
        stmt = stmt.order_by(sort_column.desc())
    else:
        stmt = stmt.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * per_page
    stmt = stmt.offset(offset).limit(per_page)

    # Execute
    result = await db.execute(stmt)
    ideas = list(result.scalars().all())

    # Calculate pagination meta
    total_pages = (total_count + per_page - 1) // per_page
    meta = PaginationMeta(
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    # Convert ideas to dicts with all fields
    data = [
        {
            "id": idea.id,
            "title": idea.title,
            "description": idea.description,
            "hook": idea.hook,
            "platform": idea.platform,
            "content_type": idea.content_type or "reel",
            "engagement_score": idea.engagement_score,
            "opportunity_score": idea.opportunity_score,
            "expected_reach_min": idea.expected_reach_min,
            "expected_reach_max": idea.expected_reach_max,
            "expected_views_min": idea.expected_views_min,
            "expected_views_max": idea.expected_views_max,
            "expected_saves_min": idea.expected_saves_min,
            "expected_saves_max": idea.expected_saves_max,
            "expected_shares_min": idea.expected_shares_min,
            "expected_shares_max": idea.expected_shares_max,
            "difficulty": idea.difficulty,
            "duration_seconds": idea.duration_seconds,
            "best_time_to_post": idea.best_time_to_post,
            "trend_reference": idea.trend_reference,
            "tags": idea.tags or [],
            "status": idea.status,
            "parent_idea_id": idea.parent_idea_id,
            "generation_job_id": idea.generation_job_id,
            "created_at": idea.created_at.isoformat() if idea.created_at else None,
            "updated_at": idea.updated_at.isoformat() if idea.updated_at else None,
        }
        for idea in ideas
    ]

    return PaginatedIdeasResponse(data=data, meta=meta)


# ── Script Generation ──────────────────────────────────────────────────────────


@router.post("/{account_id}/trends/persist-idea")
async def persist_quick_idea_endpoint(
    account_id: str,
    request: PersistQuickIdeaRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Persist a quick recommendation card as a database-backed idea."""
    if not is_feature_enabled("TREND_RECOMMENDATIONS_V2"):
        raise HTTPException(status_code=503, detail="Trend Recommendations V2 is not yet available. Check back soon.")

    import uuid

    trend = request.trend or {}
    recommendation = request.recommendation or {}

    title = (
        recommendation.get("suggested_title")
        or trend.get("topic_name")
        or "Content Idea"
    )
    hook = recommendation.get("hook")
    description = (
        recommendation.get("expected_impact")
        or recommendation.get("rationale")
        or trend.get("description")
        or "Generated from a quick trend recommendation."
    )
    rationale = recommendation.get("rationale") or trend.get("description")
    content_style = recommendation.get("content_style") or trend.get("trend_type") or "reel"
    trend_reference = recommendation.get("trend_reference") or trend.get("topic_name")
    difficulty = recommendation.get("difficulty") or "Medium"
    opportunity_score = recommendation.get("opportunity_score")
    content_type = str(content_style).strip() or "reel"

    normalized_type = content_type.lower()
    if normalized_type in {"how-to", "educational", "story", "personal story", "pov/lifestyle", "brand friendly"}:
        normalized_type = "reel"
    elif normalized_type not in {"reel", "carousel", "photo"}:
        normalized_type = "reel"

    tags = [
        value.strip()
        for value in [
            recommendation.get("content_style"),
            trend.get("trend_type"),
            trend.get("momentum"),
            trend_reference,
        ]
        if isinstance(value, str) and value.strip()
    ]

    idea = Idea(
        id=str(uuid.uuid4()),
        account_id=account_id,
        title=title,
        description=description,
        hook=hook,
        content_type=normalized_type,
        platform="instagram",
        opportunity_score=opportunity_score,
        expected_reach_min=recommendation.get("expected_reach_min"),
        expected_reach_max=recommendation.get("expected_reach_max"),
        expected_views_min=recommendation.get("expected_views_min"),
        expected_views_max=recommendation.get("expected_views_max"),
        expected_saves_min=recommendation.get("expected_saves_min"),
        expected_saves_max=recommendation.get("expected_saves_max"),
        expected_shares_min=recommendation.get("expected_shares_min"),
        expected_shares_max=recommendation.get("expected_shares_max"),
        difficulty=difficulty,
        duration_seconds=recommendation.get("duration_seconds") or 45,
        best_time_to_post=recommendation.get("best_time"),
        trend_reference=trend_reference,
        tags=tags,
        generation_metadata={
            "source": request.source,
            "content_style": recommendation.get("content_style"),
            "rationale": rationale,
            "trend_snapshot": trend,
            "recommendation_snapshot": recommendation,
        },
        status="draft",
    )

    db.add(idea)
    await db.commit()

    return {
        "id": idea.id,
        "title": idea.title,
        "hook": idea.hook,
        "description": idea.description,
        "content_type": idea.content_type,
        "opportunity_score": idea.opportunity_score,
        "difficulty": idea.difficulty,
        "trend_reference": idea.trend_reference,
        "rationale": rationale,
        "status": idea.status,
    }


@router.post("/{account_id}/trends/generate-script", response_model=GenerateScriptResponse)
async def generate_script_endpoint(
    account_id: str,
    request: GenerateScriptRequest,
    db: AsyncSession = Depends(get_db),
) -> GenerateScriptResponse:
    """Generate script for an idea."""
    if not is_feature_enabled("TREND_RECOMMENDATIONS_V2"):
        raise HTTPException(status_code=503, detail="Trend Recommendations V2 is not yet available. Check back soon.")
    logger.info("[ContentSuggestionRoutes] Generating script for idea=%s", request.idea_id)

    # Fetch the idea to get title and hook
    idea_result = await db.execute(
        select(Idea).where(Idea.id == request.idea_id, Idea.account_id == account_id)
    )
    idea = idea_result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    from backend.app.services.script_generator import generate_script

    response = await generate_script(
        idea_id=request.idea_id,
        title=idea.title,
        hook=idea.hook,
        script_type=request.script_type,
        content_type=idea.content_type,
        tone=request.tone,
        language=request.language,
        duration_seconds=request.duration_seconds,
    )

    # Store the script on the idea
    idea.script = {
        "hook": response.hook,
        "scenes": [s.model_dump() for s in response.scenes],
        "cta": response.cta,
        "estimated_duration_sec": response.estimated_duration_sec,
        "full_script": response.full_script,
        "content_type": idea.content_type,
    }
    await db.commit()

    return response


@router.post("/{account_id}/trends/generate-caption", response_model=GenerateCaptionResponse)
async def generate_caption_endpoint(
    account_id: str,
    request: GenerateCaptionRequest,
    db: AsyncSession = Depends(get_db),
) -> GenerateCaptionResponse:
    """Generate caption for an idea."""
    if not is_feature_enabled("TREND_RECOMMENDATIONS_V2"):
        raise HTTPException(status_code=503, detail="Trend Recommendations V2 is not yet available. Check back soon.")
    logger.info("[ContentSuggestionRoutes] Generating caption for idea=%s", request.idea_id)

    # Fetch the idea to get title, hook, and script context
    idea_result = await db.execute(
        select(Idea).where(Idea.id == request.idea_id, Idea.account_id == account_id)
    )
    idea = idea_result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    # Build script summary from stored script if available
    script_summary = None
    if idea.script and isinstance(idea.script, dict):
        script_summary = idea.script.get("full_script", "")

    from backend.app.services.caption_generator import generate_caption

    response = await generate_caption(
        idea_id=request.idea_id,
        title=idea.title,
        hook=idea.hook,
        script_summary=script_summary,
        platforms=request.platforms,
        tone=request.tone,
        language=request.language,
        include_hashtags=request.include_hashtags,
        max_hashtags=request.max_hashtags,
    )

    # Store captions on the idea
    idea.captions = [c.model_dump() for c in response.captions]
    await db.commit()

    return response


# ── Idea Improvement ───────────────────────────────────────────────────────────


@router.post("/{account_id}/ideas/{idea_id}/improve", response_model=ImproveIdeaResponse)
async def improve_idea_endpoint(
    account_id: str,
    idea_id: str,
    request: ImproveIdeaRequest,
    db: AsyncSession = Depends(get_db),
) -> ImproveIdeaResponse:
    """Improve an idea based on feedback."""
    logger.info("[ContentSuggestionRoutes] Improving idea=%s aspect=%s", idea_id, request.aspect)
    await _get_account_idea_or_404(db, account_id, idea_id)
    job_id = await asyncio.to_thread(enqueue_idea_improve, account_id, idea_id, request)
    return ImproveIdeaResponse(job_id=job_id, status="processing")


@router.post("/{account_id}/ideas/{idea_id}/variations", response_model=VariationsResponse)
async def generate_variations_endpoint(
    account_id: str,
    idea_id: str,
    request: VariationsRequest,
    db: AsyncSession = Depends(get_db),
) -> VariationsResponse:
    """Generate variations of an idea."""
    logger.info("[ContentSuggestionRoutes] Generating variations for idea=%s count=%d", idea_id, request.count)
    await _get_account_idea_or_404(db, account_id, idea_id)
    job_id = await asyncio.to_thread(enqueue_idea_variations, account_id, idea_id, request)
    return VariationsResponse(job_id=job_id, status="processing")


# ── Screen 2: Script Block Improvement ───────────────────────────────────────

@router.post("/{account_id}/ideas/{idea_id}/improve-script-block")
async def improve_script_block_endpoint(
    account_id: str,
    idea_id: str,
    request: ImproveScriptBlockRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Improve a single scene block in a script (Screen 2)."""
    if not is_feature_enabled("TREND_RECOMMENDATIONS_V2"):
        raise HTTPException(status_code=503, detail="Trend Recommendations V2 is not yet available. Check back soon.")
    logger.info("[ContentSuggestionRoutes] Improving script block=%s for idea=%s", request.block_id, idea_id)

    # Fetch idea
    result = await db.execute(select(Idea).where(Idea.id == idea_id, Idea.account_id == account_id))
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    # Call LLM to improve the block
    from backend.app.ai.llm_client import get_llm_client
    llm = get_llm_client()
    prompt = f"""Improve the following script block for a social media video. Keep the same length and style, but make it more engaging and polished.

Block type: {request.block_id}
Current text: "{request.text}"
Tone: {request.tone}
Instruction: {request.instruction}

Return ONLY the improved text, no explanation."""
    improved = (await llm.complete(prompt)).strip()

    # Update the stored script
    if idea.script and isinstance(idea.script, dict):
        script = dict(idea.script)
        # Find and update the block in scenes, hook, or cta
        if request.block_id == "hook":
            script["hook"] = improved
        elif request.block_id == "cta":
            script["cta"] = improved
        else:
            scenes = script.get("scenes", [])
            for scene in scenes:
                if str(scene.get("scene_number", "")) == request.block_id.replace("scene_", ""):
                    scene["description"] = improved
        idea.script = script
        await db.commit()

    return {"block_id": request.block_id, "improved_text": improved}


# ── Screen 3: Caption Variants ────────────────────────────────────────────────

@router.post("/{account_id}/ideas/{idea_id}/caption/variants")
async def generate_caption_variants_endpoint(
    account_id: str,
    idea_id: str,
    request: CaptionVariantsRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate caption variants (Screen 3)."""
    if not is_feature_enabled("TREND_RECOMMENDATIONS_V2"):
        raise HTTPException(status_code=503, detail="Trend Recommendations V2 is not yet available. Check back soon.")
    logger.info("[ContentSuggestionRoutes] Generating caption variants for idea=%s count=%d", idea_id, request.count)

    result = await db.execute(select(Idea).where(Idea.id == idea_id, Idea.account_id == account_id))
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    styles = request.styles or ["friendly", "funny", "professional", "luxury", "minimal"]
    variants = []

    from backend.app.ai.llm_client import get_llm_client
    llm = get_llm_client()
    
    for style in styles[:request.count]:
        prompt = f"""Write a {style} caption for a social media post. The post is about: {idea.title}. Hook: {idea.hook or ''}. Keep it under 250 characters, include 4-5 hashtags. Return as plain text with hashtags on a separate line."""
        text = (await llm.complete(prompt)).strip()
        lines = text.split("\n")
        caption = lines[0] if lines else text
        hashtags_line = lines[-1] if len(lines) > 1 and "#" in lines[-1] else ""
        tags = [t.strip() for t in hashtags_line.split() if t.strip().startswith("#")]
        variants.append({
            "style": style,
            "caption_text": caption,
            "hashtags": tags[:5],
            "character_count": len(caption),
        })

    return {"idea_id": idea_id, "variants": variants}


# ── Screen 4: Thumbnail Generation ────────────────────────────────────────────

@router.post("/{account_id}/ideas/{idea_id}/generate-thumbnails")
async def generate_thumbnails_endpoint(
    account_id: str,
    idea_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate thumbnail concepts for an idea (Screen 4)."""
    if not is_feature_enabled("TREND_RECOMMENDATIONS_V2"):
        raise HTTPException(status_code=503, detail="Trend Recommendations V2 is not yet available. Check back soon.")
    logger.info("[ContentSuggestionRoutes] Generating thumbnails for idea=%s", idea_id)

    result = await db.execute(select(Idea).where(Idea.id == idea_id, Idea.account_id == account_id))
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    import uuid

    # Generate 4 thumbnail concepts with different prompts
    labels = [
        f"{idea.title[:25]}",
        f"{idea.title[:20]} Variation",
        f"Clean {idea.title[:20]}",
        f"Bold {idea.title[:18]}",
    ]
    
    prompt_base = f"Social media thumbnail for '{idea.title}'. {idea.hook or ''}. Professional, eye-catching, vibrant colors."
    
    thumbnails = []
    for i, label in enumerate(labels):
        tid = str(uuid.uuid4())[:8]
        prompt = f"{prompt_base} Style variant {i+1}: {'bold typography' if i==0 else 'minimalist' if i==1 else 'colorful gradient' if i==2 else 'dark moody'}"
        thumbnails.append({
            "id": tid,
            "image_url": None,
            "label": label,
            "prompt": prompt,
            "resolution": "1080x1080",
            "status": "concept_only",
        })

    return {"idea_id": idea_id, "thumbnails": thumbnails}


# ── Screen 5: Multi-Collection Save ──────────────────────────────────────────

@router.post("/{account_id}/ideas/{idea_id}/save")
async def multi_save_idea_endpoint(
    account_id: str,
    idea_id: str,
    request: MultiSaveRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Save idea to multiple collections at once (Screen 5)."""
    logger.info("[ContentSuggestionRoutes] Saving idea=%s to %d collections", idea_id, len(request.collection_ids))

    saved = []
    await _get_account_idea_or_404(db, account_id, idea_id)
    for coll_id in request.collection_ids:
        await _get_account_collection_or_404(db, account_id, coll_id)
        existing = await db.execute(
            select(CollectionIdea).where(
                CollectionIdea.collection_id == coll_id,
                CollectionIdea.idea_id == idea_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        junction = CollectionIdea(collection_id=coll_id, idea_id=idea_id)
        db.add(junction)
        saved.append(coll_id)

    await db.commit()
    return {"saved_to": saved, "idea_id": idea_id}


# ── Screen 9: Niche Details ───────────────────────────────────────────────────

@router.get("/{account_id}/niche")
async def get_niche_details(
    account_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get niche analysis for an account (Screen 9)."""
    logger.info("[ContentSuggestionRoutes] Fetching niche for account=%s", account_id)

    # Try to use the account health engine results
    from backend.app.infra.models import Account
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()

    if account and account.niche_category:
        return {
            "primary_niche": account.niche_category,
            "sub_niches": [
                {"name": n, "confidence": account.niche_confidence_score or 0.0}
                for n in (account.sub_niches or [])[:5]
            ],
            "confidence_score": account.niche_confidence_score or 0.0,
            "explanation": account.niche_explanation or "No niche explanation is available yet.",
            "content_style_summary": account.content_style_summary or "No content style summary is available yet.",
            "creator_strengths": account.creator_strengths or [],
        }

    trend_result = await db.get(CreatorTrendResult, account_id)
    niche = trend_result.niche_json if trend_result and isinstance(trend_result.niche_json, dict) else {}
    primary_category = niche.get("primary_category")
    if isinstance(primary_category, str) and primary_category.strip():
        confidence = float(niche.get("confidence_score") or 0.0)
        sub_niches = [name for name in niche.get("sub_niches", []) if isinstance(name, str) and name.strip()]
        return {
            "primary_niche": primary_category,
            "sub_niches": [{"name": name, "confidence": confidence} for name in sub_niches[:5]],
            "confidence_score": confidence,
            "explanation": "Niche detected from the latest trend analysis.",
            "content_style_summary": "No content style summary is available yet.",
            "creator_strengths": [],
        }

    raise HTTPException(status_code=404, detail="Niche analysis is not available yet. Refresh trend analysis first.")


@router.post("/{account_id}/ideas/{idea_id}/regenerate", response_model=RegenerateResponse)
async def regenerate_idea_endpoint(
    account_id: str,
    idea_id: str,
    request: RegenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """Regenerate an idea from scratch."""
    logger.info("[ContentSuggestionRoutes] Regenerating idea=%s", idea_id)
    await _get_account_idea_or_404(db, account_id, idea_id)
    job_id = await asyncio.to_thread(enqueue_idea_regenerate, account_id, idea_id)
    return RegenerateResponse(job_id=job_id, status="processing")


# ── Idea Management (Duplicate, Hide, Delete) ────────────────────────────────


@router.post("/{account_id}/ideas/{idea_id}/duplicate", status_code=201)
async def duplicate_idea_endpoint(
    account_id: str,
    idea_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Duplicate an idea."""
    import uuid

    result = await db.execute(select(Idea).where(Idea.id == idea_id, Idea.account_id == account_id))
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    new_id = str(uuid.uuid4())
    new_idea = Idea(
        id=new_id,
        account_id=account_id,
        parent_idea_id=idea_id,
        title=f"{idea.title} (Copy)",
        description=idea.description,
        hook=idea.hook,
        content_type=idea.content_type,
        platform=idea.platform,
        opportunity_score=idea.opportunity_score,
        expected_reach_min=idea.expected_reach_min,
        expected_reach_max=idea.expected_reach_max,
        expected_views_min=idea.expected_views_min,
        expected_views_max=idea.expected_views_max,
        expected_saves_min=idea.expected_saves_min,
        expected_saves_max=idea.expected_saves_max,
        expected_shares_min=idea.expected_shares_min,
        expected_shares_max=idea.expected_shares_max,
        difficulty=idea.difficulty,
        duration_seconds=idea.duration_seconds,
        best_time_to_post=idea.best_time_to_post,
        trend_reference=idea.trend_reference,
        tags=list(idea.tags) if idea.tags else [],
        status="draft",
    )
    db.add(new_idea)
    await db.commit()

    return {"id": new_id, "title": new_idea.title, "status": "duplicated"}


@router.get("/{account_id}/ideas/{idea_id}")
async def get_idea_detail(
    account_id: str,
    idea_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get full detail for a single idea (Screen 1)."""
    result = await db.execute(
        select(Idea).where(Idea.id == idea_id, Idea.account_id == account_id)
    )
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    return {
        "id": idea.id,
        "account_id": idea.account_id,
        "title": idea.title,
        "description": idea.description,
        "hook": idea.hook,
        "content_type": idea.content_type,
        "platform": idea.platform,
        "opportunity_score": idea.opportunity_score,
        "engagement_score": idea.engagement_score,
        "expected_reach_min": idea.expected_reach_min,
        "expected_reach_max": idea.expected_reach_max,
        "expected_views_min": idea.expected_views_min,
        "expected_views_max": idea.expected_views_max,
        "difficulty": idea.difficulty,
        "duration_seconds": idea.duration_seconds,
        "best_time_to_post": idea.best_time_to_post,
        "trend_reference": idea.trend_reference,
        "tags": idea.tags or [],
        "content_style": (idea.generation_metadata or {}).get("content_style"),
        "rationale": (idea.generation_metadata or {}).get("rationale"),
        "status": idea.status,
        "created_at": idea.created_at.isoformat() if idea.created_at else None,
        "updated_at": idea.updated_at.isoformat() if idea.updated_at else None,
    }


@router.get("/{account_id}/ideas/{idea_id}/reasoning", response_model=IdeaReasoningResponse)
async def get_idea_reasoning(
    account_id: str,
    idea_id: str,
    db: AsyncSession = Depends(get_db),
) -> IdeaReasoningResponse:
    """Get factor breakdown for an idea's opportunity score (Screen 10)."""
    result = await db.execute(
        select(Idea).where(Idea.id == idea_id, Idea.account_id == account_id)
    )
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    score = float(idea.opportunity_score or idea.engagement_score or 75.0)
    factors = _build_reasoning_factors(idea)
    strongest_factor = max(factors, key=lambda item: item["value"])["key"] if factors else None
    weakest_factor = min(factors, key=lambda item: item["value"])["key"] if factors else None
    ai_confidence_pct = _compute_reasoning_confidence(idea, factors)
    percentile_rank = await _compute_idea_percentile_rank(account_id, db, score)
    strongest_phrase = strongest_factor.replace("_", " ") if strongest_factor else "overall fit"
    weakest_phrase = weakest_factor.replace("_", " ") if weakest_factor else "supporting factors"
    timing_phrase = (
        f" A concrete best posting time is available ({idea.best_time_to_post})."
        if isinstance(idea.best_time_to_post, str) and idea.best_time_to_post.strip()
        else " No creator-specific best posting time is stored yet, so timing confidence is lower."
    )
    summary_explanation = (
        f"This idea scores {round(score)}/100 because its strongest signal is {strongest_phrase}, "
        f"while {weakest_phrase} is the main limiter right now.{timing_phrase}"
    )

    return IdeaReasoningResponse(
        idea_id=idea.id,
        opportunity_score=max(0.0, min(100.0, score)),
        factors=factors,
        ai_confidence_pct=ai_confidence_pct,
        percentile_rank=percentile_rank,
        strongest_factor=strongest_factor,
        weakest_factor=weakest_factor,
        summary_explanation=summary_explanation,
    )


@router.patch("/{account_id}/ideas/{idea_id}")
async def update_idea_endpoint(
    account_id: str,
    idea_id: str,
    updates: UpdateIdeaRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update idea fields (content_type, status, etc.)."""
    result = await db.execute(
        select(Idea).where(Idea.id == idea_id, Idea.account_id == account_id)
    )
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    changed: dict[str, Any] = {}
    for key, value in updates.model_dump(exclude_none=True).items():
        if hasattr(idea, key):
            setattr(idea, key, value)
            changed[key] = value

    await db.commit()
    return {"id": idea.id, "status": "updated", "updated": changed}


@router.delete("/{account_id}/ideas/{idea_id}", status_code=204, response_class=Response, response_model=None)
async def delete_idea_endpoint(
    account_id: str,
    idea_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete an idea (set status=deleted)."""
    result = await db.execute(
        select(Idea).where(Idea.id == idea_id, Idea.account_id == account_id)
    )
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    idea.status = "deleted"
    await db.commit()
    return Response(status_code=204)


# ── Collections ────────────────────────────────────────────────────────────────


@router.get("/{account_id}/collections")
async def list_collections_endpoint(
    account_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all collections for an account."""
    stmt = select(Collection).where(Collection.account_id == account_id)
    result = await db.execute(stmt)
    collections = list(result.scalars().all())

    # Get idea counts for each collection
    collection_list = []
    for coll in collections:
        count_stmt = select(func.count()).where(CollectionIdea.collection_id == coll.id)
        count = (await db.execute(count_stmt)).scalar() or 0
        collection_list.append({
            "id": coll.id,
            "name": coll.name,
            "description": coll.description,
            "idea_count": count,
            "created_at": coll.created_at.isoformat() if coll.created_at else None,
        })

    return collection_list


@router.post("/{account_id}/collections", status_code=201)
async def create_collection_endpoint(
    account_id: str,
    request: CreateCollectionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new collection."""
    import uuid
    coll_id = str(uuid.uuid4())
    collection = Collection(
        id=coll_id,
        account_id=account_id,
        name=request.name,
        description=request.description,
    )
    db.add(collection)
    await db.commit()

    return {
        "id": coll_id,
        "name": request.name,
        "description": request.description,
        "idea_count": 0,
    }


@router.post("/{account_id}/collections/{collection_id}/ideas", status_code=201)
async def add_idea_to_collection_endpoint(
    account_id: str,
    collection_id: str,
    request: SaveIdeaRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Add idea to collection."""
    await _get_account_collection_or_404(db, account_id, collection_id)
    await _get_account_idea_or_404(db, account_id, request.idea_id)
    # Check if already exists
    existing = await db.execute(
        select(CollectionIdea).where(
            CollectionIdea.collection_id == collection_id,
            CollectionIdea.idea_id == request.idea_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Idea already in collection")

    import uuid
    junction = CollectionIdea(
        collection_id=collection_id,
        idea_id=request.idea_id,
    )
    db.add(junction)
    await db.commit()

    return {"status": "added"}


@router.delete("/{account_id}/collections/{collection_id}/ideas/{idea_id}", status_code=204, response_class=Response, response_model=None)
async def remove_idea_from_collection_endpoint(
    account_id: str,
    collection_id: str,
    idea_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove idea from collection."""
    await _get_account_collection_or_404(db, account_id, collection_id)
    await _get_account_idea_or_404(db, account_id, idea_id)
    result = await db.execute(
        select(CollectionIdea).where(
            CollectionIdea.collection_id == collection_id,
            CollectionIdea.idea_id == idea_id,
        )
    )
    junction = result.scalar_one_or_none()
    if not junction:
        raise HTTPException(status_code=404, detail="Idea not found in collection")

    await db.delete(junction)
    await db.commit()
    return Response(status_code=204)


@router.get("/{account_id}/ideas/{idea_id}/collections")
async def list_collections_for_idea_endpoint(
    account_id: str,
    idea_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str]]:
    """List collections containing an idea."""
    await _get_account_idea_or_404(db, account_id, idea_id)
    stmt = (
        select(Collection.id, Collection.name)
        .join(CollectionIdea, CollectionIdea.collection_id == Collection.id)
        .where(CollectionIdea.idea_id == idea_id, Collection.account_id == account_id)
    )
    result = await db.execute(stmt)
    return [{"collection_id": row[0], "name": row[1]} for row in result.all()]


# ── Planner / Scheduler ────────────────────────────────────────────────────────


@router.post("/{account_id}/planner/schedule")
async def schedule_idea_endpoint(
    account_id: str,
    request: ScheduleIdeaRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Schedule idea to planner."""
    if not is_feature_enabled("TREND_RECOMMENDATIONS_V2"):
        raise HTTPException(status_code=503, detail="Trend Recommendations V2 is not yet available. Check back soon.")
    logger.info("[ContentSuggestionRoutes] Scheduling idea=%s for %s %s", request.idea_id, request.scheduled_date, request.scheduled_time)
    await _get_account_idea_or_404(db, account_id, request.idea_id)
    emit_event("planner_schedule_clicked", account_id=account_id, properties={"idea_id": request.idea_id, "platform": request.platform, "scheduled_at": f"{request.scheduled_date}T{request.scheduled_time}"})

    from datetime import datetime

    scheduled_at = datetime.fromisoformat(f"{request.scheduled_date}T{request.scheduled_time}")

    # Check for conflicts (same platform within 30 minutes)
    conflict_stmt = select(ScheduledItem).where(
        ScheduledItem.account_id == account_id,
        ScheduledItem.platform == request.platform,
    )
    result = await db.execute(conflict_stmt)
    existing_items = list(result.scalars().all())

    conflicts = []
    for item in existing_items:
        time_diff = abs((item.scheduled_at - scheduled_at).total_seconds())
        if time_diff < 1800:  # 30 minutes
            conflicts.append(item)

    if conflicts and request.conflict_resolution == "reject":
        # Find next available slot
        next_slot = scheduled_at
        while any(abs((item.scheduled_at - next_slot).total_seconds()) < 1800 for item in existing_items):
            next_slot = next_slot.replace(minute=next_slot.minute + 30)

        return {
            "status": "conflict",
            "conflicting_items": [
                {
                    "id": item.id,
                    "scheduled_time": item.scheduled_at.strftime("%H:%M"),
                    "platform": item.platform,
                }
                for item in conflicts
            ],
            "suggestion": f"Next available slot: {next_slot.strftime('%H:%M')} on {request.scheduled_date}",
            "available_slots": [next_slot.strftime("%H:%M")],
        }

    # Create scheduled item
    import uuid
    item = ScheduledItem(
        id=str(uuid.uuid4()),
        account_id=account_id,
        idea_id=request.idea_id,
        platform=request.platform,
        scheduled_at=scheduled_at,
        conflict_acknowledged=bool(conflicts) and request.conflict_resolution == "warn",
        )
    db.add(item)
    await db.commit()

    emit_event("planner_schedule_succeeded", account_id=account_id, properties={"idea_id": request.idea_id, "scheduled_at": item.scheduled_at.isoformat()})
    return {
        "status": "scheduled",
        "scheduled_item": {
            "id": item.id,
            "idea_id": item.idea_id,
            "platform": item.platform,
            "scheduled_at": item.scheduled_at.isoformat(),
        },
    }


@router.delete("/{account_id}/planner/schedule/{item_id}", status_code=204, response_class=Response, response_model=None)
async def unschedule_item_endpoint(
    account_id: str,
    item_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Unschedule item."""
    result = await db.execute(
        select(ScheduledItem).where(
            ScheduledItem.id == item_id,
            ScheduledItem.account_id == account_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Scheduled item not found")

    await db.delete(item)
    await db.commit()
    return Response(status_code=204)


@router.get("/{account_id}/planner/calendar")
async def get_planner_calendar(
    account_id: str,
    week_start: str = Query(None, description="ISO date for Monday of the week"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get 7-day calendar view with scheduled items (Screen 6)."""
    from datetime import datetime, timedelta, timezone

    if week_start:
        monday = datetime.fromisoformat(week_start).replace(tzinfo=timezone.utc)
    else:
        today = datetime.now(timezone.utc)
        monday = today - timedelta(days=today.weekday())
        monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)

    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

    stmt = select(ScheduledItem).where(
        ScheduledItem.account_id == account_id,
        ScheduledItem.scheduled_at >= monday,
        ScheduledItem.scheduled_at <= sunday,
    ).order_by(ScheduledItem.scheduled_at)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    # Build day buckets
    days = []
    for offset in range(7):
        day_date = monday + timedelta(days=offset)
        day_start = day_date.replace(hour=0, minute=0, second=0)
        day_end = day_date.replace(hour=23, minute=59, second=59)
        day_items = [
            {
                "id": item.id,
                "idea_id": item.idea_id,
                "platform": item.platform,
                "scheduled_at": item.scheduled_at.isoformat(),
                "conflict": item.conflict_acknowledged,
                "status": item.status,
            }
            for item in items
            if day_start <= item.scheduled_at <= day_end
        ]
        days.append({
            "date": day_date.strftime("%Y-%m-%d"),
            "day_name": day_date.strftime("%a"),
            "day_number": day_date.day,
            "items": day_items,
        })

    return {
        "week_start": monday.strftime("%Y-%m-%d"),
        "week_end": sunday.strftime("%Y-%m-%d"),
        "days": days,
    }


@router.patch("/{account_id}/planner/{schedule_id}")
async def move_scheduled_item(
    account_id: str,
    schedule_id: str,
    updates: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Move/reschedule a planned item (Screen 6 drag-and-drop)."""
    from datetime import datetime

    result = await db.execute(
        select(ScheduledItem).where(
            ScheduledItem.id == schedule_id,
            ScheduledItem.account_id == account_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Scheduled item not found")

    if "scheduled_at" in updates:
        item.scheduled_at = datetime.fromisoformat(updates["scheduled_at"])
    if "platform" in updates:
        item.platform = updates["platform"]
    if "status" in updates:
        item.status = updates["status"]

        from datetime import datetime, timezone
    if "scheduled_at" in updates or "platform" in updates or "status" in updates:
        pass  # item was already updated above
    await db.commit()

    return {
        "id": item.id,
        "idea_id": item.idea_id,
        "platform": item.platform,
        "scheduled_at": item.scheduled_at.isoformat(),
        "status": item.status,
    }


@router.get("/{account_id}/planner")
async def get_planner_endpoint(
    account_id: str,
    week_start: str = Query(...),
    platform: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get weekly planner view."""
    from datetime import datetime, timedelta

    start_date = datetime.fromisoformat(week_start)

    stmt = select(ScheduledItem).where(
        ScheduledItem.account_id == account_id,
        ScheduledItem.scheduled_at >= start_date,
        ScheduledItem.scheduled_at < start_date + timedelta(days=7),
    )
    if platform:
        stmt = stmt.where(ScheduledItem.platform == platform)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    # Group by date
    days = []
    for i in range(7):
        day_date = start_date + timedelta(days=i)
        day_items = [
            {
                "id": item.id,
                "idea_id": item.idea_id,
                "platform": item.platform,
                "scheduled_at": item.scheduled_at.strftime("%H:%M"),
                "status": "scheduled",
            }
            for item in items
            if item.scheduled_at.date() == day_date.date()
        ]
        days.append({
            "date": day_date.strftime("%Y-%m-%d"),
            "items": day_items,
        })

    return {
        "week_start": week_start,
        "days": days,
    }


# ── AI Assistant ───────────────────────────────────────────────────────────────


@router.get("/{account_id}/activity")
async def get_activity_history(
    account_id: str,
    type: str = Query("all", description="Filter: all, generated, scheduled, published"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get chronological activity log (Screen 13)."""
    from datetime import datetime, timedelta, timezone

    stmt = select(Idea).where(Idea.account_id == account_id)
    if type == "generated":
        stmt = stmt.where(Idea.status == "generated")
    elif type == "scheduled":
        stmt = stmt.where(Idea.status == "scheduled")
    elif type == "published":
        stmt = stmt.where(Idea.status == "published")

    stmt = stmt.order_by(Idea.created_at.desc()).offset(offset).limit(limit)
    total_stmt = select(func.count(Idea.id)).where(Idea.account_id == account_id)

    result = await db.execute(stmt)
    total_result = await db.execute(total_stmt)
    ideas = list(result.scalars().all())
    total = total_result.scalar() or 0

    activity = []
    for idea in ideas:
        action = "Generated" if idea.status == "generated" else idea.status or "Created"
        activity.append({
            "id": idea.id,
            "title": idea.title,
            "action": action,
            "status": idea.status or "generated",
            "created_at": idea.created_at.isoformat() if idea.created_at else None,
            "tags": idea.tags or [],
        })

    return {
        "activity": activity,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{account_id}/notifications")
async def get_notifications(
    account_id: str,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get in-app notifications (Screen 17)."""
    # Notifications are derived from recent job completions + scheduled items
    from datetime import datetime, timedelta, timezone

    notifications = []

    # 1. Recent completed generation jobs
    jobs_stmt = (
        select(IdeaGenerationJob)
        .where(IdeaGenerationJob.account_id == account_id)
        .order_by(IdeaGenerationJob.completed_at.desc().nullslast())
        .limit(5)
    )
    jobs_result = await db.execute(jobs_stmt)
    for job in jobs_result.scalars().all():
        if job.status == "completed" and job.completed_at:
            notifications.append({
                "id": f"job-{job.id}",
                "type": "generation_complete",
                "title": f"{job.result_count or 0} ideas generated",
                "body": "Your content ideas are ready to review",
                "created_at": job.completed_at.isoformat(),
                "read": False,
            })

    # 2. Upcoming scheduled items (next 24h)
    soon = datetime.now(timezone.utc) + timedelta(hours=24)
    sched_stmt = (
        select(ScheduledItem)
        .where(
            ScheduledItem.account_id == account_id,
            ScheduledItem.scheduled_at >= datetime.now(timezone.utc),
            ScheduledItem.scheduled_at <= soon,
        )
        .order_by(ScheduledItem.scheduled_at.asc())
        .limit(5)
    )
    sched_result = await db.execute(sched_stmt)
    for item in sched_result.scalars().all():
        notifications.append({
            "id": f"sched-{item.id}",
            "type": "idea_scheduled",
            "title": "Idea scheduled",
            "body": f"Scheduled for {item.scheduled_at.strftime('%b %d at %I:%M %p')}",
            "created_at": item.scheduled_at.isoformat(),
            "read": False,
            "scheduled_at": item.scheduled_at.isoformat(),
        })

    # Sort by newest first, limit
    notifications.sort(key=lambda n: n["created_at"], reverse=True)
    notifications = notifications[:limit]

    return {
        "notifications": notifications,
        "unread_count": len([n for n in notifications if not n.get("read")]),
    }


@router.patch("/{account_id}/notifications/read-all")
async def mark_all_notifications_read(
    account_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Mark all notifications as read (Screen 17)."""
    # In-memory only — notifications are ephemeral and derived from events
    return {"status": "ok"}


@router.patch("/{account_id}/notifications/{notification_id}/read")
async def mark_notification_read(
    account_id: str,
    notification_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Mark a single notification as read (Screen 17)."""
    return {"status": "ok"}


@router.post("/{account_id}/trends/ai-assistant", response_model=AssistantResponse)
async def ai_assistant_endpoint(
    account_id: str,
    request: AssistantRequest,
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Chat with AI assistant."""
    logger.info("[ContentSuggestionRoutes] AI assistant message for account=%s", account_id)

    result = await db.execute(
        select(CreatorTrendResult).where(CreatorTrendResult.account_id == account_id)
    )
    trend_result = result.scalar_one_or_none()
    trends = (trend_result.global_trends_json or []) if trend_result else []
    recommendations = (trend_result.recommendations_json or []) if trend_result else []

    context = {
        "trends": trends[:5],
        "recommendations": recommendations[:5],
        "user_context": request.context or {},
    }
    prompt = {
        "system": (
            "You are a creator strategy assistant. Answer only from the supplied account trend context. "
            "If there is insufficient context, say so plainly and ask the user to refresh analysis. "
            "Do not invent trend names, performance figures, or Instagram data. Keep the answer concise."
        ),
        "user": f"Account context: {context}\n\nCreator question: {request.message}",
    }
    try:
        from backend.app.ai.llm_client import LLMClient

        reply = await asyncio.to_thread(LLMClient(temperature=0.4, max_tokens=350).generate, prompt)
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("Empty assistant response")
    except Exception as exc:
        logger.exception("[ContentSuggestionRoutes] AI assistant failed for account=%s", account_id)
        raise HTTPException(status_code=503, detail="The AI assistant is unavailable. Please try again shortly.") from exc

    return AssistantResponse(reply=reply.strip(), suggested_ideas=None)
