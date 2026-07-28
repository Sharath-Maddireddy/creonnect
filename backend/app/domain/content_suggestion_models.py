"""Pydantic models for content suggestions feature."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Idea Generation ────────────────────────────────────────────────────────────


class GenerateIdeasRequest(BaseModel):
    """Request to generate new content ideas."""

    model_config = ConfigDict(extra="forbid")

    optimization_goals: list[str] = Field(
        default=["maximum_reach"],
        description="Optimization goals: maximum_reach, followers, engagement, brand_deals, saves, product_sales",
    )
    content_type: str = Field(
        default="reel",
        description="Content type: reel, carousel, photo",
    )
    topic: str | None = Field(
        default=None,
        description="Optional topic focus for idea generation",
    )
    audience: str = Field(
        default="everyone",
        description="Target audience: everyone, 18-24, 25-34, 35-44, 45+, gen_z, millennials",
    )
    tone_of_voice: list[str] = Field(
        default=["professional"],
        description="Tone of voice: professional, funny, storytelling, luxury, educational",
    )
    count: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of ideas to generate (1-10)",
    )


class GenerateIdeasResponse(BaseModel):
    """Response when idea generation job is started."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: str
    estimated_seconds: int


class IdeaGenerationProgress(BaseModel):
    """Current progress of idea generation job."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: str  # queued | processing | completed | failed
    current_step: int
    total_steps: int
    step_label: str | None = None
    percent_complete: float
    ideas: list[dict[str, Any]] | None = None  # populated when completed
    error: str | None = None


# ── Pagination ─────────────────────────────────────────────────────────────────


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    model_config = ConfigDict(extra="forbid")

    page: int
    per_page: int
    total_count: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PaginatedIdeasResponse(BaseModel):
    """Paginated list of ideas."""

    model_config = ConfigDict(extra="forbid")

    data: list[dict[str, Any]]
    meta: PaginationMeta


# ── Script Generation ──────────────────────────────────────────────────────────


class GenerateScriptRequest(BaseModel):
    """Request to generate a script for an idea."""

    model_config = ConfigDict(extra="forbid")

    idea_id: str
    script_type: str = Field(
        default="viral",
        description="Script type: viral, natural, story",
    )
    tone: str = Field(
        default="friendly",
        description="Tone: friendly, professional, funny",
    )
    language: str = Field(
        default="en",
        description="Language code: en, hi, es, etc.",
    )
    duration_seconds: int = Field(
        default=60,
        ge=15,
        le=180,
        description="Target duration in seconds",
    )


class Scene(BaseModel):
    """A scene in a generated script."""

    model_config = ConfigDict(extra="forbid")

    scene_number: int
    time_range: str
    description: str
    visual_notes: str | None = None


class GenerateScriptResponse(BaseModel):
    """Generated script result."""

    model_config = ConfigDict(extra="forbid")

    idea_id: str
    hook: str
    scenes: list[Scene]
    cta: str
    estimated_duration_sec: int
    full_script: str


# ── Caption Generation ─────────────────────────────────────────────────────────


class GenerateCaptionRequest(BaseModel):
    """Request to generate captions for an idea."""

    model_config = ConfigDict(extra="forbid")

    idea_id: str
    script_id: str | None = None
    platforms: list[str] = Field(
        default=["instagram"],
        description="Platforms to generate captions for",
    )
    tone: str = Field(default="friendly")
    language: str = Field(default="en")
    include_hashtags: bool = Field(default=True)
    max_hashtags: int = Field(default=10, ge=0, le=30)


class GeneratedCaption(BaseModel):
    """A caption for a specific platform."""

    model_config = ConfigDict(extra="forbid")

    platform: str
    caption_text: str
    hashtags: list[str]
    character_count: int
    hashtag_count: int
    tips_applied: list[str]


class GenerateCaptionResponse(BaseModel):
    """Generated captions result."""

    model_config = ConfigDict(extra="forbid")

    idea_id: str
    captions: list[GeneratedCaption]


class PersistQuickIdeaRequest(BaseModel):
    """Persist a quick trend recommendation as a full idea."""

    model_config = ConfigDict(extra="forbid")

    trend: dict[str, Any] = Field(default_factory=dict)
    recommendation: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="quick_trend_card")


# ── Idea Improvement ───────────────────────────────────────────────────────────


class ImproveIdeaRequest(BaseModel):
    """Request to improve an idea based on feedback."""

    model_config = ConfigDict(extra="forbid")

    feedback: str = Field(description="Feedback for improvement")
    aspect: str = Field(
        default="full",
        description="Aspect to improve: hook, title, rationale, full",
    )


class ImproveIdeaResponse(BaseModel):
    """Improved idea result."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: str


class VariationsRequest(BaseModel):
    """Request to generate variations of an idea."""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(default=3, ge=1, le=5)


class VariationsResponse(BaseModel):
    """Variations generation result."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: str


class RegenerateRequest(BaseModel):
    """Request to regenerate an idea from scratch."""

    model_config = ConfigDict(extra="forbid")

    aspect: str = Field(default="full")


class RegenerateResponse(BaseModel):
    """Regeneration result."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: str


# ── Collections ────────────────────────────────────────────────────────────────


