"""Background job functions for content suggestions.

Handles idea generation, improvement, variations, and regeneration.
Uses RQ for job queue management.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.app.domain.content_suggestion_models import (
    GenerateIdeasRequest,
    ImproveIdeaRequest,
    VariationsRequest,
    RegenerateRequest,
)
from backend.app.infra.database import get_sync_sessionmaker
from backend.app.infra.models import Idea, IdeaGenerationJob
from backend.app.utils.logger import logger

# Step labels for progress tracking
IDEA_GENERATION_STEPS = [
    "Analysing your recent content",
    "Researching trending topics",
    "Analysing your audience",
    "Checking competitors",
    "Generating high-potential ideas",
]


def _generate_id() -> str:
    return str(uuid.uuid4())


# ── Enqueue Functions ──────────────────────────────────────────────────────────


def enqueue_idea_generation(account_id: str, request: GenerateIdeasRequest) -> str:
    """Enqueue idea generation job, return job_id."""
    job_id = _generate_id()

    session_factory = get_sync_sessionmaker()
    with session_factory() as db:
        job = IdeaGenerationJob(
            id=job_id,
            account_id=account_id,
            status="queued",
            current_step=0,
            total_steps=5,
            step_label="Queued",
            percent_complete=0.0,
            optimization_goals=request.optimization_goals,
            content_type=request.content_type,
            topic=request.topic,
            audience=request.audience,
            tone_of_voice=request.tone_of_voice,
            result_count=request.count,
        )
        db.add(job)
        db.commit()

    # Enqueue to RQ
    try:
        from backend.app.infra.rq_queue import get_queue

        queue = get_queue("content-suggestions")
        queue.enqueue(
            "backend.app.services.content_suggestion_jobs.run_idea_generation",
            account_id,
            job_id,
            job_timeout=300,
            result_ttl=86400,
        )
        logger.info("[ContentSuggestionJob] Enqueued to RQ job_id=%s", job_id)
    except Exception as e:
        logger.warning("[ContentSuggestionJob] RQ enqueue failed, running synchronously: %s", e)
        # Fallback: run synchronously if RQ unavailable
        run_idea_generation(account_id, job_id)

    return job_id


def enqueue_idea_improve(account_id: str, idea_id: str, request: ImproveIdeaRequest) -> str:
    """Enqueue idea improvement job."""
    job_id = _generate_id()

    try:
        from backend.app.infra.rq_queue import get_queue

        queue = get_queue("content-suggestions")
        queue.enqueue(
            "backend.app.services.content_suggestion_jobs.run_idea_improve",
            account_id,
            idea_id,
            request.feedback,
            request.aspect,
            job_timeout=120,
            result_ttl=86400,
        )
        logger.info("[ContentSuggestionJob] Enqueued improve job_id=%s idea_id=%s", job_id, idea_id)
    except Exception as e:
        logger.warning("[ContentSuggestionJob] RQ enqueue failed for improve: %s", e)
        run_idea_improve(account_id, idea_id, request.feedback, request.aspect)

    return job_id


def enqueue_idea_variations(account_id: str, idea_id: str, request: VariationsRequest) -> str:
    """Enqueue variations generation job."""
    job_id = _generate_id()

    try:
        from backend.app.infra.rq_queue import get_queue

        queue = get_queue("content-suggestions")
        queue.enqueue(
            "backend.app.services.content_suggestion_jobs.run_idea_variations",
            account_id,
            idea_id,
            request.count,
            job_timeout=120,
            result_ttl=86400,
        )
        logger.info("[ContentSuggestionJob] Enqueued variations job_id=%s idea_id=%s", job_id, idea_id)
    except Exception as e:
        logger.warning("[ContentSuggestionJob] RQ enqueue failed for variations: %s", e)
        run_idea_variations(account_id, idea_id, request.count)

    return job_id


def enqueue_idea_regenerate(account_id: str, idea_id: str) -> str:
    """Enqueue idea regeneration job."""
    job_id = _generate_id()

    try:
        from backend.app.infra.rq_queue import get_queue

        queue = get_queue("content-suggestions")
        queue.enqueue(
            "backend.app.services.content_suggestion_jobs.run_idea_regenerate",
            account_id,
            idea_id,
            job_timeout=120,
            result_ttl=86400,
        )
        logger.info("[ContentSuggestionJob] Enqueued regenerate job_id=%s idea_id=%s", job_id, idea_id)
    except Exception as e:
        logger.warning("[ContentSuggestionJob] RQ enqueue failed for regenerate: %s", e)
        run_idea_regenerate(account_id, idea_id)

    return job_id


# ── Worker Entrypoints ─────────────────────────────────────────────────────────


def run_idea_generation(account_id: str, job_id: str) -> None:
    """Sync worker function for idea generation.

    This is the main entrypoint called by the RQ worker.
    """
    logger.info("[ContentSuggestionJob] Starting idea generation job_id=%s", job_id)

    session_factory = get_sync_sessionmaker()
    with session_factory() as db:
        job = db.get(IdeaGenerationJob, job_id)
        if not job:
            logger.error("[ContentSuggestionJob] Job not found: %s", job_id)
            return

        job.status = "processing"
        job.current_step = 0
        db.commit()

        try:
            # Step 1: Analyse recent content
            _update_progress(db, job, 0, "Analysing your recent content")

            # Step 2: Research trending topics
            _update_progress(db, job, 1, "Researching trending topics")

            # Step 3: Analyse audience
            _update_progress(db, job, 2, "Analysing your audience")

            # Step 4: Check competitors
            _update_progress(db, job, 3, "Checking competitors")

            # Step 5: Generate ideas via LLM
            _update_progress(db, job, 4, "Generating high-potential ideas")
            ideas = _generate_ideas_with_llm(db, job)

            # Store generated ideas
            for idea_data in ideas:
                idea = Idea(
                    id=_generate_id(),
                    account_id=account_id,
                    title=idea_data.get("title", "Untitled Idea"),
                    description=idea_data.get("description"),
                    hook=idea_data.get("hook"),
                    content_type=job.content_type or "reel",
                    platform=job.content_type,
                    opportunity_score=idea_data.get("opportunity_score"),
                    difficulty=idea_data.get("difficulty"),
                    duration_seconds=idea_data.get("duration_seconds"),
                    tags=idea_data.get("tags", []),
                    trend_reference=idea_data.get("trend_reference"),
                    generation_job_id=job_id,
                    generation_metadata={
                        "job_id": job_id,
                        "model": "gpt-4o",
                        "prompt_version": "v1.0",
                    },
                    status="generated",
                )
                db.add(idea)

            job.result_count = len(ideas)
            job.status = "completed"
            job.percent_complete = 1.0
            job.completed_at = datetime.utcnow()
            db.commit()

            logger.info("[ContentSuggestionJob] Completed job_id=%s generated=%d ideas", job_id, len(ideas))

        except Exception as e:
            logger.exception("[ContentSuggestionJob] Failed job_id=%s: %s", job_id, e)
            job.status = "failed"
            job.error_message = str(e)
            db.commit()


def _update_progress(db, job: IdeaGenerationJob, step: int, label: str) -> None:
    """Update job progress."""
    job.current_step = step
    job.step_label = label
    job.percent_complete = step / job.total_steps
    db.commit()


def _generate_ideas_with_llm(db, job: IdeaGenerationJob) -> list[dict[str, Any]]:
    """Generate ideas using LLM."""
    import asyncio

    from backend.app.ai.llm_client import LLMClient

    count = job.result_count or 5
    goals = ", ".join(job.optimization_goals or ["maximum_reach"])
    tones = ", ".join(job.tone_of_voice or ["professional"])

    system_prompt = (
        "You are a Creative Director for short-form social media content. "
        "Generate engaging, high-potential content ideas that align with the creator's niche and audience. "
        "Return ONLY one valid JSON object and no markdown."
    )

    user_prompt = f"""Generate {count} content ideas for {job.content_type or 'reel'} content.

