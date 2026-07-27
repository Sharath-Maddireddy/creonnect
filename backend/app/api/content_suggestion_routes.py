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
    ImproveIdeaRequest,
    ImproveIdeaResponse,
    PaginatedIdeasResponse,
    PaginationMeta,
    PlannerResponse,
    DaySchedule,
    RegenerateRequest,
    RegenerateResponse,
    SaveIdeaRequest,
    ScheduleIdeaRequest,
    ScheduledItemResponse,
    VariationsRequest,
    VariationsResponse,
    AssistantRequest,
    AssistantResponse,
)
from backend.app.infra.database import get_db
from backend.app.infra.models import (
    Collection,
    CollectionIdea,
    Idea,
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

router = APIRouter(prefix="/api/v1/accounts", tags=["content-suggestions"])


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
    idea_result = await db.execute(select(Idea).where(Idea.id == request.idea_id))
    idea = idea_result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    from backend.app.services.script_generator import generate_script

    response = await generate_script(
        idea_id=request.idea_id,
        title=idea.title,
        hook=idea.hook,
        script_type=request.script_type,
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
    idea_result = await db.execute(select(Idea).where(Idea.id == request.idea_id))
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
    job_id = await asyncio.to_thread(enqueue_idea_variations, account_id, idea_id, request)
    return VariationsResponse(job_id=job_id, status="processing")


@router.post("/{account_id}/ideas/{idea_id}/regenerate", response_model=RegenerateResponse)
async def regenerate_idea_endpoint(
    account_id: str,
    idea_id: str,
    request: RegenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> RegenerateResponse:
    """Regenerate an idea from scratch."""
    logger.info("[ContentSuggestionRoutes] Regenerating idea=%s", idea_id)
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

    result = await db.execute(select(Idea).where(Idea.id == idea_id))
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


@router.patch("/{account_id}/ideas/{idea_id}")
async def update_idea_endpoint(
    account_id: str,
    idea_id: str,
    updates: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update idea fields (content_type, status, etc.)."""
    result = await db.execute(
        select(Idea).where(Idea.id == idea_id, Idea.account_id == account_id)
    )
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    # Only allow updating specific fields
    allowed_fields = {"content_type", "status", "title", "hook", "description", "tags"}
    for key, value in updates.items():
        if key in allowed_fields and hasattr(idea, key):
            setattr(idea, key, value)

    await db.commit()
    return {"id": idea.id, "status": "updated"}


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
    stmt = (
        select(Collection.id, Collection.name)
        .join(CollectionIdea, CollectionIdea.collection_id == Collection.id)
        .where(CollectionIdea.idea_id == idea_id)
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


@router.post("/{account_id}/trends/ai-assistant", response_model=AssistantResponse)
async def ai_assistant_endpoint(
    account_id: str,
    request: AssistantRequest,
    db: AsyncSession = Depends(get_db),
) -> AssistantResponse:
    """Chat with AI assistant."""
    logger.info("[ContentSuggestionRoutes] AI assistant message for account=%s", account_id)

    # TODO: Implement actual LLM chat with context
    reply = f"I received your message: '{request.message}'. This is a placeholder response. The AI assistant will be implemented with full LLM integration."

    return AssistantResponse(reply=reply, suggested_ideas=None)
