from __future__ import annotations

"""Domain models for trend analysis.

This module defines Pydantic models used across backend services to
represent creator niches, global trends, recommendations, and aggregated
analysis results. Each field includes a descriptive `Field` description
to support downstream LLM-driven TOON/JSON generation and schema
documentation.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreatorNiche(BaseModel):
    """Represents a creator's inferred niche classification.

    Attributes
    - primary_category: High-level category label for the creator.
    - sub_niches: Finer-grained niche labels within the primary category.
    - confidence_score: Normalized confidence (0.0-1.0) for the classification.
    """

    primary_category: str = Field(
        ...,
        description=(
            "Primary high-level category assigned to the creator, for example "
            "'Fitness', 'Beauty', 'Gaming'. This label is used for coarse audience "
            "segmentation and to guide trend matching and content recommendations."
        ),
    )

    sub_niches: list[str] = Field(
        ...,
        description=(
            "List of more specific niches or themes within the primary category, "
            "for example ['HIIT', 'Home Workouts']. These help tailor recommendations "
            "and contextualize trend relevance."
        ),
    )

    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Float in the range 0.0-1.0 indicating the model's confidence that the "
            "assigned primary category and sub-niches correctly describe the creator's "
            "content. Higher values indicate greater certainty."
        ),
    )


class GlobalTrend(BaseModel):
    """Represents a global trend detected across platforms or datasets.

    Attributes
    - topic_name: Human-readable name of the trend topic.
    - trend_type: The axis of the trend (topic, format, audio, hashtag).
    - momentum: Current momentum stage (rising, peaking, falling).
    - description: Brief summary of the trend and why it matters.
    - example_reference: Optional pointer (URL, post id, or short text) illustrating the trend.
    """

    topic_name: str = Field(
        ...,
        description=(
            "Canonical human-readable name of the trend or topic, e.g. '90s Dance Revival' "
            "or 'Edutainment Short-Form'. Used for display and matching to creator context."
        ),
    )

    trend_type: Literal["topic", "format", "audio", "hashtag"] = Field(
        ...,
        description=(
            "Type of trend; one of: 'topic' (subject matter), 'format' (video structure), "
            "'audio' (sound/music), or 'hashtag' (tag-driven trend). This helps determine "
            "how to apply the trend in recommendations."
        ),
    )

    momentum: Literal["rising", "peaking", "falling"] = Field(
        ...,
        description=(
            "Estimated momentum stage of the trend: 'rising' (gaining attention), "
            "'peaking' (at or near maximum visibility), or 'falling' (losing traction). "
            "Used to prioritize recommendations."
        ),
    )

    description: str = Field(
        ...,
        description=(
            "Concise description of the trend, data signals behind it, and the key "
            "audiences or content styles it impacts. Useful for human-readable summaries."
        ),
    )

    example_reference: Optional[str] = Field(
        None,
        description=(
            "Optional example illustrating the trend, such as a representative post URL, "
            "content id, or short textual example. May be omitted if no single example "
            "is preferred."
        ),
    )

    audience_match_pct: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description=(
            "Percentage match (0-100) indicating how well this trend aligns with the "
            "creator's audience interests and content patterns."
        ),
    )


class TrendRecommendation(BaseModel):
    """A concrete recommendation derived from trend analysis for a creator to apply.

    Attributes
    - suggested_title: A suggested title or headline the creator could use.
    - rationale: Explanation linking the recommendation to observed trends and the creator's niche.
    - expected_impact: Short description of the anticipated benefit (reach, engagement, discovery).
    - trend_reference: Optional pointer to the `GlobalTrend.topic_name` or an external reference.
    - opportunity_score: 0-100 score combining trend momentum, niche fit, and engagement potential.
    - expected_reach_min: Lower bound of expected reach range.
    - expected_reach_max: Upper bound of expected reach range.
    - best_time: Suggested posting time (e.g., "Thu, 8:30 PM").
    - difficulty: Content creation difficulty level.
    - hook: Suggested opening hook text for the content.
    - content_style: Richer content type label (e.g., "Storytelling", "Educational").
    """

    suggested_title: str = Field(
        ...,
        description=(
            "Concise suggested title or hook for a piece of content that aligns with the trend "
            "and the creator's niche. Should be short and actionable."
        ),
    )

    rationale: str = Field(
        ...,
        description=(
            "Detailed rationale that ties the suggested title to the detected trend signals, "
            "creator niche, and the expected audience behavior. This is important for LLM "
            "explanations and auditing."
        ),
    )

    expected_impact: str = Field(
        ...,
        description=(
            "A brief statement of the expected benefit if the creator follows the recommendation, "
            "for example increased discovery, improved watch-time, or higher brand-fit engagement."
        ),
    )

    trend_reference: Optional[str] = Field(
        None,
        description=(
            "Optional reference to the originating trend, such as the `GlobalTrend.topic_name`, "
            "a trend id, or an external link that contextualizes the recommendation."
        ),
    )

    opportunity_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description=(
            "0-100 score combining trend momentum, niche fit, and engagement potential. "
            "Higher scores indicate greater content opportunity."
        ),
    )

    expected_reach_min: Optional[int] = Field(
        None,
        ge=0,
        description="Lower bound of expected reach range for this content.",
    )

    expected_reach_max: Optional[int] = Field(
        None,
        ge=0,
        description="Upper bound of expected reach range for this content.",
    )

    best_time: Optional[str] = Field(
        None,
        description=(
            "Suggested posting time derived from the creator's engagement heatmap, "
            "for example 'Thu, 8:30 PM'."
        ),
    )

    difficulty: Optional[str] = Field(
        None,
        description=(
            "Content creation difficulty level: 'Easy', 'Medium', or 'Hard'. "
            "Derived from trend type and content complexity."
        ),
    )

    hook: Optional[str] = Field(
        None,
        description=(
            "Suggested opening hook text for the content. A short, attention-grabbing "
            "first line that aligns with the trend and creator style."
        ),
    )

    content_style: Optional[str] = Field(
        None,
        description=(
            "Richer content type label beyond the basic trend_type. For example: "
            "'Storytelling', 'Educational', 'POV/Lifestyle', 'How-to', 'Day-in-life'."
        ),
    )


class ContentGap(BaseModel):
    """A detected gap in the creator's content strategy."""

    description: str = Field(
        ...,
        description="Human-readable description of the content gap.",
    )

    severity: str = Field(
        default="info",
        description="Severity level: 'warning', 'info', or 'opportunity'.",
    )

    suggested_action: Optional[str] = Field(
        None,
        description="Optional suggested action to address this gap.",
    )


