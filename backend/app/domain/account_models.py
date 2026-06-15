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


class ContentTypeBreakdownEntry(BaseModel):
    """Performance metrics for a single content type (e.g. IMAGE or REEL)."""

    model_config = ConfigDict(extra="forbid")

    content_type: str = Field(description="Content format identifier (IMAGE, REEL, etc.).")
    post_count: int = Field(default=0, ge=0, description="Number of posts of this type.")
    percentage_of_total: float = Field(default=0.0, ge=0.0, le=100.0, description="What percentage of total posts this type represents.")
    avg_views: float | None = Field(default=None, ge=0.0, description="Average reach/views for this content type.")
    total_views: int | None = Field(default=None, ge=0, description="Sum of all views for this content type.")
    avg_engagement_rate: float | None = Field(default=None, ge=0.0, description="Average engagement rate for this content type.")
    avg_likes: float | None = Field(default=None, ge=0.0, description="Average likes for this content type.")
    avg_comments: float | None = Field(default=None, ge=0.0, description="Average comments for this content type.")
    avg_saves: float | None = Field(default=None, ge=0.0, description="Average saves for this content type.")
    avg_shares: float | None = Field(default=None, ge=0.0, description="Average shares for this content type.")
    avg_weighted_score: float | None = Field(default=None, ge=0.0, le=100.0, description="Average weighted post score P for this type.")
    views_share_percent: float | None = Field(default=None, ge=0.0, le=100.0, description="What percentage of total views this type drives.")

    @field_validator("content_type", mode="before")
    @classmethod
    def _normalize_content_type(cls, value: str | None) -> str:
        if not isinstance(value, str):
            return "UNKNOWN"
        return value.strip().upper()[:20] or "UNKNOWN"


