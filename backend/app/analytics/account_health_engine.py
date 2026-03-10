"""Deterministic account-level aggregation and Account Health Score (AHS)."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, median, pstdev

from backend.app.domain.account_models import (
    AccountHealthMetadata,
    AccountHealthScore,
    DeterministicDriver,
    DeterministicRecommendation,
    PillarScore,
)
from backend.app.domain.post_models import SinglePostInsights


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


def _safe_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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

    ordered = sorted(posts, key=_sort_key, reverse=True)
    return ordered[:30]


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
            "median_save_rate": _mean_or_none(save_rates),
            "median_share_rate": _mean_or_none(share_rates),
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
        posts_per_week = len(posts) / (time_window_days / 7.0)
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


def compute_account_health_score(
    posts: list[SinglePostInsights],
    account_avg_engagement_rate: float | None = None,
    niche_avg_engagement_rate: float | None = None,
    follower_band: str | None = None,
    now_ts: datetime | None = None,
) -> AccountHealthScore:
    """Compute deterministic Account Health Score (AHS) from recent posts.

    Uses up to the 30 most recent posts and composes five pillars:
    content quality, engagement quality, niche fit, consistency, and brand safety.
    """

    del now_ts  # Reserved for future explicit time-window overrides.

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

    return AccountHealthScore(
        ahs_score=ahs_score,
        ahs_band=ahs_band,
        pillars=pillars,
        drivers=drivers,
        recommendations=recommendations,
        metadata=metadata,
    )
