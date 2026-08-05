"""Versioned, evidence-aware contract for creator intelligence reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MetricStatus = Literal["observed", "derived", "predicted", "unavailable"]
UnavailableReason = Literal[
    "insufficient_post_history",
    "insufficient_follower_history",
    "missing_reel_insights",
    "missing_audience_insights",
    "missing_peer_cohort",
    "missing_account_metrics",
    "not_yet_calculated",
]

CREATOR_INTELLIGENCE_METRIC_IDS = (
    "overall_account_grade",
    "growth_potential",
    "virality_potential",
    "follower_quality",
    "best_posting_time",
    "posting_frequency",
    "best_posts",
    "worst_posts",
    "best_hooks",
    "weak_hooks",
    "caption_quality",
    "visual_quality",
    "editing_quality",
    "thumbnail_quality",
    "retention",
    "hashtag_performance",
    "cta_performance",
    "content_pillars",
    "content_fatigue",
    "audience_demographics",
    "competitor_analysis",
    "brand_readiness",
    "estimated_earnings",
    "thirty_day_plan",
    "weekly_checklist",
    "priority_improvements",
)


class CreatorIntelligenceMetric(BaseModel):
    """One report metric and the evidence state needed to trust it."""

    model_config = ConfigDict(extra="forbid")

    metric_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    category: Literal["account", "content", "audience", "competition", "monetization", "action"]
    status: MetricStatus
    value: Any | None = None
    unit: str | None = Field(default=None, max_length=40)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list, max_length=20)
    evidence_details: list["MetricEvidence"] = Field(default_factory=list, max_length=20)
    methodology_version: str = Field(default="creator-intelligence-v1", min_length=1, max_length=80)
    source_data_at: datetime | None = None
    unavailable_reason: UnavailableReason | None = None
    availability_guidance: str | None = Field(default=None, max_length=240)

    @field_validator("evidence", mode="before")
    @classmethod
    def _sanitize_evidence(cls, value: list[str] | None) -> list[str]:
        if not isinstance(value, list):
            return []
        return [" ".join(item.strip().split())[:160] for item in value if isinstance(item, str) and item.strip()]

    @model_validator(mode="after")
    def _enforce_availability_contract(self) -> "CreatorIntelligenceMetric":
        if self.status == "unavailable":
            if self.value is not None or self.confidence is not None or self.evidence or self.evidence_details:
                raise ValueError("unavailable metrics cannot contain values, confidence, or evidence")
            if self.unavailable_reason is None or not self.availability_guidance:
                raise ValueError("unavailable metrics require a reason and user-facing guidance")
        elif self.unavailable_reason is not None or self.availability_guidance is not None:
            raise ValueError("available metrics cannot contain unavailable metadata")
        return self


class MetricEvidence(BaseModel):
    """Structured provenance for a metric input without exposing raw credentials."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=80)
    fields: list[str] = Field(default_factory=list, max_length=20)
    observed_at: datetime | None = None
    reference: str | None = Field(default=None, max_length=160)


class ReelDataAvailability(BaseModel):
    """Availability manifest for Reel-only cards in the report UI."""

    model_config = ConfigDict(extra="forbid")

    reel_post_count: int = Field(default=0, ge=0)
    reels_with_visual_analysis: int = Field(default=0, ge=0)
    reels_with_observed_watch_through: int = Field(default=0, ge=0)
    editing_quality_available: bool = False
    retention_available: bool = False
    guidance: str | None = None


class CreatorIntelligenceReport(BaseModel):
    """Persistable report envelope. Every supported metric is always represented."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    report_status: Literal["complete", "partial"] = "partial"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: list[CreatorIntelligenceMetric] = Field(min_length=26, max_length=26)
    reel_data_availability: ReelDataAvailability = Field(default_factory=ReelDataAvailability)

    @model_validator(mode="after")
    def _validate_metric_inventory(self) -> "CreatorIntelligenceReport":
        metric_ids = [metric.metric_id for metric in self.metrics]
        if tuple(metric_ids) != CREATOR_INTELLIGENCE_METRIC_IDS:
            raise ValueError("report metrics must match the versioned metric inventory and order")
        return self
