"""Build the initial evidence-aware Creator Intelligence Report."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import median
from typing import Any, Sequence

from backend.app.domain.account_models import AccountHealthScore
from backend.app.domain.creator_intelligence_report_models import (
    CreatorIntelligenceMetric,
    CreatorIntelligenceReport,
    MetricEvidence,
    ReelDataAvailability,
    UnavailableReason,
)


_METRIC_DEFINITIONS = (
    ("overall_account_grade", "Overall Account Grade", "account"),
    ("growth_potential", "Growth Potential", "account"),
    ("virality_potential", "Virality Potential", "account"),
    ("follower_quality", "Follower Quality", "audience"),
    ("best_posting_time", "Best Posting Time", "content"),
    ("posting_frequency", "Posting Frequency", "content"),
    ("best_posts", "Best Performing Posts", "content"),
    ("worst_posts", "Worst Performing Posts", "content"),
    ("best_hooks", "Best Hooks", "content"),
    ("weak_hooks", "Hooks To Improve", "content"),
    ("caption_quality", "Caption Quality", "content"),
    ("visual_quality", "Visual Quality", "content"),
    ("editing_quality", "Editing Quality", "content"),
    ("thumbnail_quality", "Thumbnail Quality", "content"),
    ("retention", "Retention", "content"),
    ("hashtag_performance", "Hashtag Performance", "content"),
    ("cta_performance", "CTA Performance", "content"),
    ("content_pillars", "Content Pillars", "content"),
    ("content_fatigue", "Content Fatigue", "content"),
    ("audience_demographics", "Audience Demographics", "audience"),
    ("competitor_analysis", "Competitor Analysis", "competition"),
    ("brand_readiness", "Brand Readiness", "monetization"),
    ("estimated_earnings", "Estimated Earnings", "monetization"),
    ("thirty_day_plan", "30-Day Growth Plan", "action"),
    ("weekly_checklist", "Weekly Checklist", "action"),
    ("priority_improvements", "Priority Improvements", "action"),
)

_GUIDANCE: dict[UnavailableReason, str] = {
    "insufficient_post_history": "Analyze more posts with complete publishing and engagement data.",
    "insufficient_follower_history": "Reconnect after at least two follower snapshots collected seven days apart.",
    "missing_reel_insights": "Connect Reel insights that include retention and playback metrics.",
    "missing_audience_insights": "Connect Instagram audience insights for this account.",
    "missing_peer_cohort": "Analyze at least 30 comparable creators in the same niche and follower band.",
    "missing_account_metrics": "Refresh the account so the required Instagram insight metrics are available.",
    "not_yet_calculated": "This metric is not available in the current report version yet.",
}


def _available(
    metric_id: str,
    label: str,
    category: str,
    value: Any,
    *,
    unit: str | None = None,
    coverage: float = 1.0,
    evidence: list[str] | None = None,
    evidence_details: list[MetricEvidence] | None = None,
    methodology_version: str | None = None,
    source_data_at: datetime | None = None,
    status: str = "derived",
) -> CreatorIntelligenceMetric:
    return CreatorIntelligenceMetric(
        metric_id=metric_id,
        label=label,
        category=category,
        status=status,
        value=value,
        unit=unit,
        confidence=round(max(0.0, min(1.0, coverage)), 2),
        coverage=max(0.0, min(1.0, coverage)),
        evidence=evidence or [],
        evidence_details=evidence_details or [],
        methodology_version=methodology_version or f"{metric_id}-v1",
        source_data_at=source_data_at,
    )


def _unavailable(
    metric_id: str,
    label: str,
    category: str,
    reason: UnavailableReason,
) -> CreatorIntelligenceMetric:
    return CreatorIntelligenceMetric(
        metric_id=metric_id,
        label=label,
        category=category,
        status="unavailable",
        coverage=0.0,
        unavailable_reason=reason,
        availability_guidance=_GUIDANCE[reason],
        methodology_version=f"{metric_id}-v1",
    )


def _snapshot_values(snapshots: Sequence[Any]) -> list[tuple[datetime, int]]:
    values: list[tuple[datetime, int]] = []
    for snapshot in snapshots:
        observed_at = getattr(snapshot, "observed_at", None)
        follower_count = getattr(snapshot, "follower_count", None)
        if isinstance(observed_at, datetime) and isinstance(follower_count, int) and follower_count >= 0:
            values.append((observed_at, follower_count))
    return sorted(values, key=lambda value: value[0])


def _follower_projection(values: Sequence[tuple[datetime, int]]) -> dict[str, Any] | None:
    """Project followers only after a meaningful observed history exists."""
    if len(values) < 4:
        return None
    first_at, _ = values[0]
    last_at, current_followers = values[-1]
    elapsed_days = (last_at - first_at).total_seconds() / 86400.0
    if elapsed_days < 28:
        return None

    day_offsets = [(observed_at - first_at).total_seconds() / 86400.0 for observed_at, _ in values]
    mean_x = sum(day_offsets) / len(day_offsets)
    mean_y = sum(count for _, count in values) / len(values)
    denominator = sum((offset - mean_x) ** 2 for offset in day_offsets)
    if denominator <= 0:
        return None
    daily_change = sum(
        (offset - mean_x) * (count - mean_y)
        for offset, (_, count) in zip(day_offsets, values)
    ) / denominator
    return {
        "baseline_followers": values[0][1],
        "current_followers": current_followers,
        "observed_days": round(elapsed_days, 1),
        "snapshot_count": len(values),
        "average_daily_follower_change": round(daily_change, 2),
        "thirty_day_followers": max(0, round(current_followers + daily_change * 30)),
        "ninety_day_followers": max(0, round(current_followers + daily_change * 90)),
    }


def _percentile(value: float, population: Sequence[float]) -> float:
    if not population:
        return 0.0
    return round((sum(item <= value for item in population) / len(population)) * 100.0, 1)


def _peer_cohort_summary(
    peers: Sequence[Any],
    *,
    account_score: float,
) -> dict[str, Any] | None:
    """Summarize a pre-filtered real creator cohort; never infer competitors."""
    scored_peers = [
        peer for peer in peers
        if isinstance(getattr(peer, "ahs_score", None), (int, float))
        and isinstance(getattr(peer, "predicted_engagement_rate", None), (int, float))
    ]
    if len(scored_peers) < 30:
        return None
    scores = [float(peer.ahs_score) for peer in scored_peers]
    engagement_rates = [float(peer.predicted_engagement_rate) for peer in scored_peers]
    return {
        "cohort_size": len(scored_peers),
        "median_account_score": round(median(scores), 2),
        "account_score_percentile": _percentile(account_score, scores),
        "median_engagement_rate": round(median(engagement_rates), 4),
        "follower_band": "within_0.5x_to_2x",
    }


def _action_plan(recommendations: Sequence[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Turn deterministic recommendations into a transparent four-week plan."""
    actionable = [
        {
            "recommendation_id": str(getattr(recommendation, "id", "")),
            "text": str(getattr(recommendation, "text", "")).strip(),
            "impact_level": str(getattr(recommendation, "impact_level", "MEDIUM")),
        }
        for recommendation in recommendations
        if str(getattr(recommendation, "text", "")).strip()
    ][:6]
    if not actionable:
        return [], []
    weeks = [{"week": number, "focus": []} for number in range(1, 5)]
    for index, recommendation in enumerate(actionable):
        weeks[index % len(weeks)]["focus"].append(recommendation)
    return weeks, [
        {"recommendation_id": item["recommendation_id"], "text": item["text"], "completed": False}
        for item in actionable
    ]