class ContentTypePerformance(BaseModel):
    """Breakdown of which content types drive the most views and engagement."""

    model_config = ConfigDict(extra="forbid")

    breakdown: list[ContentTypeBreakdownEntry] = Field(default_factory=list, description="Per-type performance entries sorted by avg_views descending.")
    best_for_views: str | None = Field(default=None, description="Content type that drives the highest average views.")
    best_for_engagement: str | None = Field(default=None, description="Content type with the highest average engagement rate.")
    insight: str | None = Field(default=None, description="Human-readable summary insight about content type performance.")
    notes: list[str] = Field(default_factory=list, description="Deterministic notes about data coverage.")

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

    @field_validator("insight", mode="before")
    @classmethod
    def _sanitize_insight(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return None
        text = " ".join(value.strip().split())
        return text[:300] if text else None


class AccountHealthScore(BaseModel):
    """Composite deterministic account health score."""

    model_config = ConfigDict(extra="forbid")

    ahs_score: float = Field(default=0.0, ge=0.0, le=100.0)
    ahs_band: Band = Field(default="NEEDS_WORK")
    pillars: dict[str, PillarScore] = Field(default_factory=dict)
    drivers: list[DeterministicDriver] = Field(default_factory=list)
    recommendations: list[DeterministicRecommendation] = Field(default_factory=list)
    metadata: AccountHealthMetadata = Field(default_factory=AccountHealthMetadata)
    creator_intelligence: CreatorIntelligence | None = None
    vision_summary: AccountVisionSummary | None = None
    engagement_signals: AccountEngagementSignals | None = None
    content_type_performance: ContentTypePerformance | None = None

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


class AccountVisionSummary(BaseModel):
    """Vision-derived rollup signals for an account."""

    model_config = ConfigDict(extra="forbid")

    avg_cringe_score: float | None = Field(default=None, ge=0.0, le=100.0)
    avg_hook_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    avg_production_level: str | None = None
    flagged_posts_count: int = Field(default=0, ge=0)
    common_technical_flaws: list[str] = Field(default_factory=list)

    @field_validator("avg_production_level", mode="before")
    @classmethod
    def _sanitize_avg_production_level(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return None
        text = " ".join(value.strip().split()).lower()[:20]
        return text if text in {"low", "medium", "high"} else None

    @field_validator("common_technical_flaws", mode="before")
    @classmethod
    def _sanitize_common_technical_flaws(
        cls, value: list[str] | str | None
    ) -> list[str]:
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
            sanitized.append(text[:160])
            if len(sanitized) >= 5:
                break
        return sanitized


class AccountEngagementSignals(BaseModel):
    """Aggregate engagement-derived account signals."""

    model_config = ConfigDict(extra="forbid")

    avg_save_rate: float | None = Field(default=None, ge=0.0)
    avg_share_rate: float | None = Field(default=None, ge=0.0)
    avg_watch_through_rate: float | None = Field(default=None, ge=0.0)
    avg_profile_visit_rate: float | None = Field(default=None, ge=0.0)
    audience_trust_index: float | None = Field(default=None, ge=0.0, le=100.0)
    virality_potential: float | None = Field(default=None, ge=0.0, le=100.0)
    consistency_score: float | None = Field(default=None, ge=0.0, le=100.0)


class BrandFitSignals(BaseModel):
    """Brand-fit categories and safety red flags."""

    model_config = ConfigDict(extra="forbid")

    fit_categories: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)

    @field_validator("fit_categories", mode="before")
    @classmethod
    def _sanitize_fit_categories(cls, value: list[str] | str | None) -> list[str]:
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
            sanitized.append(text)
            if len(sanitized) >= 8:
                break
        return sanitized

    @field_validator("red_flags", mode="before")
    @classmethod
    def _sanitize_red_flags(cls, value: list[str] | str | None) -> list[str]:
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
            sanitized.append(text)
            if len(sanitized) >= 5:
                break
        return sanitized


class CreatorIntelligence(BaseModel):
    """Account-level creator profile and brand fit rollup."""

    model_config = ConfigDict(extra="forbid")

    creator_persona: str | None = None
    content_style_summary: str | None = None
    audience_hypothesis: str | None = None
    creator_strengths: list[str] = Field(default_factory=list)
    improvement_areas: list[str] = Field(default_factory=list)
    sponsorship_potential: Literal["HIGH", "MEDIUM", "LOW"] | None = None
    notable_formats: list[str] = Field(default_factory=list)
    top_performing_themes: list[str] = Field(default_factory=list)
    brand_fit: BrandFitSignals = Field(default_factory=BrandFitSignals)

    @field_validator("creator_persona", "content_style_summary", "audience_hypothesis", mode="before")
    @classmethod
    def _sanitize_optional_text(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return None
        text = " ".join(value.strip().split())
        return text[:500] or None

    @field_validator("creator_strengths", "improvement_areas", "notable_formats", "top_performing_themes", mode="before")
    @classmethod
    def _sanitize_text_lists(
        cls, value: list[str] | str | None
    ) -> list[str]:
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
            sanitized.append(text[:120])
            if len(sanitized) >= 5:
                break
        return sanitized



AccountHealthScore.model_rebuild()


class CreatorEngagementMetrics(BaseModel):
    engagement_rate_flag: Literal["Good", "Bad", "Neutral"]
    save_rate_flag: Literal["Good", "Bad", "Neutral"]
    share_rate_flag: Literal["Good", "Bad", "Neutral"]
    comment_rate_flag: Literal["Good", "Bad", "Neutral"]


class CreatorReachMetrics(BaseModel):
    reach_efficiency_flag: Literal["Healthy", "Weak", "Neutral"]
    reel_reach_flag: Literal["Healthy", "Weak", "Neutral"]
    story_reach_flag: Literal["Healthy", "Weak", "Neutral"]
    non_follower_reach_flag: Literal["Healthy", "Weak", "Neutral"]


class CreatorRetentionMetrics(BaseModel):
    completion_rate_flag: Literal["Good", "Weak", "Neutral"]
    replay_rate_flag: Literal["Good", "Weak", "Neutral"]
    hook_efficiency_flag: Literal["Good", "Weak", "Neutral"]
    watch_time_ratio_flag: Literal["Good", "Weak", "Neutral"]


class CreatorGrowthMetrics(BaseModel):
    follower_growth_flag: Literal["Steady", "Huge Spikes", "Neutral"]
    net_growth_flag: Literal["Positive", "Negative", "Neutral"]
    growth_velocity_flag: Literal["Consistent", "Sudden Jumps", "Neutral"]
    unfollow_rate_flag: Literal["Healthy", "Bad Signal", "Neutral"]


class FakeFollowerSignals(BaseModel):
    poor_audience_quality: bool = False
    weak_audience_interest: bool = False
    bot_activity: bool = False
    possible_bought_followers: bool = False
    inactive_followers: bool = False
    dead_audience: bool = False


class AIFeaturePredictions(BaseModel):
    optimized_caption_options: list[str] = Field(
        default_factory=list,
        description="Two optimized caption variants for the upcoming post.",
    )
    predicted_reach_band: Literal["High", "Average", "Low"] = Field(
        default="Average",
        description="Predicted reach band for the upcoming post.",
    )
    optimal_posting_times: list[str] = Field(
        default_factory=list,
        description="List of optimal posting windows based on historical post performance.",
    )
    safety_flags: list[str] = Field(
        default_factory=list,
        description="Safety or distribution risks detected in the caption strategy.",
    )
    content_format_recommendation: str | None = Field(
        default=None,
        description="Suggested content format adjustment to improve reach.",
    )
    tone_alignment_warning: str | None = Field(
        default=None,
        description="Warning when the proposed caption tone diverges from the creator's historical voice.",
    )
    viral_probability: float = Field(default=0.0, description="0.0 to 1.0 probability of going viral")
    campaign_roi_prediction: str | None = Field(default=None, description="Predicted ROI band (e.g., '2x - 3x')")
    best_posting_time: list[str] = Field(
        default_factory=list,
        description="List of optimal posting times (e.g. ['Wednesday 4PM EST'])",
    )
    audience_authenticity_score: float = Field(default=0.0, description="0 to 100 authenticity score")
    spam_detected_count: int = Field(default=0, description="Number of suspected spam comments")
    sentiment_score: float = Field(default=0.0, description="-1.0 (negative) to 1.0 (positive) comment sentiment")
    prediction_status: Literal["ok", "degraded"] = Field(default="ok", description="Whether AI prediction used normal or fallback path.")
    degraded_reason: str | None = Field(default=None, description="Reason for degraded fallback when prediction_status is 'degraded'.")


class AnalysisCoverage(BaseModel):
    """Coverage details for creator-score computations."""

    posts_considered: int = Field(default=0, ge=0)
    posts_with_reach: int = Field(default=0, ge=0)
    zero_denominator_events: int = Field(default=0, ge=0)
    missing_metric_events: int = Field(default=0, ge=0)


class AnalysisConfidence(BaseModel):
    """Confidence indicators for creator-score outputs."""

    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    status: Literal["ok", "degraded"] = Field(default="ok")
    reasons: list[str] = Field(default_factory=list)


class CreatorScore(BaseModel):
    final_score: float
    interpretation: Literal[
        "Elite Creator",
        "Strong Creator",
        "Average Creator",
        "Weak Audience",
        "High Risk / Fake Signals",
    ]
    engagement_metrics: CreatorEngagementMetrics
    reach_metrics: CreatorReachMetrics
    retention_metrics: CreatorRetentionMetrics
    growth_metrics: CreatorGrowthMetrics
    fake_follower_signals: FakeFollowerSignals
    ai_predictions: AIFeaturePredictions | None = None
    coverage: AnalysisCoverage | None = None
    confidence: AnalysisConfidence | None = None
