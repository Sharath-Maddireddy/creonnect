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


class TrendRecommendation(BaseModel):
    """A concrete recommendation derived from trend analysis for a creator to apply.

    Attributes
    - suggested_title: A suggested title or headline the creator could use.
    - rationale: Explanation linking the recommendation to observed trends and the creator's niche.
    - expected_impact: Short description of the anticipated benefit (reach, engagement, discovery).
    - trend_reference: Optional pointer to the `GlobalTrend.topic_name` or an external reference.
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


class TrendAnalysisResult(BaseModel):
    """Aggregated result of running trend analysis for a specific creator.

    Attributes
    - niche: The inferred `CreatorNiche` for the creator.
    - global_trends: Ordered list of `GlobalTrend` objects relevant to the creator.
    - recommendations: Prioritized list of `TrendRecommendation` items the creator can act on.
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


__all__ = [
    "CreatorNiche",
    "GlobalTrend",
    "TrendRecommendation",
    "TrendAnalysisResult",
]
