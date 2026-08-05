from __future__ import annotations

"""Orchestration service that runs niche discovery, global trend fetching,
and recommendation generation for a creator.
"""

from typing import List

from backend.app.analytics.niche_discovery_engine import discover_creator_niche
from backend.app.analytics.global_trend_engine import fetch_global_trends
from backend.app.analytics.trend_recommendation_engine import generate_trend_recommendations
from backend.app.domain.post_models import SinglePostInsights
from backend.app.domain.account_models import CreatorIntelligence, HeatmapData
from backend.app.domain.trend_models import CreatorNiche, TrendAnalysisResult, WeeklyOpportunity
from backend.app.utils.logger import logger
from backend.app.utils.number_utils import safe_float as _safe_float


class TrendDataUnavailableError(RuntimeError):
    """Raised when the trend pipeline cannot produce usable trend data."""


def _build_heatmap_from_posts(posts: list[SinglePostInsights]) -> list[HeatmapData]:
    """Build a simple engagement heatmap from post timing and engagement rates."""
    heat_bins: dict[tuple[int, int], list[float]] = {}
    for post in posts:
        published_at = post.published_at
        if published_at is None:
            continue
        if not hasattr(published_at, "weekday") or not hasattr(published_at, "hour"):
            continue
        day = published_at.weekday()
        hour = published_at.hour
        key = (day, hour)
        er = _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
        if er is not None and er >= 0:
            heat_bins.setdefault(key, []).append(er)

    if not heat_bins:
        return []

    max_count = max(len(v) for v in heat_bins.values()) or 1
    heatmap: list[HeatmapData] = []
    for (day, hour), ers in heat_bins.items():
        count_weight = len(ers) / max_count
        avg_er = sum(ers) / len(ers) if ers else 0.0
        er_weight = min(1.0, avg_er / 0.10)
        intensity = round(min(1.0, max(0.0, count_weight * 0.4 + er_weight * 0.6)), 3)
        heatmap.append(HeatmapData(day_of_week=day, hour_of_day=hour, intensity=intensity))
    return heatmap


def _derive_creator_intelligence(
    creator_intelligence: CreatorIntelligence,
    posts: List[SinglePostInsights],
    niche: CreatorNiche,
) -> CreatorIntelligence:
    if (
        creator_intelligence.content_style_summary
        or creator_intelligence.creator_strengths
        or creator_intelligence.top_performing_themes
    ):
        return creator_intelligence

    media_types: dict[str, int] = {}
    themes: list[str] = []
    seen_themes: set[str] = set()
    for post in posts[:20]:
        media_type = getattr(post, "media_type", None)
        if isinstance(media_type, str) and media_type.strip():
            key = media_type.strip().upper()
            media_types[key] = media_types.get(key, 0) + 1
        for token in (getattr(post, "caption_text", None) or "").lower().replace("#", " ").split():
            word = "".join(ch for ch in token if ch.isalnum())
            if len(word) < 4 or word in seen_themes:
                continue
            seen_themes.add(word)
            themes.append(word)
            if len(themes) >= 5:
                break

    top_media = max(media_types.items(), key=lambda item: item[1])[0] if media_types else "post"
    niche_label = niche.primary_category.lower()
    sub_niches = ", ".join(niche.sub_niches[:3]) if niche.sub_niches else niche_label
    return CreatorIntelligence(
        content_style_summary=f"Creates mostly {top_media.lower()} content around {sub_niches}.",
        creator_strengths=[
            f"Clear {niche_label} positioning",
            "Reusable recent-post themes",
        ],
        top_performing_themes=themes[:5] or niche.sub_niches[:5],
    )


