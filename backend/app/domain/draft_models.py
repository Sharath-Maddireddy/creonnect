from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DraftPostAnalysisRequest(BaseModel):
    """Request payload for pre-post draft optimization."""

    model_config = ConfigDict(extra="forbid")

    account_id: str
    draft_caption: str = ""
    post_type: Literal["IMAGE", "REEL"] = "IMAGE"
    media_url: str | None = None

    @field_validator("account_id", mode="before")
    @classmethod
    def _normalize_account_id(cls, value: object) -> str:
        text = value.strip() if isinstance(value, str) else ""
        if not text:
            raise ValueError("account_id is required.")
        return text

    @field_validator("draft_caption", mode="before")
    @classmethod
    def _normalize_draft_caption(cls, value: object) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()

    @field_validator("post_type", mode="before")
    @classmethod
    def _normalize_post_type(cls, value: object) -> Literal["IMAGE", "REEL"]:
        text = value.strip().upper() if isinstance(value, str) else ""
        if text in {"REEL", "VIDEO", "REELS", "CLIPS"}:
            return "REEL"
        return "IMAGE"

    @field_validator("media_url", mode="before")
    @classmethod
    def _normalize_media_url(cls, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text if text else None


class DraftVisualAnalysis(BaseModel):
    """Optional visual optimization feedback for the draft media."""

    model_config = ConfigDict(extra="forbid")

    visual_quality_score: int = Field(default=0, ge=0, le=10)
    hook_strength_score: float = Field(default=0.0, ge=0.0, le=1.0)
    primary_objects: list[str] = Field(default_factory=list)
    detected_text: str = ""
    lighting_feedback: str = ""
    composition_feedback: str = ""
    aesthetic_fixes: list[str] = Field(default_factory=list)
    is_cringe: bool = False
    adult_content_detected: bool = False


class DraftPostOptimizationResponse(BaseModel):
    """Structured response for draft post optimization."""

    model_config = ConfigDict(extra="forbid")

    optimized_caption_options: list[str] = Field(default_factory=list)
    predicted_reach_band: Literal["High", "Average", "Low"] = "Average"
    optimal_posting_times: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)
    content_format_recommendation: str = ""
    tone_alignment_warning: str = ""
    visual_analysis: DraftVisualAnalysis | None = None