def _reel_data_availability(posts: Sequence[Any]) -> ReelDataAvailability:
    reels = [post for post in posts if str(getattr(post, "media_type", "")).strip().upper() == "REEL"]
    visual_count = sum(
        1
        for post in reels
        if getattr(getattr(post, "reel_analysis", None), "total", None) is not None
    )
    watch_through_count = sum(
        1
        for post in reels
        if getattr(getattr(post, "derived_metrics", None), "watch_through_rate", None) is not None
    )
    editing_available = visual_count >= 3
    retention_available = watch_through_count >= 3
    guidance = None
    if not retention_available:
        guidance = "Connect Reel insights with watch-through or completion data for at least three Reels."
    elif not editing_available:
        guidance = "Analyze at least three Reel videos to unlock editing-quality insights."
    return ReelDataAvailability(
        reel_post_count=len(reels),
        reels_with_visual_analysis=visual_count,
        reels_with_observed_watch_through=watch_through_count,
        editing_quality_available=editing_available,
        retention_available=retention_available,
        guidance=guidance,
    )


def _observed_post_rankings(posts: Sequence[Any]) -> list[dict[str, Any]]:
    rankings: list[dict[str, Any]] = []
    for post in posts:
        metrics = getattr(post, "derived_metrics", None)
        engagement_rate = getattr(metrics, "engagement_rate", None)
        media_id = getattr(post, "media_id", None)
        if not isinstance(engagement_rate, (int, float)) or engagement_rate < 0 or not media_id:
            continue
        core_metrics = getattr(post, "core_metrics", None)
        published_at = getattr(post, "published_at", None)
        rankings.append(
            {
                "media_id": str(media_id),
                "media_type": getattr(post, "media_type", None),
                "published_at": published_at.isoformat() if isinstance(published_at, datetime) else None,
                "engagement_rate": round(float(engagement_rate), 4),
                "reach": getattr(core_metrics, "reach", None),
                "saves": getattr(core_metrics, "saves", None),
                "shares": getattr(core_metrics, "shares", None),
            }
        )
    return sorted(
        rankings,
        key=lambda post: (post["engagement_rate"], post["reach"] or 0),
        reverse=True,
    )


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _caption_rollup(posts: Sequence[Any]) -> tuple[dict[str, float] | None, int]:
    caption_scores = [
        getattr(post, "caption_effectiveness_score", None)
        for post in posts
        if isinstance(getattr(post, "caption_text", None), str) and getattr(post, "caption_text", "").strip()
    ]
    if len(caption_scores) < 3:
        return None, len(caption_scores)
    raw_scores = [float(score.s2_raw_0_100) for score in caption_scores]
    cta_scores = [float(score.cta_score_0_100) for score in caption_scores]
    return {
        "score": _mean(raw_scores) or 0.0,
        "cta_score": _mean(cta_scores) or 0.0,
        "caption_count": len(caption_scores),
    }, len(caption_scores)