class DailyInsights(BaseModel):
    """Today's key insights for the creator."""

    audience_active_window: Optional[str] = Field(
        None,
        description="Peak audience activity window (e.g., '8:30 PM – 11:30 PM').",
    )

    best_content_type: Optional[str] = Field(
        None,
        description="Best performing content type today (e.g., 'Reels').",
    )

    trending_audio_count: Optional[int] = Field(
        None,
        ge=0,
        description="Number of trending audio tracks relevant to the creator's niche.",
    )

    competition_level: Optional[str] = Field(
        None,
        description="Competition level for posting today: 'Low', 'Medium', or 'High'.",
    )

    overall_opportunity: Optional[str] = Field(
        None,
        description="Overall opportunity level today: 'Very High', 'High', 'Medium', or 'Low'.",
    )


class TrendAnalysisResult(BaseModel):
    """Aggregated result of running trend analysis for a specific creator.

    Attributes
    - niche: The inferred `CreatorNiche` for the creator.
    - global_trends: Ordered list of `GlobalTrend` objects relevant to the creator.
    - recommendations: Prioritized list of `TrendRecommendation` items the creator can act on.
    - content_gaps: Detected gaps in the creator's content strategy.
    - daily_insights: Today's key insights for the creator.
    - opportunity_bullets: AI-generated insight bullets for the weekly opportunity banner.
    """

    niche: CreatorNiche = Field(
        ...,
        description=(
            "The inferred niche classification for the creator. Used as the primary context "
            "for matching trends and generating tailored recommendations."
        ),
    )

    global_trends: list[GlobalTrend] = Field(
        default_factory=list,
        description=(
            "List of global trends deemed relevant to the creator's niche. Trends are ordered "
            "by relevance or priority and include metadata to explain their momentum and type."
        ),
    )

    recommendations: list[TrendRecommendation] = Field(
        default_factory=list,
        description=(
            "Actionable, prioritized recommendations for the creator derived from the niche "
            "and the matching global trends. Each includes rationale and expected impact."
        ),
    )

    content_gaps: list["ContentGap"] = Field(
        default_factory=list,
        description=(
            "Detected gaps in the creator's content strategy, such as missing content types, "
            "underutilized formats, or low-performing areas relative to trending opportunities."
        ),
    )

    daily_insights: Optional["DailyInsights"] = Field(
        None,
        description=(
            "Today's key insights for the creator, including active audience window, "
            "best content type, trending audio count, and competition level."
        ),
    )

    opportunity_bullets: list[str] = Field(
        default_factory=list,
        description=(
            "AI-generated insight bullets for the weekly opportunity banner. "
            "Each is a concise statement about a content opportunity (e.g., "
            "'Travel reels are underutilized')."
        ),
    )


__all__ = [
    "CreatorNiche",
    "GlobalTrend",
    "TrendRecommendation",
    "ContentGap",
    "DailyInsights",
    "TrendAnalysisResult",
]