class CreatorTrendService:
    """Service to produce trend analysis results for a creator.

    Usage:
        service = CreatorTrendService()
        result = await service.get_trends_and_recommendations(...)
    """

    async def get_trends_and_recommendations(
        self,
        account_id: str,
        posts: List[SinglePostInsights],
        bio: str | None,
        username: str | None,
        creator_intelligence: CreatorIntelligence,
        recommendation_count: int = 5,
    ) -> TrendAnalysisResult:
        """Run the full trend analysis pipeline and return consolidated results.

        Workflow:
        1. discover_creator_niche
        2. fetch_global_trends
        3. generate_trend_recommendations (up to recommendation_count items)

        Logs progress and raises a RuntimeError on unexpected orchestration errors.
        """

        logger.info("[CreatorTrendService] Starting trend analysis for account=%s", account_id)

        try:
            niche = await discover_creator_niche(posts, bio, username)
            trends = await fetch_global_trends(niche)
            if not trends:
                raise TrendDataUnavailableError("Global trends unavailable")
            enriched_intelligence = _derive_creator_intelligence(creator_intelligence, posts, niche)

            # Build heatmap from posts for timing recommendations
            heatmap = _build_heatmap_from_posts(posts)

            recs, content_gaps, daily_insights, opportunity_bullets = await generate_trend_recommendations(
                enriched_intelligence,
                trends,
                recommendation_count=recommendation_count,
                posts=posts,
                heatmap=heatmap,
            )

            result = TrendAnalysisResult(
                niche=niche,
                global_trends=trends,
                recommendations=recs,
                content_gaps=content_gaps,
                daily_insights=daily_insights,
                opportunity_bullets=opportunity_bullets,
            )
            result.weekly_opportunity = build_weekly_opportunity(
                niche=niche,
                trends=trends,
                recommendations=recs,
                content_gaps=content_gaps,
                opportunity_bullets=opportunity_bullets,
            )
            logger.info("[CreatorTrendService] Completed trend analysis for account=%s", account_id)
            return result

        except TrendDataUnavailableError:
            logger.warning("[CreatorTrendService] No usable trend data for account=%s", account_id)
            raise
        except Exception as exc:
            logger.error("[CreatorTrendService] Orchestration failed for account=%s: %s", account_id, exc)
            raise RuntimeError("Creator trend orchestration failed") from exc


__all__ = ["CreatorTrendService", "TrendDataUnavailableError"]


def build_weekly_opportunity(
    niche: CreatorNiche | None,
    trends: list,
    recommendations: list,
    content_gaps: list | None,
    opportunity_bullets: list[str] | None,
) -> WeeklyOpportunity:
    """Build a truthful weekly opportunity summary from available trend-analysis data."""
    trends = trends or []
    recommendations = recommendations or []
    content_gaps = content_gaps or []
    opportunity_bullets = [str(item).strip() for item in (opportunity_bullets or []) if str(item).strip()]

    recommendation_scores = [
        float(getattr(rec, "opportunity_score", 0) or 0)
        for rec in recommendations
        if getattr(rec, "opportunity_score", None) is not None
    ]
    avg_recommendation_score = sum(recommendation_scores) / len(recommendation_scores) if recommendation_scores else 0.0
    rising_count = sum(1 for trend in trends if getattr(trend, "momentum", None) == "rising")
    peaking_count = sum(1 for trend in trends if getattr(trend, "momentum", None) == "peaking")
    opportunity_gap_count = sum(1 for gap in content_gaps if getattr(gap, "severity", "") == "opportunity")
    niche_confidence = float(getattr(niche, "confidence_score", 0) or 0)

    score = (
        avg_recommendation_score * 0.55
        + min(15.0, rising_count * 4.0 + peaking_count * 5.0)
        + niche_confidence * 20.0
        + min(10.0, opportunity_gap_count * 3.0)
    )
    score = int(round(max(0.0, min(100.0, score))))

    if score >= 85:
        label = "Very High"
    elif score >= 70:
        label = "High"
    elif score >= 50:
        label = "Medium"
    else:
        label = "Low"

    primary_niche = getattr(niche, "primary_category", None) or "your niche"
    top_trend = getattr(trends[0], "topic_name", None) if trends else None
    summary_reason = (
        f"{primary_niche} is well aligned with this week's trend mix"
        f"{f', especially {top_trend}' if top_trend else ''},"
        " giving you strong chances to publish timely ideas with clear audience fit."
    )

    bullets = opportunity_bullets[:4]
    if not bullets:
        derived_bullets: list[str] = []
        if rising_count:
            derived_bullets.append(f"{rising_count} rising trend{'s' if rising_count != 1 else ''} are relevant to your audience.")
        if recommendation_scores:
            derived_bullets.append(f"Your current recommendation set averages {round(avg_recommendation_score)}/100 in opportunity score.")
        if peaking_count:
            derived_bullets.append(f"{peaking_count} peaking trend{'s' if peaking_count != 1 else ''} can help drive discovery quickly.")
        if opportunity_gap_count:
            derived_bullets.append(f"{opportunity_gap_count} content gap{'s' if opportunity_gap_count != 1 else ''} could turn into near-term wins.")
        bullets = derived_bullets[:4]

    return WeeklyOpportunity(
        score=score,
        label=label,
        idea_count=len(recommendations),
        summary_reason=summary_reason,
        bullets=bullets,
    )


def attach_weekly_opportunity(result: TrendAnalysisResult) -> TrendAnalysisResult:
    """Ensure a trend analysis result includes a weekly opportunity payload."""
    if result.weekly_opportunity is None:
        result.weekly_opportunity = build_weekly_opportunity(
            niche=result.niche,
            trends=result.global_trends,
            recommendations=result.recommendations,
            content_gaps=result.content_gaps,
            opportunity_bullets=result.opportunity_bullets,
        )
    return result
