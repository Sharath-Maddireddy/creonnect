"""Domain models for deterministic account-level health analysis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Band = Literal["NEEDS_WORK", "AVERAGE", "STRONG", "EXCEPTIONAL"]


class DeterministicDriver(BaseModel):
    """Deterministic account-level driver entry."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    type: Literal["POSITIVE", "LIMITING"] = "LIMITING"
    explanation: str

    @field_validator("id", "label", "explanation", mode="before")
    @classmethod
    def _sanitize_text(cls, value: str | None) -> str:
        text = value if isinstance(value, str) else ""
        return " ".join(text.strip().split())[:240]

    @field_validator("id", mode="after")
    @classmethod
    def _validate_id_not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("id cannot be empty")
        return value


class DeterministicRecommendation(BaseModel):
    """Deterministic account-level recommendation entry."""

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    impact_level: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"

    @field_validator("id", "text", mode="before")
    @classmethod
    def _sanitize_text(cls, value: str | None) -> str:
        text = value if isinstance(value, str) else ""
        return " ".join(text.strip().split())[:240]

    @field_validator("id", mode="after")
    @classmethod
    def _validate_id_not_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("id cannot be empty")
        return value


class PillarScore(BaseModel):
    """One account health pillar score."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(default=0.0, ge=0.0, le=100.0)
    band: Band = Field(default="NEEDS_WORK")
    notes: list[str] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, value: int | float | str | None) -> float:
        if value is None:
            return 0.0
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return round(max(0.0, min(100.0, numeric)), 2)

    @field_validator("notes", mode="before")
    @classmethod
    def _sanitize_notes(cls, value: list[str] | str | None) -> list[str]:
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
            sanitized.append(text[:200])
        return sanitized


class AccountHealthMetadata(BaseModel):
    """Metadata describing account-level aggregation inputs."""

    model_config = ConfigDict(extra="forbid")

    post_count_used: int = Field(default=0, ge=0, le=30)
    min_history_threshold_met: bool = Field(default=False)
    time_window_days: int | None = Field(default=None, ge=1)


class AccountHealthScore(BaseModel):
    """Composite deterministic account health score."""

    model_config = ConfigDict(extra="forbid")

    ahs_score: float = Field(default=0.0, ge=0.0, le=100.0)
    ahs_band: Band = Field(default="NEEDS_WORK")
    pillars: dict[str, PillarScore] = Field(default_factory=dict)
    drivers: list[DeterministicDriver] = Field(default_factory=list)
    recommendations: list[DeterministicRecommendation] = Field(default_factory=list)
    metadata: AccountHealthMetadata = Field(default_factory=AccountHealthMetadata)

    @field_validator("ahs_score", mode="before")
    @classmethod
    def _clamp_ahs_score(cls, value: int | float | str | None) -> float:
        if value is None:
            return 0.0
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return round(max(0.0, min(100.0, numeric)), 2)