class CollectionResponse(BaseModel):
    """Collection with metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str | None = None
    idea_count: int
    created_at: datetime


class CreateCollectionRequest(BaseModel):
    """Request to create a new collection."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class SaveIdeaRequest(BaseModel):
    """Request to save an idea to a collection."""

    model_config = ConfigDict(extra="forbid")

    idea_id: str


class CollectionIdeaResponse(BaseModel):
    """Collection reference for an idea."""

    model_config = ConfigDict(extra="forbid")

    collection_id: str
    name: str


# ── Planner / Scheduler ────────────────────────────────────────────────────────


class ScheduleIdeaRequest(BaseModel):
    """Request to schedule an idea to the planner."""

    model_config = ConfigDict(extra="forbid")

    idea_id: str
    scheduled_date: str = Field(description="Date in YYYY-MM-DD format")
    scheduled_time: str = Field(description="Time in HH:MM:SS format")
    platform: str = Field(description="Platform: instagram, tiktok, linkedin")
    conflict_resolution: str = Field(
        default="reject",
        description="Conflict resolution: reject, warn, force",
    )
    notes: str | None = None


class ScheduledItemResponse(BaseModel):
    """Scheduled item details."""

    model_config = ConfigDict(extra="forbid")

    id: str
    idea_id: str
    platform: str
    scheduled_at: str
    idea_title: str | None = None
    status: str


class ConflictItem(BaseModel):
    """Conflicting scheduled item."""

    model_config = ConfigDict(extra="forbid")

    id: str
    scheduled_time: str
    platform: str
    idea_title: str | None = None


class ConflictResponse(BaseModel):
    """Conflict detection response."""

    model_config = ConfigDict(extra="forbid")

    status: str = "conflict"
    conflicting_items: list[ConflictItem]
    suggestion: str
    available_slots: list[str]


class DaySchedule(BaseModel):
    """Schedule for a single day."""

    model_config = ConfigDict(extra="forbid")

    date: str
    items: list[ScheduledItemResponse]


class PlannerResponse(BaseModel):
    """Weekly planner view."""

    model_config = ConfigDict(extra="forbid")

    week_start: str
    days: list[DaySchedule]


# ── AI Assistant ───────────────────────────────────────────────────────────────


class AssistantRequest(BaseModel):
    """Request to AI assistant."""

    model_config = ConfigDict(extra="forbid")

    message: str
    context: dict[str, Any] | None = None


class AssistantResponse(BaseModel):
    """AI assistant response."""

    model_config = ConfigDict(extra="forbid")

    reply: str
    suggested_ideas: list[dict[str, Any]] | None = None


# ── Screen 2: Script Block Improvement ───────────────────────────────────────


class ImproveScriptBlockRequest(BaseModel):
    """Improve a single scene block in a script."""

    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(description="Scene block ID (e.g., 'hook', 'scene_1', 'cta')")
    text: str = Field(description="Current text of the block")
    tone: str = Field(default="friendly")
    instruction: str = Field(default="improve", description="Improvement instruction")


class ImproveScriptBlockResponse(BaseModel):
    """Improved script block."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    improved_text: str


# ── Screen 3: Caption Variants ────────────────────────────────────────────────


class CaptionVariantsRequest(BaseModel):
    """Generate caption variants."""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(default=3, ge=1, le=5)
    styles: list[str] | None = Field(default=None, description="Caption styles: friendly, funny, professional, etc.")


class CaptionVariant(BaseModel):
    """A single caption variant."""

    model_config = ConfigDict(extra="forbid")

    style: str
    caption_text: str
    hashtags: list[str]
    character_count: int


class CaptionVariantsResponse(BaseModel):
    """Multiple caption variants."""

    model_config = ConfigDict(extra="forbid")

    idea_id: str
    variants: list[CaptionVariant]


# ── Screen 4: Thumbnails ──────────────────────────────────────────────────────


class ThumbnailOption(BaseModel):
    """A thumbnail concept option."""

    model_config = ConfigDict(extra="forbid")

    id: str
    image_url: str
    label: str
    prompt: str
    resolution: str = "1080x1080"


class ThumbnailsResponse(BaseModel):
    """Generated thumbnails."""

    model_config = ConfigDict(extra="forbid")

    idea_id: str
    thumbnails: list[ThumbnailOption]


# ── Screen 5: Multi-Collection Save ───────────────────────────────────────────


class MultiSaveRequest(BaseModel):
    """Save idea to multiple collections."""

    model_config = ConfigDict(extra="forbid")

    collection_ids: list[str] = Field(min_length=1)


class MultiSaveResponse(BaseModel):
    """Multi-save result."""

    model_config = ConfigDict(extra="forbid")

    saved_to: list[str]
    idea_id: str


# ── Screen 9: Niche Details ───────────────────────────────────────────────────


class SubNiche(BaseModel):
    """A sub-niche tag."""

    model_config = ConfigDict(extra="forbid")

    name: str
    confidence: float


class NicheDetails(BaseModel):
    """Full niche analysis for a creator."""

    model_config = ConfigDict(extra="forbid")

    primary_niche: str
    sub_niches: list[SubNiche]
    confidence_score: float
    explanation: str
    content_style_summary: str
    creator_strengths: list[str]