def _visual_rollup(posts: Sequence[Any]) -> tuple[dict[str, float] | None, int]:
    visual_scores = [
        getattr(post, "visual_quality_score", None)
        for post in posts
        if getattr(getattr(post, "vision_analysis", None), "status", None) == "ok"
        and isinstance(getattr(getattr(post, "visual_quality_score", None), "total", None), (int, float))
        and getattr(getattr(post, "visual_quality_score", None), "total", 0) > 0
    ]
    if len(visual_scores) < 3:
        return None, len(visual_scores)
    return {
        "score": round((_mean([float(score.total) for score in visual_scores]) or 0.0) * 2.0, 2),
        "composition": _mean([float(score.composition) for score in visual_scores]) or 0.0,
        "lighting": _mean([float(score.lighting) for score in visual_scores]) or 0.0,
        "subject_clarity": _mean([float(score.subject_clarity) for score in visual_scores]) or 0.0,
        "aesthetic_quality": _mean([float(score.aesthetic_quality) for score in visual_scores]) or 0.0,
        "post_count": len(visual_scores),
    }, len(visual_scores)


def _hook_rankings(posts: Sequence[Any]) -> list[dict[str, Any]]:
    hooks: list[dict[str, Any]] = []
    for post in posts:
        hook_score = getattr(getattr(post, "reel_analysis", None), "hook_score", None)
        engagement_rate = getattr(getattr(post, "derived_metrics", None), "engagement_rate", None)
        media_id = getattr(post, "media_id", None)
        if not isinstance(hook_score, (int, float)) or not isinstance(engagement_rate, (int, float)) or not media_id:
            continue
        caption = getattr(post, "caption_text", "")
        hook_text = caption.split(".", 1)[0].strip()[:160] if isinstance(caption, str) and caption.strip() else None
        hooks.append(
            {
                "media_id": str(media_id),
                "hook_score": round(float(hook_score) * 2.0, 2),
                "engagement_rate": round(float(engagement_rate), 4),
                "hook_text": hook_text,
            }
        )
    return sorted(hooks, key=lambda hook: (hook["hook_score"], hook["engagement_rate"]), reverse=True)


