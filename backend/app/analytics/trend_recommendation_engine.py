from __future__ import annotations

"""Generate trend recommendations for a creator using an LLM.

Exposes `generate_trend_recommendations` which instructs an LLM acting as a
Creative Director to produce three highly actionable `TrendRecommendation`
objects in TOON format. The function cross-references the provided
`CreatorIntelligence` with the list of `GlobalTrend` objects and ensures each
recommendation includes a clear rationale explaining why the trend fits the creator.
"""

import asyncio
from typing import List

from backend.app.ai.llm_client import LLMClient
from backend.app.ai.toon_helpers import toon_parse_list
from backend.app.domain.account_models import CreatorIntelligence, HeatmapData
from backend.app.domain.post_models import SinglePostInsights
from backend.app.domain.trend_models import (
    ContentGap,
    DailyInsights,
    GlobalTrend,
    TrendRecommendation,
)
from backend.app.utils.logger import logger
from backend.app.utils.number_utils import safe_float as _safe_float


def _clean_text(value: object, *, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    text = " ".join(value.strip().split())
    return text or fallback


# ── Opportunity scoring helpers ────────────────────────────────────────────────

_MOMENTUM_SCORES: dict[str, float] = {
    "rising": 30.0,
    "peaking": 40.0,
    "falling": 10.0,
}

_TREND_TYPE_SCORES: dict[str, float] = {
    "format": 20.0,
    "audio": 15.0,
    "topic": 12.0,
    "hashtag": 10.0,
}

_NICHE_CATEGORY_KEYWORDS: dict[str, set[str]] = {
    "Fitness": {"fitness", "workout", "gym", "health", "exercise", "training"},
    "Food": {"food", "cooking", "recipe", "chef", "cuisine", "restaurant"},
    "Beauty": {"beauty", "makeup", "skincare", "hair", "glam", "tutorial"},
    "Fashion": {"fashion", "outfit", "style", "ootd", "wear", "dress"},
    "Travel": {"travel", "trip", "vacation", "explore", "destination", "vlog"},
    "Tech": {"tech", "coding", "software", "ai", "gadget", "review"},
    "Finance": {"finance", "money", "investing", "crypto", "business", "stocks"},
    "Motivation": {"motivation", "mindset", "goals", "hustle", "success", "grind"},
    "Lifestyle": {"lifestyle", "daily", "routine", "vlog", "grwm", "day"},
    "Education": {"education", "learn", "tutorial", "howto", "tips", "study"},
    "Comedy": {"comedy", "funny", "humor", "meme", "prank", "skit"},
}


def _compute_opportunity_score(
    trend: GlobalTrend,
    creator_intelligence: CreatorIntelligence,
    posts: list[SinglePostInsights] | None = None,
) -> float:
    """Compute a 0-100 opportunity score for a recommendation.

    Factors:
    - Trend momentum (0-40): rising=30, peaking=40, falling=10
    - Niche fit (0-30): how well trend matches creator's category
    - Content type match (0-20): format/audio trends score higher for video creators
    - Recency boost (0-10): based on post frequency
    """
    # Momentum component (0-40)
    momentum_score = _MOMENTUM_SCORES.get(trend.momentum, 20.0)

    # Niche fit component (0-30)
    niche_score = 15.0  # default mid-range
    primary = (creator_intelligence.content_style_summary or "").lower()
    trend_name = (trend.topic_name or "").lower()
    trend_desc = (trend.description or "").lower()
    combined_text = f"{trend_name} {trend_desc}"

    for category, keywords in _NICHE_CATEGORY_KEYWORDS.items():
        category_lower = category.lower()
        if category_lower in primary:
            keyword_hits = sum(1 for kw in keywords if kw in combined_text)
            if keyword_hits >= 2:
                niche_score = 28.0
            elif keyword_hits >= 1:
                niche_score = 22.0
            else:
                niche_score = 12.0
            break

    # Content type match component (0-20)
    type_score = _TREND_TYPE_SCORES.get(trend.trend_type, 10.0)
    # Boost format/audio for video-heavy creators
    if posts:
        video_count = sum(
            1 for p in posts
            if (getattr(p, "media_type", "") or "").upper() in ("REEL", "VIDEO")
        )
        if video_count > len(posts) * 0.5:
            if trend.trend_type in ("format", "audio"):
                type_score = min(20.0, type_score + 5.0)

    # Recency component (0-10)
    recency_score = 7.0
    if posts and len(posts) >= 5:
        recency_score = 10.0
    elif posts and len(posts) >= 3:
        recency_score = 8.0

    total = momentum_score + niche_score + type_score + recency_score
    return round(min(100.0, max(0.0, total)), 1)


def _estimate_reach_range(
    posts: list[SinglePostInsights],
    trend_momentum: str,
) -> tuple[int | None, int | None]:
    """Estimate expected reach range based on historical post reach and trend momentum.

    Returns (min, max) or (None, None) if no data available.
    """
    if not posts:
        return None, None

    reach_values: list[float] = []
    for post in posts:
        reach = _safe_float(getattr(post.core_metrics, "reach", None))
        if reach is not None and reach > 0:
            reach_values.append(reach)

    if not reach_values:
        return None, None

    # Use median reach as baseline
    reach_values.sort()
    mid = len(reach_values) // 2
    median_reach = reach_values[mid] if len(reach_values) % 2 == 1 else (reach_values[mid - 1] + reach_values[mid]) / 2

    # Apply momentum multiplier
    multiplier = {"rising": 1.2, "peaking": 1.5, "falling": 0.8}.get(trend_momentum, 1.0)
    base = median_reach * multiplier

    # ±20% range
    min_reach = int(base * 0.8)
    max_reach = int(base * 1.2)

    return min_reach, max_reach


def _derive_best_time(heatmap: list[HeatmapData]) -> str | None:
    """Derive the best posting time from engagement heatmap data."""
    if not heatmap:
        return None

    sorted_slots = sorted(heatmap, key=lambda h: h.intensity, reverse=True)
    if not sorted_slots:
        return None

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    best = sorted_slots[0]
    hour = best.hour_of_day
    period = "AM" if hour < 12 else "PM"
    display_hour = hour if hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12

    return f"{day_names[best.day_of_week]}, {display_hour}:00 {period}"


def _compute_difficulty(
    trend: GlobalTrend,
    posts: list[SinglePostInsights] | None = None,
) -> str:
    """Compute content creation difficulty based on trend type and complexity."""
    # Format trends are generally easier (follow a template)
    if trend.trend_type == "format":
        return "Easy"

    # Audio trends require production effort
    if trend.trend_type == "audio":
        return "Hard"

    # Topic trends depend on depth
    desc = (trend.description or "").lower()
    if any(word in desc for word in ["deep dive", "research", "analysis", "tutorial", "how-to"]):
        return "Hard"
    if any(word in desc for word in ["quick", "simple", "easy", "casual"]):
        return "Easy"

    # Hashtag trends are moderate
    if trend.trend_type == "hashtag":
        return "Medium"

    return "Medium"


def _detect_content_gaps(
    posts: list[SinglePostInsights],
    trends: list[GlobalTrend],
) -> list[ContentGap]:
    """Detect gaps in the creator's content strategy."""
    gaps: list[ContentGap] = []

    if not posts:
        return gaps

    # Check content type diversity
    type_counts: dict[str, int] = {}
    for post in posts:
        mt = (getattr(post, "media_type", "") or "").strip().upper()
        if mt:
            type_counts[mt] = type_counts.get(mt, 0) + 1

    total = len(posts)
    for content_type in ["REEL", "CAROUSEL", "IMAGE"]:
        count = type_counts.get(content_type, 0)
        pct = (count / total * 100) if total > 0 else 0
        if pct < 10 and count < 3:
            gaps.append(ContentGap(
                description=f"No {content_type.lower()} content posted recently",
                severity="warning",
                suggested_action=f"Consider posting {content_type.lower()} content to diversify",
            ))

    # Check for face-to-camera content
    face_to_camera = sum(
        1 for p in posts
        if any("face" in (getattr(s, "description", "") or "").lower()
               for s in (getattr(p, "vision_analysis", None).signals if getattr(p, "vision_analysis", None) else []))
    )
    if face_to_camera == 0 and total >= 5:
        gaps.append(ContentGap(
            description="No face-to-camera reels recently",
            severity="info",
            suggested_action="Face-to-camera content often builds stronger audience connection",
        ))

    # Check for trending format usage
    trend_types_used = set()
    for post in posts:
        caption = (getattr(post, "caption_text", "") or "").lower()
        if "pov" in caption:
            trend_types_used.add("pov")
        if "storytime" in caption or "story time" in caption:
            trend_types_used.add("storytime")
        if "tutorial" in caption or "how to" in caption:
            trend_types_used.add("tutorial")

    trending_types = set()
    for trend in trends:
        trending_types.add(trend.trend_type)

    if "format" in trending_types and not trend_types_used.intersection({"pov", "storytime", "tutorial"}):
        gaps.append(ContentGap(
            description="Underutilized trending formats",
            severity="opportunity",
            suggested_action="Try trending format styles this week",
        ))

    return gaps


def _compute_daily_insights(
    posts: list[SinglePostInsights],
    heatmap: list[HeatmapData],
    trends: list[GlobalTrend],
) -> DailyInsights:
    """Compute today's key insights from engagement data and trends."""
    # Best content type
    type_reach: dict[str, list[float]] = {}
    for post in posts:
        mt = (getattr(post, "media_type", "") or "").strip().upper()
        reach = _safe_float(getattr(post.core_metrics, "reach", None))
        if mt and reach is not None:
            type_reach.setdefault(mt, []).append(reach)

    best_type = None
    best_avg = 0.0
    for mt, reaches in type_reach.items():
        avg = sum(reaches) / len(reaches)
        if avg > best_avg:
            best_avg = avg
            best_type = mt

    # Active window from heatmap
    active_window = _derive_best_time(heatmap) if heatmap else None

    # Trending audio count
    audio_count = sum(1 for t in trends if t.trend_type == "audio")

    # Competition level (based on number of rising trends)
    rising_count = sum(1 for t in trends if t.momentum == "rising")
    peaking_count = sum(1 for t in trends if t.momentum == "peaking")
    if peaking_count >= 2:
        competition = "High"
    elif rising_count >= 2:
        competition = "Medium"
    else:
        competition = "Low"

    # Overall opportunity
    if peaking_count >= 2 and rising_count >= 1:
        overall = "Very High"
    elif rising_count >= 2:
        overall = "High"
    elif rising_count >= 1:
        overall = "Medium"
    else:
        overall = "Low"

    return DailyInsights(
        audience_active_window=active_window,
        best_content_type=best_type,
        trending_audio_count=audio_count,
        competition_level=competition,
        overall_opportunity=overall,
    )


def _fallback_recommendations(
    creator_intelligence: CreatorIntelligence,
    trends: List[GlobalTrend],
) -> List[TrendRecommendation]:
    style = _clean_text(
        creator_intelligence.content_style_summary,
        fallback="the creator's recent content style",
    )
    strengths = [
        _clean_text(strength)
        for strength in (creator_intelligence.creator_strengths or [])
        if _clean_text(strength)
    ]
    strength_text = strengths[0] if strengths else "their strongest recurring themes"

    fallback_trends = trends[:3]
    if not fallback_trends:
        fallback_trends = [
            GlobalTrend(
                topic_name="Evergreen Content",
                trend_type="topic",
                momentum="rising",
                description="A reliable evergreen format for testing content-market fit.",
            )
        ]

    recommendations: list[TrendRecommendation] = []
    for index, trend in enumerate(fallback_trends, start=1):
        title_prefix = {
            "format": "Try the format",
            "audio": "Adapt the audio",
            "hashtag": "Test the hashtag",
            "topic": "Cover the topic",
        }.get(trend.trend_type, "Test the trend")
        recommendations.append(
            TrendRecommendation(
                suggested_title=f"{title_prefix}: {trend.topic_name}",
                rationale=(
                    f"{trend.topic_name} is a {trend.momentum} {trend.trend_type} trend. "
                    f"It fits {style} and can build on {strength_text}."
                ),
                expected_impact=(
                    "Improves discovery and gives the creator a concrete trend-led post "
                    f"to test in slot {index}."
                ),
                trend_reference=trend.topic_name,
            )
        )

    return recommendations[:3]


async def generate_trend_recommendations(
    creator_intelligence: CreatorIntelligence,
    trends: List[GlobalTrend],
    recommendation_count: int = 5,
    posts: list[SinglePostInsights] | None = None,
    heatmap: list[HeatmapData] | None = None,
) -> tuple[List[TrendRecommendation], list[ContentGap], DailyInsights | None, list[str]]:
    """Generate up to `recommendation_count` actionable TrendRecommendation objects.

    Returns:
        Tuple of (recommendations, content_gaps, daily_insights, opportunity_bullets)
    """

    count = max(1, min(recommendation_count, 10))  # clamp 1-10
    posts = posts or []

    system_prompt = (
        "You are a Creative Director for short-form social video. Using the provided "
        f"creator intelligence, produce exactly {count} highly actionable TrendRecommendation "
        "objects tailored to the creator. Each object must include: suggested_title, "
        "rationale, expected_impact, trend_reference (optional), hook (a short attention-grabbing "
        "opening line), and content_style (e.g., 'Storytelling', 'Educational', 'POV/Lifestyle', "
        "'How-to', 'Day-in-life'). The rationale MUST explain WHY this trend fits the creator "
        "by referencing creator strengths and content style. Return ONLY valid TOON format "
        "(Token-Oriented Object Notation, YAML-like indentation, no braces, no quotes). "
        "Use 2-space indentation for nesting and '-' for list items. "
        "Do not include markdown, commentary, or extra keys.\n\n"
        "OUTPUT EXAMPLE (STRICT TOON ONLY):\n"
        "recommendations\n"
        "  -\n"
        "    suggested_title: The aesthetic morning routine\n"
        "    rationale: Visuals match your style\n"
        "    expected_impact: High engagement\n"
        "    trend_reference: Morning Vlog\n"
        "    hook: Nobody tells you this about morning routines...\n"
        "    content_style: Day-in-life\n"
        "\n"
        "Also produce 3-4 opportunity_bullets — short insights about content opportunities "
        "(e.g., 'Travel reels are underutilized'). Return as a TOON list after recommendations:\n"
        "opportunity_bullets\n"
        "  - Travel reels are underutilized\n"
        "  - Storytelling hooks outperform aesthetic content"
    )

    # Build user payload summarizing creator intelligence and trends
    strengths_text = "\n".join(f"- {s}" for s in (creator_intelligence.creator_strengths or []))
    style_summary = creator_intelligence.content_style_summary or ""

    trends_text_lines: list[str] = []
    for t in trends[:8]:
        trends_text_lines.append(f"- {t.topic_name} | type={t.trend_type} | momentum={t.momentum}")
    trends_text = "\n".join(trends_text_lines) or "- None"

    user_payload = (
        f"creator_strengths:\n{strengths_text or '- None'}\n\n"
        f"content_style_summary:\n{style_summary}\n\n"
        f"candidate_trends:\n{trends_text}\n\n"
        f"instruction: Produce exactly {count} actionable recommendations as a TOON list, "
        f"followed by opportunity_bullets."
    )

    prompt = {"system": system_prompt, "user": user_payload}

    llm = LLMClient(temperature=0.7, max_tokens=max(800, count * 200))

    try:
        raw = await asyncio.to_thread(llm.generate, prompt)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("Empty LLM response")

        text = raw.strip()

        # Parse recommendations
        results = toon_parse_list(raw, root_key="recommendations", model_cls=TrendRecommendation)

        # Parse opportunity_bullets from the raw text
        opportunity_bullets: list[str] = []
        if "opportunity_bullets" in text:
            bullets_section = text.split("opportunity_bullets")[-1]
            for line in bullets_section.splitlines():
                line = line.strip()
                if line.startswith("-"):
                    val = line[1:].strip()
                    if val:
                        opportunity_bullets.append(val)

        # Enrich recommendations with computed fields
        enriched: list[TrendRecommendation] = []
        for rec in results[:count]:
            # Find matching trend
            matching_trend = None
            for t in trends:
                if t.topic_name == rec.trend_reference:
                    matching_trend = t
                    break
            if matching_trend is None and trends:
                matching_trend = trends[0]

            # Compute opportunity score
            opp_score = None
            if matching_trend:
                opp_score = _compute_opportunity_score(matching_trend, creator_intelligence, posts)

            # Estimate reach
            reach_min, reach_max = (None, None)
            if matching_trend:
                reach_min, reach_max = _estimate_reach_range(posts, matching_trend.momentum)

            # Best time
            best_time = _derive_best_time(heatmap) if heatmap else None

            # Difficulty
            difficulty = _compute_difficulty(matching_trend, posts) if matching_trend else "Medium"

            enriched.append(TrendRecommendation(
                suggested_title=rec.suggested_title,
                rationale=rec.rationale,
                expected_impact=rec.expected_impact,
                trend_reference=rec.trend_reference,
                hook=rec.hook,
                content_style=rec.content_style,
                opportunity_score=opp_score,
                expected_reach_min=reach_min,
                expected_reach_max=reach_max,
                best_time=best_time,
                difficulty=difficulty,
            ))

        # Compute content gaps and daily insights
        content_gaps = _detect_content_gaps(posts, trends)
        daily_insights = _compute_daily_insights(posts, heatmap or [], trends) if posts else None

        return enriched, content_gaps, daily_insights, opportunity_bullets

    except Exception as e:
        logger.exception("generate_trend_recommendations failed: %s", e)
        fallback_recs = _fallback_recommendations(creator_intelligence, trends)
        content_gaps = _detect_content_gaps(posts, trends) if posts else []
        daily_insights = _compute_daily_insights(posts, heatmap or [], trends) if posts else None
        return fallback_recs, content_gaps, daily_insights, []
