"""Deterministic account-level aggregation and Account Health Score (AHS)."""


from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean, median, pstdev
from typing import Any

from backend.app.domain.account_models import (
    AccountEngagementSignals,
    AccountHealthMetadata,
    AccountHealthScore,
    AccountVisionSummary,
    AISummary,
    AudienceDemographics,
    AudienceInsights,
    BrandReadiness,
    ChartSeries,
    ContentPillar,
    ContentTypeBreakdownEntry,
    ContentTypePerformance,
    ConversionFunnel,
    CoreMetricsDashboard,
    DeterministicDriver,
    DeterministicRecommendation,
    HashtagPerformance,
    HeatmapData,
    MetricWithTrend,
    NicheBenchmark,
    PillarScore,
    TopPostSummary,
)
from backend.app.domain.post_models import SinglePostInsights
from backend.app.utils.logger import logger
from backend.app.utils.number_utils import safe_float as _safe_float


PILLAR_WEIGHTS: dict[str, float] = {
    # Spec-aligned weighted composite (normalized over available pillars).
    "content_quality": 0.30,
    "engagement_quality": 0.25,
    "niche_fit": 0.15,
    "consistency": 0.15,
    "brand_safety": 0.15,
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _score_to_band(score: float) -> str:
    if score < 40.0:
        return "NEEDS_WORK"
    if score < 60.0:
        return "AVERAGE"
    if score < 80.0:
        return "STRONG"
    return "EXCEPTIONAL"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sort_recent_posts(posts: list[SinglePostInsights]) -> list[SinglePostInsights]:
    def _sort_key(post: SinglePostInsights) -> float:
        published_at = post.published_at
        if isinstance(published_at, datetime):
            return _as_utc(published_at).timestamp()
        return float("-inf")

    return sorted(posts, key=_sort_key, reverse=True)


def _mean_or_none(values: list[float]) -> float | None:
    return mean(values) if values else None

def _map_ratio_to_score(ratio: float) -> float:
    if ratio <= 0.6:
        return 30.0
    if ratio <= 0.9:
        return 50.0
    if ratio <= 1.1:
        return 70.0
    if ratio <= 1.4:
        return 85.0
    return 95.0


def _map_absolute_er_to_score(engagement_rate: float) -> float:
    if engagement_rate <= 0.01:
        return 30.0
    if engagement_rate <= 0.03:
        return 50.0
    if engagement_rate <= 0.06:
        return 70.0
    if engagement_rate <= 0.10:
        return 85.0
    return 95.0


def _map_posts_per_week_to_score(posts_per_week: float) -> float:
    if posts_per_week <= 0.5:
        return 30.0
    if posts_per_week <= 1.5:
        return 50.0
    if posts_per_week <= 3.0:
        return 70.0
    if posts_per_week <= 6.0:
        return 85.0
    return 95.0


def _map_stddev_to_consistency(stddev_score: float) -> float:
    if stddev_score >= 25.0:
        return 40.0
    if stddev_score >= 18.0:
        return 55.0
    if stddev_score >= 12.0:
        return 70.0
    if stddev_score >= 7.0:
        return 85.0
    return 95.0


def _build_content_quality(posts: list[SinglePostInsights]) -> tuple[float, list[str], bool, dict[str, float | None]]:
    notes: list[str] = []
    per_post_scores: list[float] = []
    s1_values: list[float] = []
    s2_values: list[float] = []
    s3_values: list[float] = []
    missing_s1 = 0
    missing_s2 = 0
    missing_s3 = 0

    for post in posts:
        s1 = _safe_float(getattr(post.visual_quality_score, "total", None))
        s2 = _safe_float(getattr(post.caption_effectiveness_score, "total_0_50", None))
        s3 = _safe_float(getattr(post.content_clarity_score, "total", None))
        components = [value for value in (s1, s2, s3) if value is not None]

        if s1 is None:
            missing_s1 += 1
        else:
            s1_values.append(s1)
        if s2 is None:
            missing_s2 += 1
        else:
            s2_values.append(s2)
        if s3 is None:
            missing_s3 += 1
        else:
            s3_values.append(s3)

        if components:
            per_post_scores.append(mean(components))

    if not per_post_scores:
        notes.append("No S1/S2/S3 components available; using neutral content quality baseline.")
        return 50.0, notes, False, {"mean_s1_0_50": None, "mean_s2_0_50": None, "mean_s3_0_50": None}

    post_count = len(posts) or 1
    for name, missing_count in (("S1", missing_s1), ("S2", missing_s2), ("S3", missing_s3)):
        missing_rate = missing_count / post_count
        if missing_rate > 0.0:
            notes.append(f"{name} missing on {missing_rate * 100:.0f}% of posts; normalized over available components.")

    mean_content_0_50 = mean(per_post_scores)
    score_0_100 = _clamp(mean_content_0_50 * 2.0, 0.0, 100.0)
    return score_0_100, notes, True, {
        "mean_s1_0_50": _mean_or_none(s1_values),
        "mean_s2_0_50": _mean_or_none(s2_values),
        "mean_s3_0_50": _mean_or_none(s3_values),
    }


def _build_engagement_quality(
    posts: list[SinglePostInsights],
    account_avg_engagement_rate: float | None,
) -> tuple[float, list[str], bool, dict[str, float | None]]:
    notes: list[str] = []
    engagement_rates: list[float] = []
    save_rates: list[float] = []
    share_rates: list[float] = []

    for post in posts:
        er = _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
        if er is not None:
            engagement_rates.append(max(0.0, er))
        save_rate = _safe_float(getattr(post.derived_metrics, "save_rate", None))
        if save_rate is not None:
            save_rates.append(max(0.0, save_rate))
        share_rate = _safe_float(getattr(post.derived_metrics, "share_rate", None))
        if share_rate is not None:
            share_rates.append(max(0.0, share_rate))

    if not engagement_rates:
        notes.append("Missing engagement_rate data; using neutral engagement quality baseline.")
        return 50.0, notes, False, {
            "median_engagement_rate": None,
            "ratio_vs_account_avg": None,
            "median_save_rate": median(save_rates) if save_rates else None,
            "median_share_rate": median(share_rates) if share_rates else None,
        }

    median_engagement_rate = median(engagement_rates)
    ratio_vs_account_avg: float | None = None
    if account_avg_engagement_rate is not None and account_avg_engagement_rate > 0:
        ratio_vs_account_avg = median_engagement_rate / account_avg_engagement_rate
        score = _map_ratio_to_score(ratio_vs_account_avg)
        notes.append(
            "Engagement quality benchmarked against account average engagement rate "
            f"(ratio={ratio_vs_account_avg:.2f})."
        )
    else:
        score = _map_absolute_er_to_score(median_engagement_rate)
        notes.append("Account average engagement rate unavailable; used absolute ER band mapping.")

    median_save_rate = median(save_rates) if save_rates else None
    median_share_rate = median(share_rates) if share_rates else None
    if median_save_rate is not None and median_share_rate is not None:
        save_share_sum = median_save_rate + median_share_rate
        if save_share_sum >= 0.05:
            score += 5.0
            notes.append("Strong save/share signal boosted engagement quality.")
        elif save_share_sum <= 0.01:
            score -= 5.0
            notes.append("Weak save/share signal reduced engagement quality.")

    return _clamp(score, 0.0, 100.0), notes, True, {
        "median_engagement_rate": median_engagement_rate,
        "ratio_vs_account_avg": ratio_vs_account_avg,
        "median_save_rate": median_save_rate,
        "median_share_rate": median_share_rate,
    }


def _build_niche_fit(
    posts: list[SinglePostInsights],
    niche_avg_engagement_rate: float | None,
    follower_band: str | None,
    median_engagement_rate: float | None,
) -> tuple[float, list[str], bool, dict[str, float | None]]:
    notes: list[str] = []
    s4_values: list[float] = []
    for post in posts:
        value = _safe_float(getattr(post.audience_relevance_score, "total_0_50", None))
        if value is not None:
            s4_values.append(value)

    if s4_values:
        base_score = _clamp(mean(s4_values) * 2.0, 0.0, 100.0)
        has_signal = True
    else:
        base_score = 50.0
        has_signal = False
        notes.append("S4 audience relevance missing across posts; using neutral niche fit baseline.")

    score = base_score
    niche_ratio: float | None = None
    if (
        niche_avg_engagement_rate is not None
        and niche_avg_engagement_rate > 0
        and median_engagement_rate is not None
    ):
        niche_ratio = median_engagement_rate / niche_avg_engagement_rate
        niche_ratio_score = _map_ratio_to_score(niche_ratio)
        score = _clamp(base_score * 0.70 + niche_ratio_score * 0.30, 0.0, 100.0)
        notes.append(f"Niche fit blended with niche ER benchmark ratio ({niche_ratio:.2f}).")
    elif niche_avg_engagement_rate is None:
        notes.append("Niche average engagement benchmark unavailable; niche fit based on S4 only.")

    if isinstance(follower_band, str) and follower_band.strip():
        notes.append(f"Follower band context: {follower_band.strip()}.")

    if len(s4_values) < len(posts):
        missing_rate = ((len(posts) - len(s4_values)) / max(1, len(posts))) * 100
        notes.append(f"S4 missing for {missing_rate:.0f}% of posts.")

    return score, notes, has_signal, {
        "mean_s4_0_50": _mean_or_none(s4_values),
        "niche_ratio": niche_ratio,
    }


def _build_consistency(posts: list[SinglePostInsights]) -> tuple[float, list[str], bool, dict[str, float | None], int | None]:
    notes: list[str] = []
    posting_score: float | None = None
    performance_score: float | None = None
    posts_per_week: float | None = None
    weighted_stddev: float | None = None
    time_window_days: int | None = None

    timestamps = [
        _as_utc(post.published_at)
        for post in posts
        if isinstance(post.published_at, datetime)
    ]
    if len(timestamps) >= 2:
        newest = max(timestamps)
        oldest = min(timestamps)
        window_seconds = max(1.0, (newest - oldest).total_seconds())
        time_window_days = max(1, int(window_seconds // 86400) + 1)
        posts_per_week = len(timestamps) / (time_window_days / 7.0)
        posting_score = _map_posts_per_week_to_score(posts_per_week)
    else:
        notes.append("Insufficient timestamps for posting cadence calculation.")

    weighted_scores: list[float] = []
    for post in posts:
        weighted_score = _safe_float(getattr(post.weighted_post_score, "score", None))
        if weighted_score is not None:
            weighted_scores.append(_clamp(weighted_score, 0.0, 100.0))

    if len(weighted_scores) >= 2:
        weighted_stddev = pstdev(weighted_scores)
        performance_score = _map_stddev_to_consistency(weighted_stddev)
    else:
        notes.append("Insufficient weighted score history for performance variance.")

    components = [value for value in (posting_score, performance_score) if value is not None]
    if not components:
        notes.append("No consistency signals available; using neutral consistency baseline.")
        return 50.0, notes, False, {"posts_per_week": posts_per_week, "weighted_stddev": weighted_stddev}, time_window_days

    return mean(components), notes, True, {"posts_per_week": posts_per_week, "weighted_stddev": weighted_stddev}, time_window_days


def _build_brand_safety(posts: list[SinglePostInsights]) -> tuple[float, list[str], bool, dict[str, float | int]]:
    notes: list[str] = []
    s6_values: list[float] = []
    severe_count = 0
    penalty_counts: dict[str, int] = {}
    flag_counts: dict[str, int] = {}

    for post in posts:
        total_0_50 = _safe_float(getattr(post.brand_safety_score, "total_0_50", None))
        if total_0_50 is not None:
            s6_values.append(total_0_50)

        raw_0_100 = _safe_float(getattr(post.brand_safety_score, "s6_raw_0_100", None))
        if raw_0_100 is not None and raw_0_100 <= 40.0:
            severe_count += 1

        for penalty in getattr(post.brand_safety_score, "penalties", []):
            key = getattr(penalty, "key", None)
            if not isinstance(key, str) or not key.strip():
                continue
            penalty_counts[key] = penalty_counts.get(key, 0) + 1

        flags = getattr(post.brand_safety_score, "flags", {})
        if isinstance(flags, dict):
            for key, value in flags.items():
                if isinstance(key, str) and bool(value):
                    flag_counts[key] = flag_counts.get(key, 0) + 1

    if not s6_values:
        notes.append("S6 brand safety data missing; using neutral brand safety baseline.")
        return 50.0, notes, False, {"severe_count": severe_count}

    score = _clamp(mean(s6_values) * 2.0, 0.0, 100.0)
    if severe_count > 0:
        score = _clamp(score - 10.0, 0.0, 100.0)
        notes.append(f"Applied severe safety penalty due to {severe_count} post(s) with S6<=40/100.")

    if penalty_counts:
        ranked_penalties = sorted(penalty_counts.items(), key=lambda item: (-item[1], item[0]))
        top_penalties = ", ".join(f"{key} x{count}" for key, count in ranked_penalties[:3])
        notes.append(f"Top safety penalties: {top_penalties}.")

    if flag_counts:
        ranked_flags = sorted(flag_counts.items(), key=lambda item: (-item[1], item[0]))
        top_flags = ", ".join(f"{key} x{count}" for key, count in ranked_flags[:3])
        notes.append(f"Flag signals: {top_flags}.")

    return score, notes, True, {"severe_count": severe_count}


def _build_drivers_and_recommendations(
    content_quality: float,
    engagement_quality: float,
    niche_fit: float,
    consistency: float,
    brand_safety: float,
    min_history_threshold_met: bool,
    content_metrics: dict[str, float | None],
    engagement_metrics: dict[str, float | None],
    niche_metrics: dict[str, float | None],
    consistency_metrics: dict[str, float | None],
    brand_safety_metrics: dict[str, float | int],
) -> tuple[list[DeterministicDriver], list[DeterministicRecommendation]]:
    drivers: list[DeterministicDriver] = []
    recommendations: list[DeterministicRecommendation] = []

    if not min_history_threshold_met:
        drivers.append(
            DeterministicDriver(
                id="limited_history_context",
                label="Limited post history",
                type="LIMITING",
                explanation="Fewer than 10 posts in history; account-level confidence is reduced.",
            )
        )

    if content_quality < 50.0:
        drivers.append(
            DeterministicDriver(
                id="content_quality_low",
                label="Content clarity/quality needs improvement",
                type="LIMITING",
                explanation=(
                    "Mean content signals are low "
                    f"(S1={content_metrics.get('mean_s1_0_50')}, "
                    f"S2={content_metrics.get('mean_s2_0_50')}, "
                    f"S3={content_metrics.get('mean_s3_0_50')})."
                ),
            )
        )
        recommendations.extend(
            [
                DeterministicRecommendation(
                    id="improve_visual_hook_and_clarity",
                    text="Improve opening visual hook and framing to raise S1/S3 on most posts.",
                    impact_level="HIGH",
                ),
                DeterministicRecommendation(
                    id="strengthen_caption_structures",
                    text="Use stronger first-line hooks and clearer caption structures to raise S2.",
                    impact_level="HIGH",
                ),
            ]
        )

    if engagement_quality < 50.0:
        ratio = engagement_metrics.get("ratio_vs_account_avg")
        ratio_text = f"{ratio:.2f}" if isinstance(ratio, float) else "n/a"
        drivers.append(
            DeterministicDriver(
                id="engagement_quality_low",
                label="Engagement under benchmark",
                type="LIMITING",
                explanation=(
                    f"Median engagement performance trails benchmark (ratio={ratio_text})."
                ),
            )
        )
        recommendations.extend(
            [
                DeterministicRecommendation(
                    id="add_stronger_cta_patterns",
                    text="Add explicit CTA patterns (comment/save/share) in captions to lift interactions.",
                    impact_level="HIGH",
                ),
                DeterministicRecommendation(
                    id="optimize_for_saves_and_shares",
                    text="Prioritize utility-rich post formats that increase saves and shares.",
                    impact_level="MEDIUM",
                ),
            ]
        )

    if niche_fit < 50.0:
        mean_s4 = niche_metrics.get("mean_s4_0_50")
        mean_s4_text = f"{mean_s4:.2f}" if isinstance(mean_s4, float) else "n/a"
        drivers.append(
            DeterministicDriver(
                id="niche_fit_low",
                label="Content misaligned with audience",
                type="LIMITING",
                explanation=f"Average S4 audience relevance is low (mean S4={mean_s4_text}/50).",
            )
        )
        recommendations.append(
            DeterministicRecommendation(
                id="align_topics_with_niche",
                text="Align topics more tightly with the account's dominant niche categories.",
                impact_level="HIGH",
            )
        )

    if consistency < 50.0:
        posts_per_week = consistency_metrics.get("posts_per_week")
        stddev = consistency_metrics.get("weighted_stddev")
        ppw_text = f"{posts_per_week:.2f}" if isinstance(posts_per_week, float) else "n/a"
        std_text = f"{stddev:.2f}" if isinstance(stddev, float) else "n/a"
        drivers.append(
            DeterministicDriver(
                id="consistency_low",
                label="Inconsistent posting/performance",
                type="LIMITING",
                explanation=f"Cadence/performance consistency is weak (posts_per_week={ppw_text}, stddev={std_text}).",
            )
        )
        recommendations.append(
            DeterministicRecommendation(
                id="stabilize_posting_cadence",
                text="Maintain a steadier posting cadence and repeat higher-performing content templates.",
                impact_level="MEDIUM",
            )
        )

    severe_count = int(brand_safety_metrics.get("severe_count", 0))
    if brand_safety < 70.0 or severe_count > 0:
        drivers.append(
            DeterministicDriver(
                id="brand_safety_risks",
                label="Brand safety risks detected",
                type="LIMITING",
                explanation=f"Brand safety weakened by recurring penalties (severe_posts={severe_count}).",
            )
        )
        recommendations.extend(
            [
                DeterministicRecommendation(
                    id="reduce_safety_risk_terms",
                    text="Remove profanity/risky references and tighten moderation before publishing.",
                    impact_level="HIGH",
                ),
                DeterministicRecommendation(
                    id="reduce_hashtag_spam",
                    text="Reduce hashtag spam and improve caption signal quality to lower safety/relevance risks.",
                    impact_level="MEDIUM",
                ),
            ]
        )

    # Deduplicate recommendations by id while keeping deterministic order.
    deduped_recommendations: list[DeterministicRecommendation] = []
    seen_ids: set[str] = set()
    for recommendation in recommendations:
        if recommendation.id in seen_ids:
            continue
        deduped_recommendations.append(recommendation)
        seen_ids.add(recommendation.id)

    return drivers, deduped_recommendations



def _extract_hashtags_from_caption(caption: str) -> list[str]:
    """Extract hashtags from a caption string."""
    if not caption:
        return []
    return re.findall(r'#(\w+)', caption.lower())


def _calculate_brand_readiness(posts: list[SinglePostInsights], ahs_score: float) -> BrandReadiness:
    """Compute brand readiness score based on AHS and engagement signals."""
    if not posts:
        return BrandReadiness()
    engagement_rates = [
        _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
        for post in posts
    ]
    engagement_rates = [er for er in engagement_rates if er is not None]
    avg_er = sum(engagement_rates) / len(engagement_rates) if engagement_rates else 0.0
    score = (ahs_score * 0.6) + (min(avg_er / 0.10, 1.0) * 100.0 * 0.4)
    score = round(min(100.0, max(0.0, score)), 2)
    if score >= 80:
        label = "Highly Marketable"
    elif score >= 60:
        label = "Marketable"
    elif score >= 40:
        label = "Developing"
    else:
        label = "Early Stage"
    est_rate_per_post = round(avg_er * 5000, 2) if avg_er > 0 else None
    est_cpm = round(avg_er * 25, 2) if avg_er > 0 else None
    est_min = round(est_rate_per_post * 0.8, 2) if est_rate_per_post is not None else None
    est_max = round(est_rate_per_post * 1.2, 2) if est_rate_per_post is not None else None
    return BrandReadiness(
        score=score,
        label=label,
        est_rate_per_post=est_rate_per_post,
        est_rate_per_post_min=est_min,
        est_rate_per_post_max=est_max,
        est_cpm=est_cpm,
    )


def _build_core_metrics_dashboard(posts: list[SinglePostInsights], follower_count: int | None) -> CoreMetricsDashboard:
    """Build dashboard core metrics from posts."""
    if not posts:
        return CoreMetricsDashboard()
    reach_values = [_safe_float(getattr(post.core_metrics, "reach", None)) for post in posts]
    reach_values = [v for v in reach_values if v is not None]
    impression_values = [_safe_float(getattr(post.core_metrics, "impressions", None)) for post in posts]
    impression_values = [v for v in impression_values if v is not None]
    er_values = [_safe_float(getattr(post.derived_metrics, "engagement_rate", None)) for post in posts]
    er_values = [v for v in er_values if v is not None]
    pv_values = [_safe_float(getattr(post.core_metrics, "profile_visits", None)) for post in posts]
    pv_values = [v for v in pv_values if v is not None]

    total_reach = sum(reach_values)
    total_impressions = sum(impression_values)
    avg_er = round(sum(er_values) / len(er_values), 4) if er_values else None
    total_pv = sum(pv_values)

    followers_metric = MetricWithTrend(
        current_value=float(follower_count or 0), trend_percentage=None, label="Followers"
    )
    reach_metric = MetricWithTrend(
        current_value=total_reach if total_reach > 0 else None, trend_percentage=None, label="30D Reach"
    )
    impressions_metric = MetricWithTrend(
        current_value=total_impressions if total_impressions > 0 else None, trend_percentage=None, label="30D Impressions"
    )
    er_metric = MetricWithTrend(
        current_value=round(avg_er * 100, 2) if avg_er else None, trend_percentage=None, label="Engagement Rate"
    )
    pv_metric = MetricWithTrend(
        current_value=total_pv if total_pv > 0 else None, trend_percentage=None, label="30D Profile Visits"
    )
    vtfr = round((total_pv / (follower_count or 1)) * 100, 2) if total_pv > 0 and follower_count else None
    vtfr_metric = MetricWithTrend(
        current_value=vtfr, trend_percentage=None, label="Visit-to-Follow Rate"
    )

    return CoreMetricsDashboard(
        followers=followers_metric,
        reach_30d=reach_metric,
        impressions_30d=impressions_metric,
        engagement_rate=er_metric,
        profile_visits_30d=pv_metric,
        visit_to_follow_rate=vtfr_metric,
    )


def _build_growth_overview_chart(posts: list[SinglePostInsights], follower_count: int | None = None) -> list[ChartSeries]:
    """Build time-series chart data from post history.

    Note: followers is set to the current count for every data point
    (flat line) because Instagram API does not provide historical daily
    follower data. Replace with per-point follower counts when available.
    """
    sorted_posts = _sort_recent_posts(posts)
    series = []
    for post in sorted_posts:
        if post.published_at:
            reach = _safe_float(getattr(post.core_metrics, "reach", None))
            impressions = _safe_float(getattr(post.core_metrics, "impressions", None))
            date_str = (
                post.published_at.strftime("%Y-%m-%d")
                if hasattr(post.published_at, "strftime")
                else str(post.published_at)
            )
            series.append(
                ChartSeries(
                    date=date_str,
                    followers=float(follower_count) if follower_count else None,
                    reach=reach,
                    impressions=impressions if impressions else None,
                )
            )
    return series


def _extract_content_pillars(posts: list[SinglePostInsights]) -> list[ContentPillar]:
    """Derive content pillars from caption hashtags and post categories."""
    pillar_counter = Counter()
    for post in posts:
        caption = post.caption_text or ""
        hashtags = _extract_hashtags_from_caption(caption)
        category = (post.post_category or "").strip().lower()
        for tag in hashtags[:5]:
            pillar_counter[tag] += 1
        if category and category not in {"unknown", ""}:
            pillar_counter[category] += 1
    total = sum(pillar_counter.values()) or 1
    pillars = [
        ContentPillar(name=name, engagement_percentage=round((count / total) * 100, 2))
        for name, count in pillar_counter.most_common(6)
    ]
    return pillars


def _generate_engagement_heatmap(posts: list[SinglePostInsights]) -> list[HeatmapData]:
    """Generate a synthetic engagement heatmap from post timing."""
    heat_bins = Counter()
    er_bins = {}
    for post in posts:
        if post.published_at and hasattr(post.published_at, "weekday") and hasattr(post.published_at, "hour"):
            day = post.published_at.weekday()
            hour = post.published_at.hour
            key = (day, hour)
            heat_bins[key] += 1
            er = _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
            if er is not None:
                er_bins.setdefault(key, []).append(er)
    max_count = max(heat_bins.values()) if heat_bins else 1
    heatmap = []
    for (day, hour), count in heat_bins.items():
        count_weight = count / max_count
        er_list = er_bins.get((day, hour), [])
        er_weight = (sum(er_list) / len(er_list) / 0.10) if er_list else 0.5
        intensity = round(min(1.0, max(0.0, (count_weight * 0.4 + er_weight * 0.6))), 3)
        heatmap.append(HeatmapData(day_of_week=day, hour_of_day=hour, intensity=intensity))
    return heatmap


def _aggregate_hashtag_performance(posts: list[SinglePostInsights]) -> list[HashtagPerformance]:
    """Aggregate hashtag performance across all posts."""
    tag_posts = Counter()
    tag_reach = defaultdict(list)
    tag_er = defaultdict(list)
    for post in posts:
        caption = post.caption_text or ""
        hashtags = _extract_hashtags_from_caption(caption)
        reach = _safe_float(getattr(post.core_metrics, "reach", None))
        er = _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
        seen = set()
        for tag in hashtags:
            if tag in seen:
                continue
            seen.add(tag)
            tag_posts[tag] += 1
            if reach is not None:
                tag_reach[tag].append(reach)
            if er is not None:
                tag_er[tag].append(er)
    results = []
    for tag, count in tag_posts.most_common(10):
        avg_reach = round(sum(tag_reach.get(tag, [])) / len(tag_reach[tag]), 2) if tag_reach.get(tag) else None
        avg_er = round(sum(tag_er.get(tag, [])) / len(tag_er[tag]), 4) if tag_er.get(tag) else None
                # Thresholds based on Instagram benchmark data:
        #   >= 6% ER → strong niche fit, keep using
        #   3-6% ER  → moderate performance, test variations
        #   < 3% ER  → low engagement, consider dropping
        if avg_er and avg_er >= 0.06:
            impact = "Keep"
        elif avg_er and avg_er >= 0.03:
            impact = "Test"
        else:
            impact = "Drop"
        results.append(
            HashtagPerformance(hashtag=tag, post_count=count, reach=avg_reach, engagement_rate=avg_er, impact=impact)
        )
    return results


def _calculate_funnel_metrics(posts: list[SinglePostInsights]) -> ConversionFunnel:
    """Calculate profile-to-conversion funnel from post metrics."""
    total_pv = 0
    total_wt = 0
    for post in posts:
        total_pv += int(_safe_float(getattr(post.core_metrics, "profile_visits", None)) or 0)
        total_wt += int(_safe_float(getattr(post.core_metrics, "website_taps", None)) or 0)
    # Synthetic estimate: 15% visit-to-follow conversion.
    # Replace with real data from Instagram API when available.
    total_follows = int(total_pv * 0.15)
    vtfr = round((total_follows / total_pv) * 100, 2) if total_pv > 0 else None
    return ConversionFunnel(
        profile_visits=total_pv if total_pv > 0 else None,
        website_clicks=total_wt if total_wt > 0 else None,
        follows=total_follows if total_follows > 0 else None,
        profile_visit_to_follow_pct=vtfr,
    )


def _build_audience_insights(posts: list[SinglePostInsights]) -> AudienceInsights | None:
    """Build audience insights when real API data is available.

    Instagram Graph API does not currently expose audience viewer breakdown
    (new vs returning, follower quality, non-follower reach) or comment
    sentiment at the account level. Return None until a real data source
    is integrated so the frontend can show "Data unavailable" instead of
    fabricated metrics.
    """
    return None


def _build_ai_summary(
    posts: list[SinglePostInsights],
    ahs_band: str,
    content_pillars: list[ContentPillar],
    heatmap: list[HeatmapData] | None = None,
) -> AISummary:
    """Build AI summary stub from deterministic signals."""
    top_pillar = content_pillars[0].name if content_pillars else "General Content"
    reels = sum(1 for p in posts if (p.media_type or "").strip().upper() == "REEL")
    images = sum(1 for p in posts if (p.media_type or "").strip().upper() in ("IMAGE", "CAROUSEL"))
    top_content_type = "REEL" if reels >= images else "IMAGE"
    growth_map = {
        "EXCEPTIONAL": "Very High",
        "STRONG": "High",
        "AVERAGE": "Moderate",
        "NEEDS_WORK": "Needs improvement",
    }
    text_summary = (
        f"This account shows a {ahs_band.lower().replace('_', ' ')} overall health band. "
        f"Top content pillar is '{top_pillar}'. Best performing format is {top_content_type}. "
        f"Key growth levers include increasing posting consistency, optimizing hashtag strategy, "
        f"and improving engagement on underperforming content types."
    )
    best_posting_time = _compute_best_posting_time(heatmap) if heatmap else None
    return AISummary(
        text_summary=text_summary,
        top_content_type=top_content_type,
        best_posting_time=best_posting_time,
        top_content_pillar=top_pillar,
        growth_potential=growth_map.get(ahs_band, "Moderate"),
    )


def compute_account_health_score(
    posts: list[SinglePostInsights],
    account_avg_engagement_rate: float | None = None,
    niche_avg_engagement_rate: float | None = None,
    follower_band: str | None = None,
    follower_count: int | None = None,
) -> AccountHealthScore:
    """Compute deterministic Account Health Score (AHS) from recent posts.

    Uses up to the 30 most recent posts and composes five pillars:
    content quality, engagement quality, niche fit, consistency, and brand safety.
    """

    recent_posts = _sort_recent_posts(posts)
    post_count_used = len(recent_posts)
    min_history_threshold_met = post_count_used >= 10

    content_score, content_notes, content_has_signal, content_metrics = _build_content_quality(recent_posts)
    engagement_score, engagement_notes, engagement_has_signal, engagement_metrics = _build_engagement_quality(
        recent_posts,
        account_avg_engagement_rate,
    )
    niche_score, niche_notes, niche_has_signal, niche_metrics = _build_niche_fit(
        recent_posts,
        niche_avg_engagement_rate,
        follower_band,
        engagement_metrics.get("median_engagement_rate"),
    )
    consistency_score, consistency_notes, consistency_has_signal, consistency_metrics, time_window_days = _build_consistency(
        recent_posts
    )
    brand_safety_score, brand_safety_notes, brand_safety_has_signal, brand_safety_metrics = _build_brand_safety(
        recent_posts
    )

    pillars: dict[str, PillarScore] = {
        "content_quality": PillarScore(
            score=content_score,
            band=_score_to_band(content_score),
            notes=content_notes,
        ),
        "engagement_quality": PillarScore(
            score=engagement_score,
            band=_score_to_band(engagement_score),
            notes=engagement_notes,
        ),
        "niche_fit": PillarScore(
            score=niche_score,
            band=_score_to_band(niche_score),
            notes=niche_notes,
        ),
        "consistency": PillarScore(
            score=consistency_score,
            band=_score_to_band(consistency_score),
            notes=consistency_notes,
        ),
        "brand_safety": PillarScore(
            score=brand_safety_score,
            band=_score_to_band(brand_safety_score),
            notes=brand_safety_notes,
        ),
    }

    available_pillars: list[str] = []
    for key, has_signal in (
        ("content_quality", content_has_signal),
        ("engagement_quality", engagement_has_signal),
        ("niche_fit", niche_has_signal),
        ("consistency", consistency_has_signal),
        ("brand_safety", brand_safety_has_signal),
    ):
        if has_signal:
            available_pillars.append(key)

    if available_pillars:
        weight_sum = sum(PILLAR_WEIGHTS[key] for key in available_pillars)
        weighted_total = sum(
            pillars[key].score * (PILLAR_WEIGHTS[key] / weight_sum)
            for key in available_pillars
        )
    else:
        weighted_total = 50.0

    ahs_score = round(_clamp(weighted_total, 0.0, 100.0), 2)
    ahs_band = _score_to_band(ahs_score)

    drivers, recommendations = _build_drivers_and_recommendations(
        content_quality=content_score,
        engagement_quality=engagement_score,
        niche_fit=niche_score,
        consistency=consistency_score,
        brand_safety=brand_safety_score,
        min_history_threshold_met=min_history_threshold_met,
        content_metrics=content_metrics,
        engagement_metrics=engagement_metrics,
        niche_metrics=niche_metrics,
        consistency_metrics=consistency_metrics,
        brand_safety_metrics=brand_safety_metrics,
    )

    metadata = AccountHealthMetadata(
        post_count_used=post_count_used,
        min_history_threshold_met=min_history_threshold_met,
        time_window_days=time_window_days,
    )

                # --- Build new dashboard-facing fields ---
    _pillars = _extract_content_pillars(recent_posts)
    _heatmap = _generate_engagement_heatmap(recent_posts)

    return AccountHealthScore(
        ahs_score=ahs_score,
        ahs_band=ahs_band,
        pillars=pillars,
        drivers=drivers,
        recommendations=recommendations,
        metadata=metadata,
        # New dashboard fields
        growth_stage=_derive_growth_stage(ahs_band),
        brand_readiness=_calculate_brand_readiness(recent_posts, ahs_score),
        core_metrics=_build_core_metrics_dashboard(recent_posts, follower_count),
        growth_overview_chart=_build_growth_overview_chart(recent_posts, follower_count),
        content_type_performance=compute_content_type_performance(recent_posts),
        content_pillars=_pillars,
        engagement_heatmap=_heatmap,
        top_hashtags=_aggregate_hashtag_performance(recent_posts),
        top_posts=_extract_top_posts(recent_posts),
        audience_insights=_build_audience_insights(recent_posts),
        niche_benchmark=_build_niche_benchmark(recent_posts, niche_avg_engagement_rate),
        audience_demographics=_stub_audience_demographics(),
        conversion_funnel=_calculate_funnel_metrics(recent_posts),
        ai_summary=_build_ai_summary(recent_posts, ahs_band, _pillars, _heatmap),
    )


def _stub_audience_demographics() -> list[AudienceDemographics]:
    """Return an empty list when real demographic data is unavailable.

    Instagram Graph API does not expose audience country breakdown.
    Return an empty list so the frontend shows "Data unavailable"
    rather than fabricated percentages.
    """
    return []


def _derive_growth_stage(ahs_band: str) -> str:
    """Derive a human-readable growth stage label from the AHS band alone."""
    if ahs_band == "EXCEPTIONAL":
        return "Thriving"
    if ahs_band == "STRONG":
        return "Growing"
    if ahs_band == "AVERAGE":
        return "Developing"
    return "Needs Attention"


def _build_niche_benchmark(
    posts: list[SinglePostInsights],
    niche_avg_engagement_rate: float | None,
) -> NicheBenchmark:
    """Compute account-vs-niche benchmark ratios."""
    engagement_rates = [
        _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
        for post in posts
    ]
    engagement_rates = [er for er in engagement_rates if er is not None]
    median_er = median(engagement_rates) if engagement_rates else None
    er_vs_niche: float | None = None
    if median_er is not None and niche_avg_engagement_rate is not None and niche_avg_engagement_rate > 0:
        er_vs_niche = round(float(median_er) / niche_avg_engagement_rate, 2)
    return NicheBenchmark(
        engagement_rate_vs_niche=er_vs_niche,
        reach_vs_niche=None,
        growth_vs_niche=None,
    )


def _compute_best_posting_time(heatmap: list[HeatmapData]) -> str | None:
    """Extract top 2-3 posting time slots from the engagement heatmap."""
    if not heatmap:
        return None
    sorted_slots = sorted(heatmap, key=lambda h: h.intensity, reverse=True)[:3]
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    slots = [f"{day_names[h.day_of_week]} {h.hour_of_day}:00" for h in sorted_slots]
    return ", ".join(slots)


def _extract_top_posts(posts: list[SinglePostInsights], limit: int = 5) -> list[TopPostSummary]:
    """Return top N posts sorted by engagement rate."""
    scored: list[tuple[SinglePostInsights, float]] = []
    for post in posts:
        er = _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
        if er is not None:
            scored.append((post, er))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [
        TopPostSummary(
            media_id=p.media_id,
            caption_preview=(p.caption_text or "")[:100],
            media_type=p.media_type,
            published_at=(
                p.published_at.isoformat()
                if hasattr(p.published_at, "isoformat")
                else str(p.published_at) if p.published_at is not None else None
            ),
            engagement_rate=er,
            reach=_safe_float(getattr(p.core_metrics, "reach", None)),
        )
        for p, er in scored[:limit]
    ]


def compute_account_engagement_signals(
    posts: list[SinglePostInsights],
) -> AccountEngagementSignals:
    """Compute deterministic account-level engagement signals from processed posts."""

    def _round4(value: float | None) -> float | None:
        return round(value, 4) if isinstance(value, float) else None

    def _collect_metric(attribute: str) -> list[float]:
        values: list[float] = []
        for post in posts:
            numeric = _safe_float(getattr(post.derived_metrics, attribute, None))
            if numeric is not None:
                values.append(max(0.0, numeric))
        return values

    def _collect_hook_strengths() -> list[float]:
        values: list[float] = []
        for post in posts:
            signals = post.vision_analysis.signals if post.vision_analysis else []
            first_signal = signals[0] if signals else None
            numeric = _safe_float(getattr(first_signal, "hook_strength_score", None))
            if numeric is not None:
                values.append(_clamp(numeric, 0.0, 1.0))
        return values

    def _collect_shareability() -> list[float]:
        values: list[float] = []
        for post in posts:
            numeric = _safe_float(getattr(post.engagement_potential_score, "shareability", None))
            if numeric is not None:
                values.append(_clamp(numeric, 0.0, 10.0))
        return values

    def _normalized_weighted_score(components: list[tuple[float | None, float]]) -> float | None:
        available = [(value, weight) for value, weight in components if value is not None]
        if not available:
            return None
        total_weight = sum(weight for _, weight in available)
        if total_weight <= 0:
            return None
        score = sum(value * weight for value, weight in available) / total_weight
        return _clamp(score, 0.0, 100.0)

    try:
        save_rates = _collect_metric("save_rate")
        share_rates = _collect_metric("share_rate")
        watch_through_rates = _collect_metric("watch_through_rate")
        profile_visit_rates = _collect_metric("profile_visit_rate")
        comment_rates = _collect_metric("comment_rate")
        hook_strengths = _collect_hook_strengths()
        shareability_scores = _collect_shareability()
        engagement_rates = _collect_metric("engagement_rate")

        avg_save_rate = _mean_or_none(save_rates)
        avg_share_rate = _mean_or_none(share_rates)
        avg_watch_through_rate = _mean_or_none(watch_through_rates)
        avg_profile_visit_rate = _mean_or_none(profile_visit_rates)
        comment_rate_avg = _mean_or_none(comment_rates)
        avg_hook_strength = _mean_or_none(hook_strengths)
        avg_shareability = _mean_or_none(shareability_scores)

        audience_trust_index = _normalized_weighted_score(
            [
                (
                    _clamp((avg_save_rate / 0.15) * 100.0, 0.0, 100.0)
                    if avg_save_rate is not None
                    else None,
                    40.0,
                ),
                (
                    _clamp((avg_profile_visit_rate / 0.05) * 100.0, 0.0, 100.0)
                    if avg_profile_visit_rate is not None
                    else None,
                    35.0,
                ),
                (
                    _clamp((comment_rate_avg / 0.03) * 100.0, 0.0, 100.0)
                    if comment_rate_avg is not None
                    else None,
                    25.0,
                ),
            ]
        )

        virality_potential = _normalized_weighted_score(
            [
                (
                    _clamp((avg_share_rate / 0.10) * 100.0, 0.0, 100.0)
                    if avg_share_rate is not None
                    else None,
                    40.0,
                ),
                (
                    _clamp(avg_hook_strength * 100.0, 0.0, 100.0)
                    if avg_hook_strength is not None
                    else None,
                    35.0,
                ),
                (
                    _clamp((avg_shareability / 10.0) * 100.0, 0.0, 100.0)
                    if avg_shareability is not None
                    else None,
                    25.0,
                ),
            ]
        )

        consistency_score: float | None = None
        if len(engagement_rates) >= 2:
            engagement_rate_mean = _mean_or_none(engagement_rates)
            if engagement_rate_mean is not None and engagement_rate_mean > 0:
                cv = pstdev(engagement_rates) / engagement_rate_mean
                consistency_score = _clamp(100.0 - (cv * 100.0), 0.0, 100.0)

        return AccountEngagementSignals(
            avg_save_rate=_round4(avg_save_rate),
            avg_share_rate=_round4(avg_share_rate),
            avg_watch_through_rate=_round4(avg_watch_through_rate),
            avg_profile_visit_rate=_round4(avg_profile_visit_rate),
            audience_trust_index=_round4(audience_trust_index),
            virality_potential=_round4(virality_potential),
            consistency_score=_round4(consistency_score),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AccountHealth] Failed to compute engagement signals: %s", exc)
        return AccountEngagementSignals()


def compute_account_vision_summary(
    posts: list[SinglePostInsights],
) -> AccountVisionSummary:
    """Compute deterministic account-level vision summary signals from processed posts."""

    try:
        cringe_scores: list[float] = []
        hook_strengths: list[float] = []
        production_levels: list[str] = []
        flagged_posts_count = 0
        technical_flaw_counts: dict[str, int] = {}

        for post in posts:
            signals = post.vision_analysis.signals if post.vision_analysis else []
            first_signal = signals[0] if signals else None
            if first_signal is None:
                continue

            cringe_score = _safe_float(getattr(first_signal, "cringe_score", None))
            if cringe_score is not None:
                cringe_scores.append(_clamp(cringe_score, 0.0, 100.0))

            hook_strength = _safe_float(getattr(first_signal, "hook_strength_score", None))
            if hook_strength is not None:
                hook_strengths.append(_clamp(hook_strength, 0.0, 1.0))

            production_level = getattr(first_signal, "production_level", None)
            if isinstance(production_level, str) and production_level in {"low", "medium", "high"}:
                production_levels.append(production_level)

            is_cringe = getattr(first_signal, "is_cringe", None) is True
            adult_content_detected = getattr(first_signal, "adult_content_detected", None) is True
            if is_cringe or adult_content_detected:
                flagged_posts_count += 1

            technical_flaws = getattr(first_signal, "technical_flaws", [])
            if isinstance(technical_flaws, list):
                for flaw in technical_flaws:
                    if not isinstance(flaw, str):
                        continue
                    text = " ".join(flaw.strip().split())
                    if not text:
                        continue
                    truncated = text[:160]
                    technical_flaw_counts[truncated] = technical_flaw_counts.get(truncated, 0) + 1

        avg_cringe_score = round(mean(cringe_scores), 1) if cringe_scores else None
        avg_hook_strength = round(mean(hook_strengths), 3) if hook_strengths else None
        avg_production_level = (
            max(
                Counter(production_levels).items(),
                key=lambda item: (item[1], item[0]),
            )[0]
            if production_levels
            else None
        )
        common_technical_flaws = [
            flaw
            for flaw, _ in sorted(
                technical_flaw_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:5]
        ]

        return AccountVisionSummary(
            avg_cringe_score=avg_cringe_score,
            avg_hook_strength=avg_hook_strength,
            avg_production_level=avg_production_level,
            flagged_posts_count=flagged_posts_count,
            common_technical_flaws=common_technical_flaws,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AccountHealth] Failed to compute vision summary: %s", exc)
        return AccountVisionSummary()


def compute_content_quality_breakdown(
    posts: list[SinglePostInsights],
) -> dict[str, dict[str, float | None]]:
    """Average all S1/S2/S3/S5 sub-scores across posts for a radar-chart breakdown.

    Returns a dict with keys: visual_quality, caption, content_clarity, engagement_potential.
    Each key maps to a dict of sub-score-name -> averaged value (or None if no data).
    """

    def _avg(values: list[float]) -> float | None:
        return round(mean(values), 2) if values else None

    def _collect(posts: list[SinglePostInsights], attr: str, sub: str) -> list[float]:
        results: list[float] = []
        for post in posts:
            obj = getattr(post, attr, None)
            val = _safe_float(getattr(obj, sub, None)) if obj is not None else None
            if val is not None:
                results.append(val)
        return results

    try:
        # S1 — Visual Quality (each sub-score 0-10)
        visual_quality = {
            "composition": _avg(_collect(posts, "visual_quality_score", "composition")),
            "lighting": _avg(_collect(posts, "visual_quality_score", "lighting")),
            "subject_clarity": _avg(_collect(posts, "visual_quality_score", "subject_clarity")),
            "aesthetic_quality": _avg(_collect(posts, "visual_quality_score", "aesthetic_quality")),
        }

        # S2 — Caption Effectiveness (sub-scores 0-100)
        caption = {
            "hook_score": _avg(_collect(posts, "caption_effectiveness_score", "hook_score_0_100")),
            "hashtag_score": _avg(_collect(posts, "caption_effectiveness_score", "hashtag_score_0_100")),
            "cta_score": _avg(_collect(posts, "caption_effectiveness_score", "cta_score_0_100")),
            "length_score": _avg(_collect(posts, "caption_effectiveness_score", "length_score_0_100")),
        }

        # S3 — Content Clarity (each sub-score 0-10)
        content_clarity = {
            "message_singularity": _avg(_collect(posts, "content_clarity_score", "message_singularity")),
            "context_clarity": _avg(_collect(posts, "content_clarity_score", "context_clarity")),
            "caption_alignment": _avg(_collect(posts, "content_clarity_score", "caption_alignment")),
            "visual_message_support": _avg(_collect(posts, "content_clarity_score", "visual_message_support")),
            "cognitive_load": _avg(_collect(posts, "content_clarity_score", "cognitive_load")),
        }

        # S5 — Engagement Potential (each sub-score 0-10)
        engagement_potential = {
            "emotional_resonance": _avg(_collect(posts, "engagement_potential_score", "emotional_resonance")),
            "shareability": _avg(_collect(posts, "engagement_potential_score", "shareability")),
            "save_worthiness": _avg(_collect(posts, "engagement_potential_score", "save_worthiness")),
            "comment_potential": _avg(_collect(posts, "engagement_potential_score", "comment_potential")),
            "novelty_or_value": _avg(_collect(posts, "engagement_potential_score", "novelty_or_value")),
        }

        return {
            "visual_quality": visual_quality,
            "caption": caption,
            "content_clarity": content_clarity,
            "engagement_potential": engagement_potential,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AccountHealth] Failed to compute content quality breakdown: %s", exc)
        return {
            "visual_quality": {},
            "caption": {},
            "content_clarity": {},
            "engagement_potential": {},
        }


def compute_content_type_performance(posts: list[SinglePostInsights]) -> ContentTypePerformance:
    """Build deterministic per-content-type performance summary."""
    if not posts:
        return ContentTypePerformance(notes=["No posts available for content type analysis."])

    groups: dict[str, list[SinglePostInsights]] = {}
    for post in posts:
        raw_type = post.media_type if isinstance(post.media_type, str) else "UNKNOWN"
        content_type = raw_type.strip().upper() or "UNKNOWN"
        groups.setdefault(content_type, []).append(post)

    total_posts = len(posts)
    total_views_all_types = 0.0
    breakdown_rows: list[dict[str, Any]] = []

    for content_type, typed_posts in groups.items():
        views_values = [
            _safe_float(getattr(post.core_metrics, "reach", None))
            for post in typed_posts
        ]
        views_values = [value for value in views_values if value is not None]
        total_views = sum(views_values) if views_values else 0.0
        total_views_all_types += total_views

        engagement_rates = [
            _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
            for post in typed_posts
        ]
        engagement_rates = [value for value in engagement_rates if value is not None]

        likes = [_safe_float(getattr(post.core_metrics, "likes", None)) for post in typed_posts]
        comments = [_safe_float(getattr(post.core_metrics, "comments", None)) for post in typed_posts]
        saves = [_safe_float(getattr(post.core_metrics, "saves", None)) for post in typed_posts]
        shares = [_safe_float(getattr(post.core_metrics, "shares", None)) for post in typed_posts]
        weighted_scores = [_safe_float(getattr(post.weighted_post_score, "score", None)) for post in typed_posts]

        def _avg_clean(values: list[float | None]) -> float | None:
            filtered = [value for value in values if value is not None]
            return round(mean(filtered), 2) if filtered else None

        breakdown_rows.append(
            {
                "content_type": content_type,
                "post_count": len(typed_posts),
                "percentage_of_total": round((len(typed_posts) / total_posts) * 100.0, 2),
                "avg_views": round(mean(views_values), 2) if views_values else None,
                "total_views": int(round(total_views)) if views_values else None,
                "avg_engagement_rate": round(mean(engagement_rates), 4) if engagement_rates else None,
                "avg_likes": _avg_clean(likes),
                "avg_comments": _avg_clean(comments),
                "avg_saves": _avg_clean(saves),
                "avg_shares": _avg_clean(shares),
                "avg_weighted_score": _avg_clean(weighted_scores),
            }
        )

    for row in breakdown_rows:
        total_views = row.get("total_views")
        if isinstance(total_views, (int, float)) and total_views_all_types > 0:
            row["views_share_percent"] = round((float(total_views) / total_views_all_types) * 100.0, 2)
        else:
            row["views_share_percent"] = None

    breakdown_rows.sort(
        key=lambda row: (
            row["avg_views"] is None,
            -(row["avg_views"] or 0.0),
            row["content_type"],
        )
    )
    breakdown = [ContentTypeBreakdownEntry.model_validate(row) for row in breakdown_rows]

    by_views = max(
        breakdown,
        key=lambda row: (row.avg_views if row.avg_views is not None else -1.0),
        default=None,
    )
    by_engagement = max(
        breakdown,
        key=lambda row: (row.avg_engagement_rate if row.avg_engagement_rate is not None else -1.0),
        default=None,
    )
    best_for_views = by_views.content_type if by_views is not None else None
    best_for_engagement = by_engagement.content_type if by_engagement is not None else None

    insight: str | None = None
    if best_for_views and best_for_engagement:
        if best_for_views == best_for_engagement:
            insight = f"{best_for_views} leads both views and engagement."
        else:
            insight = f"{best_for_views} leads views, while {best_for_engagement} leads engagement."

    return ContentTypePerformance(
        breakdown=breakdown,
        best_for_views=best_for_views,
        best_for_engagement=best_for_engagement,
        insight=insight,
        notes=[],
    )
