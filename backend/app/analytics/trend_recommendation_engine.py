from __future__ import annotations

"""Generate trend recommendations for a creator using an LLM.

Exposes `generate_trend_recommendations` which instructs an LLM acting as a
Creative Director to produce three highly actionable `TrendRecommendation`
objects in TOON format. The function cross-references the provided
`CreatorIntelligence` with the list of `GlobalTrend` objects and ensures each
recommendation includes a clear rationale explaining why the trend fits the creator.
"""

import asyncio
import hashlib
from typing import List

from backend.app.ai.llm_client import LLMClient
from backend.app.ai.toon import loads as toon_loads
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
from backend.app.utils.telemetry import emit_counter


def _clean_text(value: object, *, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    text = " ".join(value.strip().split())
    return text or fallback


def _tokenize_text(value: object) -> set[str]:
    text = _clean_text(value).lower()
    if not text:
        return set()
    return {
        token
        for token in (
            "".join(ch for ch in raw if ch.isalnum())
            for raw in text.replace("/", " ").replace("-", " ").split()
        )
        if len(token) >= 3
    }


def _classify_format_family(
    trend: GlobalTrend | None,
    rec: TrendRecommendation | None,
) -> str:
    content_text = " ".join(
        part
        for part in [
            getattr(trend, "topic_name", None),
            getattr(trend, "description", None),
            getattr(rec, "suggested_title", None),
            getattr(rec, "rationale", None),
            getattr(rec, "hook", None),
            getattr(rec, "content_style", None),
        ]
        if isinstance(part, str) and part.strip()
    ).lower()

    if any(term in content_text for term in ("carousel", "slide", "slides", "swipe")):
        return "carousel"
    if any(term in content_text for term in ("photo", "static post", "single image", "lookbook", "image post")):
        return "photo"
    if trend and trend.trend_type == "format":
        return "reel"
    if any(term in content_text for term in ("reel", "video", "short-form", "grwm", "day in the life", "pov")):
        return "reel"
    return "reel"


def _classify_angle_type(
    trend: GlobalTrend | None,
    rec: TrendRecommendation | None,
) -> str:
    content_text = " ".join(
        part
        for part in [
            getattr(trend, "topic_name", None),
            getattr(trend, "description", None),
            getattr(rec, "suggested_title", None),
            getattr(rec, "rationale", None),
            getattr(rec, "expected_impact", None),
            getattr(rec, "hook", None),
            getattr(rec, "content_style", None),
        ]
        if isinstance(part, str) and part.strip()
    ).lower()
    content_style = _clean_text(getattr(rec, "content_style", None)).lower()

    if (
        "educational" in content_style
        or "how-to" in content_style
        or any(term in content_text for term in ("tips", "explained", "how to", "guide", "breakdown", "tutorial"))
    ):
        return "educational"
    if (
        "story" in content_style
        or "pov" in content_style
        or "lifestyle" in content_style
        or any(term in content_text for term in ("journey", "story", "experience", "day in the life", "grwm"))
    ):
        return "personal_story"
    if any(
        term in content_text
        for term in ("brand", "product", "review", "comparison", "storefront", "shop", "shopping", "affiliate", "sponsor", "ugc")
    ):
        return "brand_friendly"
    return "general"


def _classify_creator_level(
    difficulty: str | None,
    trend: GlobalTrend | None,
    rec: TrendRecommendation | None,
) -> str:
    difficulty_value = _clean_text(difficulty).lower()
    content_text = " ".join(
        part
        for part in [
            getattr(trend, "description", None),
            getattr(rec, "suggested_title", None),
            getattr(rec, "rationale", None),
            getattr(rec, "expected_impact", None),
        ]
        if isinstance(part, str) and part.strip()
    ).lower()

    if difficulty_value in {"easy", "quick"}:
        return "beginner"
    if difficulty_value in {"hard", "production-heavy"}:
        return "advanced"
    if any(term in content_text for term in ("deep dive", "research", "analysis", "framework", "breakdown", "multi-step")):
        return "advanced"
    return "intermediate"


# ── Opportunity scoring helpers ────────────────────────────────────────────────

_MOMENTUM_SCORES: dict[str, float] = {
    "rising": 30.0,
    "peaking": 40.0,
    "falling": 10.0,
}


def momentum_score(momentum: str | None) -> float:
    return _MOMENTUM_SCORES.get(str(momentum or "").lower(), 20.0)

_TREND_TYPE_SCORES: dict[str, float] = {
    "format": 20.0,
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
    - Content type match (0-20): format trends score higher for video creators
    - Recency boost (0-10): based on post frequency
    """
    # Momentum component (0-40)
    momentum_score_value = momentum_score(trend.momentum)

    # Niche fit component (0-30)
    niche_score = 15.0  # default mid-range
    primary = (creator_intelligence.content_style_summary or "").lower()
    trend_name = (trend.topic_name or "").lower()
    trend_desc = (trend.description or "").lower()
    combined_text = f"{trend_name} {trend_desc}"
    creator_tokens = set()
    creator_tokens |= _tokenize_text(creator_intelligence.content_style_summary)
    for strength in creator_intelligence.creator_strengths or []:
        creator_tokens |= _tokenize_text(strength)
    for theme in creator_intelligence.top_performing_themes or []:
        creator_tokens |= _tokenize_text(theme)
    trend_tokens = _tokenize_text(combined_text)

    category_scores: list[float] = []
    for category, keywords in _NICHE_CATEGORY_KEYWORDS.items():
        category_lower = category.lower()
        if category_lower in primary:
            keyword_hits = sum(1 for kw in keywords if kw in combined_text)
            if keyword_hits >= 2:
                category_scores.append(28.0)
            elif keyword_hits >= 1:
                category_scores.append(22.0)
            else:
                category_scores.append(12.0)
    if category_scores:
        niche_score = max(category_scores)
    else:
        overlap_count = len((creator_tokens & trend_tokens) - {"with", "from", "your", "this"})
        if overlap_count >= 4:
            niche_score = 28.0
        elif overlap_count >= 2:
            niche_score = 22.0
        elif overlap_count >= 1:
            niche_score = 18.0
        elif creator_tokens:
            niche_score = 14.0

    # Content type match component (0-20)
    type_score = _TREND_TYPE_SCORES.get(trend.trend_type, 10.0)
    # Boost formats for video-heavy creators.
    if posts:
        video_count = sum(
            1 for p in posts
            if (getattr(p, "media_type", "") or "").upper() in ("REEL", "VIDEO")
        )
        if video_count > len(posts) * 0.5:
            if trend.trend_type == "format":
                type_score = min(20.0, type_score + 5.0)

    # Recency component (0-10)
    recency_score = 7.0
    if posts and len(posts) >= 5:
        recency_score = 10.0
    elif posts and len(posts) >= 3:
        recency_score = 8.0

    total = momentum_score_value + niche_score + type_score + recency_score
    return round(min(100.0, max(0.0, total)), 1)


def _parse_opportunity_bullets(text: str) -> list[str]:
    try:
        parsed = toon_loads(text.strip())
    except Exception:
        return []

    if not isinstance(parsed, dict):
        return []

    raw_bullets = parsed.get("opportunity_bullets")
    if not isinstance(raw_bullets, list):
        return []

    bullets: list[str] = []
    for item in raw_bullets:
        value = _clean_text(item)
        if value:
            bullets.append(value)
    return bullets


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


def _compute_execution_effort(
    trend: GlobalTrend,
    posts: list[SinglePostInsights] | None = None,
) -> tuple[str, str]:
    """Estimate execution effort from the proposed format and production requirements."""
    description = " ".join((trend.topic_name or "", trend.description or "")).lower()
    format_family = _classify_format_family(trend, None)
    media_type_by_family = {"reel": "REEL", "carousel": "CAROUSEL", "photo": "IMAGE"}
    familiar_count = sum(
        1
        for post in posts or []
        if (getattr(post, "media_type", "") or "").strip().upper()
        == media_type_by_family[format_family]
    )

    production_terms = (
        "deep dive", "research", "analysis", "tutorial", "how-to", "interview",
        "case study", "comparison", "multi-step", "multi step", "b-roll", "b roll",
    )
    quick_terms = ("quick", "simple", "casual", "template", "prompt", "short")
    if format_family == "carousel" or any(term in description for term in production_terms):
        return (
            "Production-heavy",
            "This angle needs structured research, multiple assets, or a slide-by-slide explanation.",
        )
    if trend.trend_type == "format" or trend.trend_type == "hashtag" or any(
        term in description for term in quick_terms
    ):
        familiarity = (
            f" You have used this format in {familiar_count} recent posts."
            if familiar_count
            else " It can be created with a simple repeatable format."
        )
        return "Quick", f"This is a repeatable {format_family} format that can be produced quickly.{familiarity}"
    return "Planned", "This needs a clear outline and a focused filming or design pass."


def _explicit_trend_format_family(trend: GlobalTrend) -> str | None:
    """Return a format only when the trend explicitly names one; never infer reels by default."""
    text = f"{trend.topic_name} {trend.description}".lower()
    if any(term in text for term in ("carousel", "slide", "slides", "swipe")):
        return "carousel"
    if any(term in text for term in ("photo", "static post", "single image", "lookbook", "image post")):
        return "photo"
    if trend.trend_type == "format" or any(term in text for term in ("reel", "video", "short-form", "pov", "day in the life")):
        return "reel"
    return None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    return ordered[midpoint] if len(ordered) % 2 else (ordered[midpoint - 1] + ordered[midpoint]) / 2


def _opportunity_id(kind: str) -> str:
    value = kind.encode("utf-8")
    return f"opportunity_{hashlib.sha256(value).hexdigest()[:16]}"


def _detect_content_gaps(
    posts: list[SinglePostInsights],
    trends: list[GlobalTrend],
) -> list[ContentGap]:
    """Return ranked, evidence-backed content opportunities from enough recent posts."""
    if len(posts) < 5:
        return []

    opportunities: list[ContentGap] = []

    # Check content type diversity
    type_counts: dict[str, int] = {}
    for post in posts:
        mt = (getattr(post, "media_type", "") or "").strip().upper()
        if mt:
            type_counts[mt] = type_counts.get(mt, 0) + 1

    total = len(posts)
    trend_format_families = {family for trend in trends if (family := _explicit_trend_format_family(trend))}
    type_definitions = {
        "REEL": ("reel", "reel"),
        "CAROUSEL": ("carousel", "carousel"),
        "IMAGE": ("photo", "photo"),
    }
    for content_type, (label, family) in type_definitions.items():
        count = type_counts.get(content_type, 0)
        pct = (count / total * 100) if total > 0 else 0
        if pct < 10 and count < 3 and family in trend_format_families:
            matching_posts = [post for post in posts if (getattr(post, "media_type", "") or "").upper() == content_type]
            baseline_posts = [post for post in posts if getattr(post, "derived_metrics", None)]
            metric_names = ("engagement_rate", "save_rate", "share_rate")
            baseline = sum(
                _median([_safe_float(getattr(post.derived_metrics, metric, None)) or 0.0 for post in baseline_posts]) or 0.0
                for metric in metric_names
            )
            format_performance = sum(
                _median([_safe_float(getattr(post.derived_metrics, metric, None)) or 0.0 for post in matching_posts]) or 0.0
                for metric in metric_names
            )
            momentum = max(({"peaking": 20.0, "rising": 15.0, "falling": 5.0}.get(trend.momentum, 10.0) for trend in trends if _explicit_trend_format_family(trend) == family), default=10.0)
            performance_upside = 15.0 if not matching_posts else max(0.0, min(15.0, (baseline - format_performance) * 300.0))
            priority = min(95.0, 45.0 + momentum + (15.0 if count == 0 else 7.0) + performance_upside)
            evidence = f"Only {count} of your last {total} posts were {label}s ({pct:.0f}%)."
            if baseline_posts:
                evidence += " Priority reflects recent engagement, saves, and shares alongside active trend momentum."
            opportunities.append(ContentGap(
                id=_opportunity_id(f"format:{family}"),
                description=f"Test a {label} format this week",
                severity="opportunity",
                suggested_action=f"Use a current trend to publish one focused {label} and compare saves and reach.",
                evidence=evidence,
                priority_score=priority,
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

    storytelling_formats = {
        token
        for trend in trends if trend.trend_type == "format"
        for token in ("pov", "storytime", "tutorial")
        if token in f"{trend.topic_name} {trend.description}".lower()
    }
    if storytelling_formats and not trend_types_used.intersection(storytelling_formats):
        format_label = ", ".join(sorted(storytelling_formats))
        evidence = f"None of your last {total} captions used POV, storytime, or tutorial framing."
        storytelling_momentum = max(
            (
                {"peaking": 20.0, "rising": 15.0, "falling": 5.0}.get(trend.momentum, 10.0)
                for trend in trends
                if trend.trend_type == "format"
                and any(token in f"{trend.topic_name} {trend.description}".lower() for token in storytelling_formats)
            ),
            default=10.0,
        )
        novelty_bonus = 12.0 if not trend_types_used else 6.0
        priority = min(95.0, 48.0 + storytelling_momentum + novelty_bonus)
        opportunities.append(ContentGap(
            id=_opportunity_id(f"storytelling:{format_label}"),
            description=f"Try the active {format_label} format",
            severity="opportunity",
            suggested_action="Adapt one relevant POV, storytime, or tutorial structure to your niche this week.",
            evidence=evidence,
            priority_score=priority,
        ))

    return sorted(opportunities, key=lambda opportunity: opportunity.priority_score or 0, reverse=True)


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
        return []

    recommendations: list[TrendRecommendation] = []
    for index, trend in enumerate(fallback_trends, start=1):
        title_prefix = {
            "format": "Try the format",
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
                format_family=_classify_format_family(trend, None),
                angle_type=_classify_angle_type(trend, None),
                creator_level="intermediate",
                is_trending=trend.momentum in {"rising", "peaking"},
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
        opportunity_bullets = _parse_opportunity_bullets(text)

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

            # Execution effort is evidence-based; the field name remains backwards compatible.
            difficulty, effort_reason = (
                _compute_execution_effort(matching_trend, posts)
                if matching_trend
                else ("Planned", "This idea needs a short planning and production pass.")
            )
            format_family = _classify_format_family(matching_trend, rec)
            angle_type = _classify_angle_type(matching_trend, rec)
            creator_level = _classify_creator_level(difficulty, matching_trend, rec)
            is_trending = bool(matching_trend and matching_trend.momentum in {"rising", "peaking"})

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
                effort_reason=effort_reason,
                format_family=format_family,
                angle_type=angle_type,
                creator_level=creator_level,
                is_trending=is_trending,
            ))

        # Compute content gaps and daily insights
        content_gaps = _detect_content_gaps(posts, trends)
        daily_insights = _compute_daily_insights(posts, heatmap or [], trends) if posts else None

        return enriched, content_gaps, daily_insights, opportunity_bullets

    except Exception as e:
        logger.exception("generate_trend_recommendations failed: %s", e)
        emit_counter("trends_fallback_used", tags={"reason": type(e).__name__})
        fallback_recs = _fallback_recommendations(creator_intelligence, trends)
        content_gaps = _detect_content_gaps(posts, trends) if posts else []
        daily_insights = _compute_daily_insights(posts, heatmap or [], trends) if posts else None
        return fallback_recs, content_gaps, daily_insights, []
