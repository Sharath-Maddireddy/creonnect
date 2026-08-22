"""Domain models for the Creator Image Editor and its shared asset storage."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CreatorImageEditorOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str = ""


class CreatorImageEditorStyle(CreatorImageEditorOption):
    tag: Literal["evergreen", "rotating"]
    is_rotating: bool
    category: Literal["brand-production", "trending"]


class CreatorImageEditorEnhancement(CreatorImageEditorOption):
    mutually_exclusive_with: list[str] = Field(default_factory=list)


class CreatorImageEditorConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_version: str
    styles: list[CreatorImageEditorStyle]
    goals: list[CreatorImageEditorOption]
    events: list[CreatorImageEditorOption]
    enhancements: list[CreatorImageEditorEnhancement]
    output_formats: list[str]


class CreatorImageGenerationSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    style_id: str
    event_id: str = "none"
    enhancement_ids: list[str] = Field(default_factory=list)
    output_format: str = "png"


class CreatorImageUrlJobRequest(CreatorImageGenerationSelection):
    source_url: str = Field(min_length=1, max_length=2048)


class CreatorImageJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["queued", "processing", "succeeded", "failed", "cancelled"]
    progress_percent: int = Field(ge=0, le=100)
    progress_stage: str | None = None
    next_poll_after_ms: int | None = Field(default=None, ge=0)
    retry_allowed: bool = False
    cancel_allowed: bool = False
    source_url: str | None = None
    result_url: str | None = None
    thumbnail_url: str | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, str] | None = None
    created_at: str | None = None
    updated_at: str | None = None


class UploadImageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    account_id: str
    filename: str
    mime_type: str
    width: int
    height: int
    byte_size: int
    is_original: bool = True


class ImageAssetMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    account_id: str
    original_asset_id: str | None = None
    parent_asset_id: str | None = None
    filename: str
    mime_type: str
    width: int
    height: int
    byte_size: int
    is_original: bool
    created_at: str | None = None


class AIModeEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_asset_id: str
    prompt: str | None = Field(default=None, max_length=4000)
    provider: Literal["gpt-image", "gemini"] = "gemini"
    filter_id: str | None = None
    resolution: Literal["512", "1K", "2K", "4K"] | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