def _content_pillar_rollup(posts: Sequence[Any]) -> list[dict[str, Any]]:
    groups: dict[str, list[Any]] = defaultdict(list)
    for post in posts:
        category = getattr(post, "post_category", None)
        engagement_rate = getattr(getattr(post, "derived_metrics", None), "engagement_rate", None)
        if not isinstance(category, str) or not category.strip() or category.strip().lower() == "unknown":
            continue
        if not isinstance(engagement_rate, (int, float)) or engagement_rate < 0:
            continue
        groups[category.strip().lower()].append(post)

    pillars: list[dict[str, Any]] = []
    for category, category_posts in groups.items():
        if len(category_posts) < 3:
            continue
        engagement_rates = [float(post.derived_metrics.engagement_rate) for post in category_posts]
        reach_values = [
            float(post.core_metrics.reach)
            for post in category_posts
            if isinstance(getattr(post.core_metrics, "reach", None), (int, float))
        ]
        save_rates = [
            float(post.derived_metrics.save_rate)
            for post in category_posts
            if isinstance(getattr(post.derived_metrics, "save_rate", None), (int, float))
        ]
        share_rates = [
            float(post.derived_metrics.share_rate)
            for post in category_posts
            if isinstance(getattr(post.derived_metrics, "share_rate", None), (int, float))
        ]
        pillars.append(
            {
                "name": category,
                "post_count": len(category_posts),
                "average_engagement_rate": _mean(engagement_rates),
                "average_reach": _mean(reach_values),
                "average_save_rate": _mean(save_rates),
                "average_share_rate": _mean(share_rates),
            }
        )
    return sorted(pillars, key=lambda pillar: pillar["average_engagement_rate"] or 0.0, reverse=True)


def _content_fatigue(posts: Sequence[Any]) -> tuple[dict[str, Any] | None, int]:
    groups: dict[tuple[str, str], list[tuple[datetime, float]]] = defaultdict(list)
    for post in posts:
        category = getattr(post, "post_category", None)
        media_type = getattr(post, "media_type", None)
        published_at = getattr(post, "published_at", None)
        engagement_rate = getattr(getattr(post, "derived_metrics", None), "engagement_rate", None)
        if not isinstance(category, str) or not category.strip() or category.strip().lower() == "unknown":
            continue
        if not isinstance(media_type, str) or not media_type.strip():
            continue
        if not isinstance(published_at, datetime) or not isinstance(engagement_rate, (int, float)) or engagement_rate < 0:
            continue
        groups[(category.strip().lower(), media_type.strip().upper())].append((published_at, float(engagement_rate)))

    eligible_groups = 0
    strongest_signal: dict[str, Any] | None = None
    for (category, media_type), values in groups.items():
        ordered = sorted(values, key=lambda value: value[0])
        latest_at = ordered[-1][0]
        window_values = [value for value in ordered if (latest_at - value[0]).total_seconds() <= 28 * 86400]
        if len(window_values) < 6:
            continue
        eligible_groups += 1
        midpoint = len(window_values) // 2
        early_median = median(value[1] for value in window_values[:midpoint])
        recent_median = median(value[1] for value in window_values[midpoint:])
        decline_pct = ((early_median - recent_median) / early_median) * 100.0 if early_median > 0 else 0.0
        candidate = {
            "fatigue_detected": decline_pct >= 20.0,
            "content_pillar": category,
            "media_type": media_type,
            "post_count": len(window_values),
            "early_median_engagement_rate": round(early_median, 4),
            "recent_median_engagement_rate": round(recent_median, 4),
            "engagement_decline_pct": round(max(0.0, decline_pct), 2),
        }
        if strongest_signal is None or candidate["engagement_decline_pct"] > strongest_signal["engagement_decline_pct"]:
            strongest_signal = candidate
    return strongest_signal, eligible_groups


