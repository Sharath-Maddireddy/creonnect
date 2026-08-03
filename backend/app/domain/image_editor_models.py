"""Domain models for the Phase 1 backend-owned image editor feature."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ImageEditorStyleSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str
    popular: bool = False
    filter_only_compatible: bool = True


class ImageEditorIntensitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    value: int = Field(ge=0, le=100)


class ImageEditorQualityPresetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    output_format: str
    output_compression: int | None = None


class ImageEditorControlSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    enabled: bool
    visible_in_filter_only_mode: bool
    filter_only_compatible: bool
    operation_type: str


class ImageEditorConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_key: str
    config_version: str
    mode: str
    supported_modes: list[str] = Field(default_factory=list)
    ai_edit_available: bool = False
    styles: list[ImageEditorStyleSummary]
    intensities: list[ImageEditorIntensitySummary]
    quality_presets: list[ImageEditorQualityPresetSummary]
    controls: list[ImageEditorControlSummary]
    allowed_operations: list[str]
    forbidden_operations: list[str]


class ImageEditorCatalogFilterSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    category: Literal["brand-production", "trend-fun"]
    mode: Literal["deterministic", "ai-edit"]
    description: str
    provider_preference: Literal["none", "gpt-image", "gemini"]
    campaign_eligible: bool
    requires_secondary_asset: bool
    settings: list[str] = Field(default_factory=list)


class ImageEditorFilterCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_key: str
    catalog_version: str
    filters: list[ImageEditorCatalogFilterSummary]


class ApplyFilterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style_id: str
    intensity_id: str = "balanced"
    quality_preset_id: str = "standard"
    enabled_control_ids: list[str] = Field(default_factory=list)
    output_format: str | None = None


class ApplyFilterWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ApplyFilterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_version: str
    mode: str
    engine: str
    request_hash: str
    mime_type: str
    width: int
    height: int
    output_format: str
    image_base64: str
    warnings: list[ApplyFilterWarning] = Field(default_factory=list)
    applied_profile: dict[str, Any] = Field(default_factory=dict)


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


class PersistedFilterApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_asset_id: str
    style_id: str
    intensity_id: str = "balanced"
    quality_preset_id: str = "standard"
    enabled_control_ids: list[str] = Field(default_factory=list)
    output_format: str | None = None


class PersistedFilterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    result_asset_id: str
    original_asset_id: str
    request_hash: str
    deduplicated: bool = False
    response: ApplyFilterResponse


class RegenerateFilterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str


class AIModeEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_asset_id: str
    prompt: str | None = Field(default=None, max_length=4000)
    provider: Literal["gpt-image", "gemini"] = "gpt-image"
    filter_id: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class AIModeEditResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    status: str
    message: str
    request_id: str | None = None
    result_asset_id: str | None = None
    provider: str | None = None
    model: str | None = None
    deduplicated: bool = False


class ImageEditJobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    status: str
    queue_name: str
    job_name: str
    account_id: str | None = None
    source_ref: str | None = None
    progress: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ImageEditRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    account_id: str
    original_asset_id: str
    result_asset_id: str
    style_id: str
    intensity_id: str
    quality_preset_id: str
    enabled_control_ids: list[str] = Field(default_factory=list)
    request_hash: str
    mode: str
    engine: str
    config_version: str
    created_at: str | None = None