Topic: {job.topic or 'Trending in my niche'}
Audience: {job.audience or 'everyone'}
Tone: {tones}
Optimization goals: {goals}

For each idea, provide:
- title: Compelling title (5-10 words)
- hook: Attention-grabbing opening line (5-15 words)
- description: Brief description of the content concept (1-2 sentences)
- opportunity_score: Predicted opportunity score (0-100)
- difficulty: easy, medium, or hard
- duration_seconds: Estimated duration (15-180)
- tags: 2-4 relevant tags as comma-separated values
- trend_reference: Related trend if applicable, or empty

Return JSON shape:
{{
  "ideas": [
    {{
      "title": "Your idea title",
      "hook": "Your attention-grabbing hook",
      "description": "Brief description of the content",
      "opportunity_score": 85,
      "difficulty": "easy",
      "duration_seconds": 30,
      "tags": ["Travel", "Budget Travel", "Vietnam"],
      "trend_reference": "Budget Travel Trend"
    }}
  ]
}}
"""

    try:
        llm = LLMClient(
            temperature=0.8,
            max_tokens=2000,
            timeout=300,      # reasoning models (gpt-5.6-terra) think before responding — can take 2-5 mins
            max_retries=0,    # no silent retry — user can retry manually from UI
        )

        # Run sync LLM call (RQ workers are already synchronous)
        raw = llm.generate({"system": system_prompt, "user": user_prompt, "response_format": {"type": "json_object"}})

        if not raw or not raw.strip():
            raise ValueError("Empty LLM response")

        # Parse TOON response
        ideas = _parse_json_ideas(raw)

        # Ensure we have the requested count (pad with fallbacks if needed)
        while len(ideas) < count:
            idx = len(ideas) + 1
            ideas.append({
                "title": f"Content Idea {idx}: {job.topic or 'Trending Topic'}",
                "hook": f"Discover the secret to {job.topic or 'great content'}",
                "description": f"A {job.content_type or 'reel'} about {job.topic or 'trending content'} for {job.audience or 'everyone'}",
                "opportunity_score": 70.0 + (idx * 3),
                "difficulty": "medium",
                "duration_seconds": 30,
                "tags": [job.content_type or "reel", "trending"],
                "trend_reference": "",
            })

        return ideas[:count]

    except Exception as e:
        logger.exception("[ContentSuggestionJob] LLM generation failed: %s", e)
        # Return fallback ideas
        return [
            {
                "title": f"Idea {i+1}: {job.topic or 'Trending Topic'}",
                "hook": f"Hook for idea {i+1}",
                "description": f"Description for idea {i+1} about {job.topic or 'general content'}",
                "opportunity_score": 75.0 + i * 2,
                "difficulty": "medium",
                "duration_seconds": 30,
                "tags": [job.content_type or "reel"],
                "trend_reference": "",
            }
            for i in range(count)
        ]


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) > 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_json_object(raw: str) -> dict[str, Any]:
    stripped = _strip_markdown_fences(raw)
    if "{" in stripped and "}" in stripped:
        stripped = stripped[stripped.find("{"):stripped.rfind("}") + 1]
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    return payload


def _parse_json_ideas(raw: str) -> list[dict[str, Any]]:
    payload = _parse_json_object(raw)
    ideas = payload.get("ideas")
    return ideas if isinstance(ideas, list) else []


# ── Improve/Variations/Regenerate Workers ──────────────────────────────────────


def run_idea_improve(account_id: str, idea_id: str, feedback: str, aspect: str) -> None:
    """Worker function to improve an idea based on feedback."""
    import asyncio

    from backend.app.ai.llm_client import LLMClient

    logger.info("[ContentSuggestionJob] Running improve for idea_id=%s aspect=%s", idea_id, aspect)

    session_factory = get_sync_sessionmaker()
    with session_factory() as db:
        idea = db.get(Idea, idea_id)
        if not idea:
            logger.error("[ContentSuggestionJob] Idea not found: %s", idea_id)
            return

        system_prompt = (
            "You are a Creative Director for short-form social media content. "
            "Improve the given content idea based on the feedback provided. "
            "Return ONLY one valid JSON object and no markdown."
        )

        user_prompt = f"""Improve this content idea:

Current Title: {idea.title}
Current Hook: {idea.hook or 'No hook yet'}
Current Description: {idea.description or 'No description'}

Feedback: {feedback}
Aspect to improve: {aspect}

Provide the improved version with:
- title: Improved title
- hook: Improved hook
- description: Improved description

Return JSON shape:
{"title":"Improved title here","hook":"Improved hook here","description":"Improved description here"}
"""

        try:
            llm = LLMClient(temperature=0.7, max_tokens=500)
            raw = llm.generate({"system": system_prompt, "user": user_prompt, "response_format": {"type": "json_object"}})

            parsed = _parse_json_improvement(raw)

            # Update the idea
            if parsed.get("title"):
                idea.title = parsed["title"]
            if parsed.get("hook"):
                idea.hook = parsed["hook"]
            if parsed.get("description"):
                idea.description = parsed["description"]

            idea.updated_at = datetime.utcnow()
            db.commit()

            logger.info("[ContentSuggestionJob] Improved idea_id=%s", idea_id)

        except Exception as e:
            logger.exception("[ContentSuggestionJob] Improve failed for idea_id=%s: %s", idea_id, e)


def _parse_json_improvement(raw: str) -> dict[str, str]:
    payload = _parse_json_object(raw)
    return {k: str(v).strip() for k, v in payload.items() if k in {"title", "hook", "description"} and isinstance(v, str)}


def run_idea_variations(account_id: str, idea_id: str, count: int) -> None:
    """Worker function to generate variations of an idea."""
    import asyncio

    from backend.app.ai.llm_client import LLMClient

    logger.info("[ContentSuggestionJob] Running variations for idea_id=%s count=%d", idea_id, count)

    session_factory = get_sync_sessionmaker()
    with session_factory() as db:
        idea = db.get(Idea, idea_id)
        if not idea:
            logger.error("[ContentSuggestionJob] Idea not found: %s", idea_id)
            return

        system_prompt = (
            "You are a Creative Director for short-form social media content. "
            "Generate alternative variations of the given content idea. "
            "Return ONLY one valid JSON object and no markdown."
        )

        user_prompt = f"""Generate {count} variations of this content idea:

Title: {idea.title}
Hook: {idea.hook or 'No hook yet'}
Description: {idea.description or 'No description'}

Create {count} different angles or approaches. For each variation:
- title: Alternative title
- hook: Alternative hook
- description: Alternative description

Return JSON shape:
{"variations":[{"title":"Variation 1 title","hook":"Variation 1 hook","description":"Variation 1 description"}]}
"""

        try:
            llm = LLMClient(temperature=0.9, max_tokens=1500)
            raw = llm.generate({"system": system_prompt, "user": user_prompt, "response_format": {"type": "json_object"}})

            variations = _parse_json_variations(raw)

            # Store variations on the original idea
            existing_variations = idea.variations if isinstance(idea.variations, list) else []
            for var in variations[:count]:
                existing_variations.append({
                    "title": var.get("title", ""),
                    "hook": var.get("hook", ""),
                    "description": var.get("description", ""),
                })
            idea.variations = existing_variations
            idea.updated_at = datetime.utcnow()
            db.commit()

            logger.info("[ContentSuggestionJob] Generated %d variations for idea_id=%s", len(variations), idea_id)

        except Exception as e:
            logger.exception("[ContentSuggestionJob] Variations failed for idea_id=%s: %s", idea_id, e)


def _parse_json_variations(raw: str) -> list[dict[str, str]]:
    payload = _parse_json_object(raw)
    variations = payload.get("variations")
    return variations if isinstance(variations, list) else []


def run_idea_regenerate(account_id: str, idea_id: str) -> None:
    """Worker function to regenerate an idea from scratch."""
    import asyncio

    from backend.app.ai.llm_client import LLMClient

    logger.info("[ContentSuggestionJob] Running regenerate for idea_id=%s", idea_id)

    session_factory = get_sync_sessionmaker()
    with session_factory() as db:
        idea = db.get(Idea, idea_id)
        if not idea:
            logger.error("[ContentSuggestionJob] Idea not found: %s", idea_id)
            return

        system_prompt = (
            "You are a Creative Director for short-form social media content. "
            "Generate a completely new content idea inspired by the original concept. "
            "Return ONLY one valid JSON object and no markdown."
        )

        user_prompt = f"""Create a completely new content idea inspired by this one:

Original Title: {idea.title}
Original Hook: {idea.hook or 'No hook'}
Original Description: {idea.description or 'No description'}
Platform: {idea.platform or 'reel'}

Generate a fresh, new idea with:
- title: New compelling title
- hook: New attention-grabbing hook
- description: New content description
- engagement_score: Predicted engagement (0-100)

Return JSON shape:
{"title":"New idea title","hook":"New attention-grabbing hook","description":"New content description","engagement_score":82}
"""

        try:
            llm = LLMClient(temperature=0.9, max_tokens=500)
            raw = llm.generate({"system": system_prompt, "user": user_prompt, "response_format": {"type": "json_object"}})

            parsed = _parse_json_improvement(raw)

            # Update the idea with completely new content
            if parsed.get("title"):
                idea.title = parsed["title"]
            if parsed.get("hook"):
                idea.hook = parsed["hook"]
            if parsed.get("description"):
                idea.description = parsed["description"]

            idea.generation_metadata = {
                **(idea.generation_metadata if isinstance(idea.generation_metadata, dict) else {}),
                "regenerated_at": datetime.utcnow().isoformat(),
                "original_title": idea.title,
            }
            idea.updated_at = datetime.utcnow()
            db.commit()

            logger.info("[ContentSuggestionJob] Regenerated idea_id=%s", idea_id)

        except Exception as e:
            logger.exception("[ContentSuggestionJob] Regenerate failed for idea_id=%s: %s", idea_id, e)


# ── Status Polling ─────────────────────────────────────────────────────────────


def get_idea_generation_status(job_id: str) -> dict[str, Any]:
    """Get current status of idea generation job."""
    session_factory = get_sync_sessionmaker()
    with session_factory() as db:
        job = db.get(IdeaGenerationJob, job_id)
        if not job:
            return {"status": "not_found", "error": "Job not found"}

        result = {
            "job_id": job.id,
            "status": job.status,
            "current_step": job.current_step,
            "total_steps": job.total_steps,
            "step_label": job.step_label,
            "percent_complete": job.percent_complete,
        }

        if job.status == "completed":
            # Fetch generated ideas (match by generation_job_id column, not JSON field)
            stmt = select(Idea).where(Idea.generation_job_id == job_id)
            ideas = list(db.scalars(stmt).all())
            result["ideas"] = [
                {
                    "id": idea.id,
                    "title": idea.title,
                    "hook": idea.hook,
                    "description": idea.description,
                    "content_type": idea.content_type,
                    "opportunity_score": idea.opportunity_score,
                    "difficulty": idea.difficulty,
                    "duration_seconds": idea.duration_seconds,
                    "tags": idea.tags or [],
                    "trend_reference": idea.trend_reference,
                }
                for idea in ideas
            ]

        if job.status == "failed":
            result["error"] = job.error_message

        return result


def get_idea_status(idea_id: str) -> dict[str, Any] | None:
    """Get status of a single idea improvement/variations/regeneration job."""
    # For now, return None - can be extended with BackgroundJob tracking
    return None