def build_creator_intelligence_report(
    account_health: AccountHealthScore,
    *,
    follower_snapshots: Sequence[Any] = (),
    posts: Sequence[Any] = (),
    peer_cohort: Sequence[Any] = (),
) -> CreatorIntelligenceReport:
    """Create a report without substituting predictions for unavailable inputs."""
    definitions = {metric_id: (label, category) for metric_id, label, category in _METRIC_DEFINITIONS}
    post_count = account_health.metadata.post_count_used
    post_coverage = min(1.0, post_count / 30.0)
    snapshot_values = _snapshot_values(follower_snapshots)
    reel_data_availability = _reel_data_availability(posts)
    observed_post_rankings = _observed_post_rankings(posts)
    caption_rollup, caption_count = _caption_rollup(posts)
    visual_rollup, visual_count = _visual_rollup(posts)
    hook_rankings = _hook_rankings(posts)
    pillar_rollup = _content_pillar_rollup(posts)
    fatigue_signal, fatigue_group_count = _content_fatigue(posts)
    metrics: dict[str, CreatorIntelligenceMetric] = {}

    def available(metric_id: str, value: Any, **kwargs: Any) -> None:
        label, category = definitions[metric_id]
        metrics[metric_id] = _available(metric_id, label, category, value, **kwargs)

    def unavailable(metric_id: str, reason: UnavailableReason) -> None:
        label, category = definitions[metric_id]
        metrics[metric_id] = _unavailable(metric_id, label, category, reason)

    available(
        "overall_account_grade",
        {"score": account_health.ahs_score, "band": account_health.ahs_band},
        unit="score_0_100",
        coverage=post_coverage,
        evidence=[f"{post_count} analyzed posts", "deterministic account health score"],
        evidence_details=[
            MetricEvidence(source="account_analysis", fields=["ahs_score", "pillar_scores"])
        ],
    )

    virality = getattr(account_health.engagement_signals, "virality_potential", None)
    if virality is None:
        unavailable("virality_potential", "missing_account_metrics")
    else:
        available(
            "virality_potential",
            virality,
            unit="score_0_100",
            coverage=post_coverage,
            evidence=["observed engagement signals"],
            evidence_details=[
                MetricEvidence(source="account_analysis", fields=["save_rate", "share_rate", "watch_through_rate"])
            ],
        )

    if len(snapshot_values) >= 2:
        earliest_at, earliest_count = snapshot_values[0]
        latest_at, latest_count = snapshot_values[-1]
        elapsed_days = (latest_at - earliest_at).total_seconds() / 86400.0
        if elapsed_days >= 7 and earliest_count > 0:
            growth_pct = round(((latest_count - earliest_count) / earliest_count) * 100.0, 2)
            projection = _follower_projection(snapshot_values)
            available(
                "growth_potential",
                {
                    "baseline_followers": earliest_count,
                    "current_followers": latest_count,
                    "follower_change": latest_count - earliest_count,
                    "observed_growth_pct": growth_pct,
                    "days_observed": round(elapsed_days, 1),
                    "snapshot_count": len(snapshot_values),
                    **({"projection": projection} if projection is not None else {}),
                },
                unit="observed_percent_change",
                coverage=min(1.0, len(snapshot_values) / 4.0),
                evidence=["observed follower snapshots at least seven days apart"],
                evidence_details=[
                    MetricEvidence(
                        source="follower_snapshots",
                        fields=["follower_count"],
                        observed_at=latest_at,
                        reference=f"{len(snapshot_values)} snapshots over {round(elapsed_days, 1)} days",
                    )
                ],
                source_data_at=latest_at,
                status="predicted" if projection is not None else "derived",
            )
        else:
            unavailable("growth_potential", "insufficient_follower_history")
    else:
        unavailable("growth_potential", "insufficient_follower_history")

    if account_health.engagement_heatmap:
        available(
            "best_posting_time",
            [slot.model_dump(mode="json") for slot in account_health.engagement_heatmap],
            coverage=post_coverage,
            evidence=["at least 3 posts with observed engagement per recommended slot"],
        )
    else:
        unavailable("best_posting_time", "insufficient_post_history")

    if post_count and account_health.metadata.time_window_days:
        available(
            "posting_frequency",
            round(post_count / (account_health.metadata.time_window_days / 7), 2),
            unit="posts_per_week",
            coverage=post_coverage,
            evidence=[f"{post_count} posts over {account_health.metadata.time_window_days} days"],
        )
    else:
        unavailable("posting_frequency", "insufficient_post_history")

    if len(observed_post_rankings) >= 3:
        available(
            "best_posts",
            observed_post_rankings[:5],
            coverage=post_coverage,
            evidence=["ranked by observed engagement rate and reach"],
            evidence_details=[
                MetricEvidence(source="instagram_post_insights", fields=["engagement_rate", "reach", "saves", "shares"])
            ],
        )
        available(
            "worst_posts",
            list(reversed(observed_post_rankings[-5:])),
            coverage=post_coverage,
            evidence=["ranked by observed engagement rate and reach"],
            evidence_details=[
                MetricEvidence(source="instagram_post_insights", fields=["engagement_rate", "reach", "saves", "shares"])
            ],
        )
    else:
        unavailable("best_posts", "insufficient_post_history")

    reel_totals = [
        float(getattr(getattr(post, "reel_analysis", None), "total"))
        for post in posts
        if isinstance(getattr(getattr(post, "reel_analysis", None), "total", None), (int, float))
    ]
    if reel_data_availability.editing_quality_available:
        available(
            "editing_quality",
            {"score": round((_mean(reel_totals) or 0.0), 2), "reel_count": len(reel_totals)},
            unit="score_0_100",
            coverage=min(1.0, len(reel_totals) / max(1, reel_data_availability.reel_post_count)),
            evidence=["Reel visual and audio analysis"],
            evidence_details=[
                MetricEvidence(source="reel_analysis", fields=["hook_score", "pacing_score", "audio_alignment_score"])
            ],
        )

    watch_through_rates = [
        float(getattr(getattr(post, "derived_metrics", None), "watch_through_rate"))
        for post in posts
        if isinstance(getattr(getattr(post, "derived_metrics", None), "watch_through_rate", None), (int, float))
    ]
    if reel_data_availability.retention_available:
        available(
            "retention",
            {
                "average_watch_through_rate": _mean(watch_through_rates),
                "reel_count": len(watch_through_rates),
            },
            unit="ratio_0_1",
            coverage=min(1.0, len(watch_through_rates) / max(1, reel_data_availability.reel_post_count)),
            evidence=["observed Reel watch-through rates"],
            evidence_details=[
                MetricEvidence(source="instagram_reel_insights", fields=["watch_through_rate"])
            ],
        )

    if caption_rollup is not None:
        available(
            "caption_quality",
            caption_rollup,
            unit="score_0_100",
            coverage=min(1.0, caption_count / max(1, post_count)),
            evidence=["deterministic caption analysis"],
            evidence_details=[
                MetricEvidence(source="caption_analysis", fields=["s2_raw_0_100", "cta_score_0_100"])
            ],
        )
        available(
            "cta_performance",
            {"score": caption_rollup["cta_score"], "caption_count": caption_count},
            unit="score_0_100",
            coverage=min(1.0, caption_count / max(1, post_count)),
            evidence=["deterministic caption CTA analysis"],
            evidence_details=[MetricEvidence(source="caption_analysis", fields=["cta_score_0_100"])],
        )

    if visual_rollup is not None:
        available(
            "visual_quality",
            visual_rollup,
            unit="score_0_100",
            coverage=min(1.0, visual_count / max(1, post_count)),
            evidence=["successful visual analysis"],
            evidence_details=[
                MetricEvidence(
                    source="vision_analysis",
                    fields=["composition", "lighting", "subject_clarity", "aesthetic_quality"],
                )
            ],
        )

    if len(hook_rankings) >= 3:
        available(
            "best_hooks",
            hook_rankings[:5],
            unit="score_0_100",
            coverage=min(1.0, len(hook_rankings) / max(1, reel_data_availability.reel_post_count)),
            evidence=["Reel hook scores and observed engagement rates"],
            evidence_details=[MetricEvidence(source="reel_analysis", fields=["hook_score", "engagement_rate"])],
        )
        available(
            "weak_hooks",
            list(reversed(hook_rankings[-5:])),
            unit="score_0_100",
            coverage=min(1.0, len(hook_rankings) / max(1, reel_data_availability.reel_post_count)),
            evidence=["Reel hook scores and observed engagement rates"],
            evidence_details=[MetricEvidence(source="reel_analysis", fields=["hook_score", "engagement_rate"])],
        )

    if account_health.top_hashtags:
        available(
            "hashtag_performance",
            [hashtag.model_dump(mode="json") for hashtag in account_health.top_hashtags],
            coverage=post_coverage,
            evidence=["caption or platform hashtag data"],
        )
    else:
        unavailable("hashtag_performance", "missing_account_metrics")

    if pillar_rollup:
        available(
            "content_pillars",
            pillar_rollup,
            coverage=post_coverage,
            evidence=["post categories with observed performance"],
            evidence_details=[
                MetricEvidence(source="instagram_post_insights", fields=["post_category", "engagement_rate", "reach"])
            ],
        )
    elif account_health.content_pillars:
        available(
            "content_pillars",
            [pillar.model_dump(mode="json") for pillar in account_health.content_pillars],
            coverage=post_coverage,
            evidence=["post categories and hashtags"],
        )
    else:
        unavailable("content_pillars", "insufficient_post_history")

    if fatigue_signal is not None:
        available(
            "content_fatigue",
            fatigue_signal,
            coverage=min(1.0, fatigue_group_count / 3.0),
            evidence=["repeated category and format performance over a 28-day window"],
            evidence_details=[
                MetricEvidence(source="instagram_post_insights", fields=["post_category", "media_type", "published_at", "engagement_rate"])
            ],
        )

    if account_health.brand_readiness is not None:
        available(
            "brand_readiness",
            account_health.brand_readiness.model_dump(mode="json"),
            unit="score_0_100",
            coverage=post_coverage,
            evidence=["brand safety and account health pillars"],
        )
    else:
        unavailable("brand_readiness", "missing_account_metrics")

    peer_summary = _peer_cohort_summary(peer_cohort, account_score=account_health.ahs_score)
    if peer_summary is not None:
        available(
            "competitor_analysis",
            peer_summary,
            unit="cohort_benchmark",
            coverage=1.0,
            evidence=["real creators in the same category and a 0.5x-2x follower band"],
            evidence_details=[
                MetricEvidence(source="creator_discovery_meta", fields=["ahs_score", "predicted_engagement_rate", "follower_count"])
            ],
            methodology_version="peer-cohort-v1",
        )

    if account_health.recommendations:
        plan, checklist = _action_plan(account_health.recommendations)
        available(
            "priority_improvements",
            [recommendation.model_dump(mode="json") for recommendation in account_health.recommendations],
            coverage=post_coverage,
            evidence=["deterministic account health recommendations"],
        )
        available(
            "thirty_day_plan",
            plan,
            unit="four_week_plan",
            coverage=1.0,
            evidence=["sequenced from deterministic account health recommendations"],
            methodology_version="action-plan-v1",
        )
        available(
            "weekly_checklist",
            checklist,
            unit="checklist_items",
            coverage=1.0,
            evidence=["actionable tasks generated from deterministic recommendations"],
            methodology_version="action-checklist-v1",
        )
    else:
        unavailable("priority_improvements", "insufficient_post_history")

    for metric_id, label, category in _METRIC_DEFINITIONS:
        if metric_id in metrics:
            continue
        reason: UnavailableReason = "not_yet_calculated"
        if metric_id == "growth_potential":
            reason = "insufficient_follower_history"
        elif metric_id in {"editing_quality", "thumbnail_quality", "retention"}:
            reason = "missing_reel_insights"
        elif metric_id in {"follower_quality", "audience_demographics"}:
            reason = "missing_audience_insights"
        elif metric_id == "competitor_analysis":
            reason = "missing_peer_cohort"
        elif metric_id in {"worst_posts", "best_hooks", "weak_hooks", "caption_quality", "visual_quality", "cta_performance", "content_fatigue"}:
            reason = "not_yet_calculated" if post_count else "insufficient_post_history"
        unavailable(metric_id, reason)

    ordered_metrics = [metrics[metric_id] for metric_id, _, _ in _METRIC_DEFINITIONS]
    report_status = "complete" if all(metric.status != "unavailable" for metric in ordered_metrics) else "partial"
    return CreatorIntelligenceReport(
        report_status=report_status,
        metrics=ordered_metrics,
        reel_data_availability=reel_data_availability,
    )
