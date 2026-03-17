"""Domain models for brand-creator matching."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BrandProfile(BaseModel):
    """Brand campaign requirements for creator discovery."""

    model_config = ConfigDict(extra="forbid")

    brand_name: str = Field(description="Brand or campaign name.")
    niche: str = Field(description="Brand content niche, e.g. fitness, fashion, tech, food.")
    min_followers: int | None = Field(default=None, ge=0, description="Minimum follower count.")
    max_followers: int | None = Field(default=None, ge=0, description="Maximum follower count.")
    min_engagement_rate: float | None = Field(default=None, ge=0.0, description="Minimum engagement rate (0.0-1.0).")
    required_brand_safety_min: float = Field(default=70.0, ge=0.0, le=100.0, description="Minimum brand safety score 0-100.")
    content_quality_min: float = Field(default=50.0, ge=0.0, le=100.0, description="Minimum content quality score 0-100.")

    @field_validator("brand_name", "niche", mode="before")
    @classmethod
    def _strip_text(cls, value: str | None) -> str:
        return (value or "").strip()[:120]

    @field_validator("min_engagement_rate", mode="before")
    @classmethod
    def _clamp_min_engagement_rate(cls, value: float | int | str | None) -> float | None:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return round(max(0.0, min(1.0, numeric)), 6)

    @model_validator(mode="after")
    def _validate_follower_bounds(self) -> "BrandProfile":
        if (
            self.min_followers is not None
            and self.max_followers is not None
            and self.min_followers > self.max_followers
        ):
            raise ValueError("min_followers cannot be greater than max_followers.")
        return self


class CreatorMatchScore(BaseModel):
    """Match score for one creator against a brand profile."""

    model_config = ConfigDict(extra="forbid")

    account_id: str
    total_match_score: float = Field(ge=0.0, le=100.0)
    niche_fit: float = Field(ge=0.0, le=20.0)
    engagement_quality: float = Field(ge=0.0, le=20.0)
    brand_safety_fit: float = Field(ge=0.0, le=20.0)
    content_quality_fit: float = Field(ge=0.0, le=20.0)
    audience_size_fit: float = Field(ge=0.0, le=20.0)
    match_band: Literal["EXCELLENT", "GOOD", "MODERATE", "POOR"]
    disqualified: bool = False
    disqualify_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("account_id", mode="before")
    @classmethod
    def _sanitize_account_id(cls, value: str | None) -> str:
        return (value or "").strip()[:120]

    @field_validator(
        "total_match_score",
        mode="before",
    )
    @classmethod
    def _clamp_total_match_score(cls, value: float | int | str | None) -> float:
        if value is None:
            return 0.0
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return round(max(0.0, min(100.0, numeric)), 2)

    @field_validator(
        "niche_fit",
        "engagement_quality",
        "brand_safety_fit",
        "content_quality_fit",
        "audience_size_fit",
        mode="before",
    )
    @classmethod
    def _clamp_component_score(cls, value: float | int | str | None) -> float:
        if value is None:
            return 0.0
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return round(max(0.0, min(20.0, numeric)), 2)

    @field_validator("disqualify_reasons", "notes", mode="before")
    @classmethod
    def _sanitize_text_list(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        values = value if isinstance(value, list) else [value]
        sanitized: list[str] = []
        for item in values:
            if not isinstance(item, str):
                continue
            text = " ".join(item.strip().split())
            if not text:
                continue
            sanitized.append(text[:240])
        return sanitized
