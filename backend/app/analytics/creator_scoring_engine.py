from __future__ import annotations

from statistics import mean
from typing import Any, Literal

from backend.app.domain.account_models import (
    CreatorEngagementMetrics,
    CreatorGrowthMetrics,
    CreatorReachMetrics,
    CreatorRetentionMetrics,
    CreatorScore,
    FakeFollowerSignals,
)
from backend.app.domain.post_models import SinglePostInsights


def _safe_float(value: object) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_numeric(account_data: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = account_data.get(key)
        if value is None:
            continue
        numeric = _safe_float(value)
        if numeric > 0:
            return numeric
    return 0.0


def _pick_post_or_account_numeric(post: SinglePostInsights, account_data: dict[str, Any], *keys: str) -> float:
    for key in keys:
        candidate = getattr(post, key, None)
        if candidate is None:
            core = getattr(post, "core_metrics", None)
            candidate = getattr(core, key, None) if core is not None else None
        if candidate is None:
            reel = getattr(post, "reel_analysis", None)
            candidate = getattr(reel, key, None) if reel is not None else None
        if candidate is None:
            candidate = account_data.get(key)
        numeric = _safe_float(candidate)
        if numeric > 0:
            return numeric
    return 0.0


def _rate_percent(numerator: float, denominator: float) -> tuple[float, bool]:
    if denominator <= 0:
        return 0.0, False
    return (numerator / denominator) * 100.0, True


def _avg(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _classify_engagement(rate: float, valid: bool, good_min: float, bad_max_exclusive: float) -> Literal["Good", "Bad", "Neutral"]:
    if not valid:
        return "Neutral"
    if rate < bad_max_exclusive:
        return "Bad"
    if rate >= good_min:
        return "Good"
    return "Neutral"


def _classify_health(rate: float, valid: bool, healthy_min: float, weak_max_exclusive: float) -> Literal["Healthy", "Weak", "Neutral"]:
    if not valid:
        return "Neutral"
    if rate < weak_max_exclusive:
        return "Weak"
    if rate >= healthy_min:
        return "Healthy"
    return "Neutral"


def _classify_good_weak(rate: float, valid: bool, good_min: float, weak_max_exclusive: float) -> Literal["Good", "Weak", "Neutral"]:
    if not valid:
        return "Neutral"
    if rate < weak_max_exclusive:
        return "Weak"
    if rate >= good_min:
        return "Good"
    return "Neutral"


def _classify_story_reach(rate: float, valid: bool) -> Literal["Healthy", "Weak", "Neutral"]:
    if not valid:
        return "Neutral"
    if rate < 5.0:
        return "Weak"
    if 5.0 <= rate <= 20.0:
        return "Healthy"
    return "Neutral"


def _score_three_band(flags: list[str], good_label: str, weak_label: str) -> float:
    if flags and all(flag == good_label for flag in flags):
        return 100.0
    if flags and all(flag == weak_label for flag in flags):
        return 0.0
    return 50.0


def _interpret(score: float) -> Literal[
    "Elite Creator",
    "Strong Creator",
    "Average Creator",
    "Weak Audience",
    "High Risk / Fake Signals",
]:
    if score >= 90.0:
        return "Elite Creator"
    if score >= 75.0:
        return "Strong Creator"
    if score >= 60.0:
        return "Average Creator"
    if score >= 40.0:
        return "Weak Audience"
    return "High Risk / Fake Signals"


def generate_creator_score(posts: list[SinglePostInsights], account_data: dict[str, Any]) -> CreatorScore:
    followers_from_account = _extract_numeric(account_data, "followers", "follower_count", "followers_count")

    engagement_rates: list[float] = []
    save_rates: list[float] = []
    share_rates: list[float] = []
    comment_rates: list[float] = []

    reach_efficiency_rates: list[float] = []
    reel_reach_rates: list[float] = []
    story_reach_rates: list[float] = []
    non_follower_reach_rates: list[float] = []

    completion_rates: list[float] = []
    replay_rates: list[float] = []
    hook_efficiency_rates: list[float] = []
    watch_time_ratio_rates: list[float] = []

    valid_engagement = False
    valid_save = False
    valid_share = False
    valid_comment = False
    valid_reach_eff = False
    valid_reel_reach = False
    valid_story_reach = False
    valid_non_follower = False
    valid_completion = False
    valid_replay = False
    valid_hook = False
    valid_watch_time = False

    avg_reach_values: list[float] = []

    for post in posts:
        core = post.core_metrics
        followers = followers_from_account if followers_from_account > 0 else _safe_float(post.follower_count)

        likes = _safe_float(getattr(core, "likes", None))
        comments = _safe_float(getattr(core, "comments", None))
        shares = _safe_float(getattr(core, "shares", None))
        saves = _safe_float(getattr(core, "saves", None))
        reach = _safe_float(getattr(core, "reach", None))

        if reach > 0:
            avg_reach_values.append(reach)

        er, er_ok = _rate_percent(likes + comments + shares + saves, followers)
        engagement_rates.append(er)
        valid_engagement = valid_engagement or er_ok

        save_rate, save_ok = _rate_percent(saves, reach)
        save_rates.append(save_rate)
        valid_save = valid_save or save_ok

        share_rate, share_ok = _rate_percent(shares, reach)
        share_rates.append(share_rate)
        valid_share = valid_share or share_ok

        comment_rate, comment_ok = _rate_percent(comments, followers)
        comment_rates.append(comment_rate)
        valid_comment = valid_comment or comment_ok

        reach_eff, reach_eff_ok = _rate_percent(reach, followers)
        reach_efficiency_rates.append(reach_eff)
        valid_reach_eff = valid_reach_eff or reach_eff_ok

        media_type = (post.media_type or "").strip().upper()
        if media_type in {"REEL", "VIDEO"}:
            reel_reach_rates.append(reach_eff)
            valid_reel_reach = valid_reel_reach or reach_eff_ok
        if media_type == "STORY":
            story_reach_rates.append(reach_eff)
            valid_story_reach = valid_story_reach or reach_eff_ok

        non_follower_reach = _pick_post_or_account_numeric(
            post, account_data, "non_follower_reach", "reach_non_followers"
        )
        non_follow_rate, non_follow_ok = _rate_percent(non_follower_reach, reach)
        non_follower_reach_rates.append(non_follow_rate)
        valid_non_follower = valid_non_follower or non_follow_ok

        completed_views = _pick_post_or_account_numeric(post, account_data, "completed_views")
        total_plays = _pick_post_or_account_numeric(post, account_data, "total_plays", "plays")
        replays = _pick_post_or_account_numeric(post, account_data, "replays")
        three_sec_views = _pick_post_or_account_numeric(post, account_data, "three_sec_views")
        total_views = _pick_post_or_account_numeric(post, account_data, "total_views", "views", "reach")
        avg_watch_time = _pick_post_or_account_numeric(post, account_data, "avg_watch_time", "average_watch_time")
        reel_duration = _pick_post_or_account_numeric(post, account_data, "reel_duration", "duration")

        completion_rate, completion_ok = _rate_percent(completed_views, total_plays)
        completion_rates.append(completion_rate)
        valid_completion = valid_completion or completion_ok

        replay_rate, replay_ok = _rate_percent(replays, total_plays)
        replay_rates.append(replay_rate)
        valid_replay = valid_replay or replay_ok

        hook_rate, hook_ok = _rate_percent(three_sec_views, total_views)
        hook_efficiency_rates.append(hook_rate)
        valid_hook = valid_hook or hook_ok

        watch_time_rate, watch_ok = _rate_percent(avg_watch_time, reel_duration)
        watch_time_ratio_rates.append(watch_time_rate)
        valid_watch_time = valid_watch_time or watch_ok

    engagement_rate_avg = _avg(engagement_rates)
    save_rate_avg = _avg(save_rates)
    share_rate_avg = _avg(share_rates)
    comment_rate_avg = _avg(comment_rates)

    reach_eff_avg = _avg(reach_efficiency_rates)
    reel_reach_avg = _avg(reel_reach_rates)
    story_reach_avg = _avg(story_reach_rates)
    non_follower_reach_avg = _avg(non_follower_reach_rates)

    completion_rate_avg = _avg(completion_rates)
    replay_rate_avg = _avg(replay_rates)
    hook_efficiency_avg = _avg(hook_efficiency_rates)
    watch_time_ratio_avg = _avg(watch_time_ratio_rates)

    engagement_metrics = CreatorEngagementMetrics(
        engagement_rate_flag=_classify_engagement(engagement_rate_avg, valid_engagement, good_min=2.0, bad_max_exclusive=1.0),
        save_rate_flag=_classify_engagement(save_rate_avg, valid_save, good_min=2.0, bad_max_exclusive=1.0),
        share_rate_flag=_classify_engagement(share_rate_avg, valid_share, good_min=2.0, bad_max_exclusive=1.0),
        comment_rate_flag=_classify_engagement(comment_rate_avg, valid_comment, good_min=0.5, bad_max_exclusive=0.1),
    )

    reach_metrics = CreatorReachMetrics(
        reach_efficiency_flag=_classify_health(reach_eff_avg, valid_reach_eff, healthy_min=20.0, weak_max_exclusive=10.0),
        reel_reach_flag=_classify_health(reel_reach_avg, valid_reel_reach, healthy_min=40.0, weak_max_exclusive=10.0),
        story_reach_flag=_classify_story_reach(story_reach_avg, valid_story_reach),
        non_follower_reach_flag=_classify_health(non_follower_reach_avg, valid_non_follower, healthy_min=40.0, weak_max_exclusive=15.0),
    )

    retention_metrics = CreatorRetentionMetrics(
        completion_rate_flag=_classify_good_weak(completion_rate_avg, valid_completion, good_min=50.0, weak_max_exclusive=30.0),
        replay_rate_flag=_classify_good_weak(replay_rate_avg, valid_replay, good_min=5.0, weak_max_exclusive=1.0),
        hook_efficiency_flag=_classify_good_weak(hook_efficiency_avg, valid_hook, good_min=70.0, weak_max_exclusive=40.0),
        watch_time_ratio_flag=_classify_good_weak(watch_time_ratio_avg, valid_watch_time, good_min=60.0, weak_max_exclusive=30.0),
    )

    growth_metrics = CreatorGrowthMetrics(
        follower_growth_flag="Neutral",
        net_growth_flag="Neutral",
        growth_velocity_flag="Neutral",
        unfollow_rate_flag="Neutral",
    )

    avg_reach = _avg(avg_reach_values)
    fake_follower_signals = FakeFollowerSignals(
        poor_audience_quality=(followers_from_account >= 1_000_000 and avg_reach <= 8_000),
        weak_audience_interest=(save_rate_avg < 1.0 and share_rate_avg < 1.0),
        bot_activity=False,
        possible_bought_followers=False,
        inactive_followers=False,
        dead_audience=(followers_from_account > 50_000 and engagement_rate_avg < 1.0),
    )

    engagement_sub_score = _score_three_band(
        [
            engagement_metrics.engagement_rate_flag,
            engagement_metrics.save_rate_flag,
            engagement_metrics.share_rate_flag,
            engagement_metrics.comment_rate_flag,
        ],
        good_label="Good",
        weak_label="Bad",
    )
    reach_sub_score = _score_three_band(
        [
            reach_metrics.reach_efficiency_flag,
            reach_metrics.reel_reach_flag,
            reach_metrics.story_reach_flag,
            reach_metrics.non_follower_reach_flag,
        ],
        good_label="Healthy",
        weak_label="Weak",
    )
    retention_sub_score = _score_three_band(
        [
            retention_metrics.completion_rate_flag,
            retention_metrics.replay_rate_flag,
            retention_metrics.hook_efficiency_flag,
            retention_metrics.watch_time_ratio_flag,
        ],
        good_label="Good",
        weak_label="Weak",
    )

    true_fake_signals = sum(
        int(flag)
        for flag in (
            fake_follower_signals.poor_audience_quality,
            fake_follower_signals.weak_audience_interest,
            fake_follower_signals.bot_activity,
            fake_follower_signals.possible_bought_followers,
            fake_follower_signals.inactive_followers,
            fake_follower_signals.dead_audience,
        )
    )
    authenticity_sub_score = max(0.0, 100.0 - (25.0 * true_fake_signals))
    growth_sub_score = 50.0
    brand_fit_sub_score = 50.0

    final_score = (
        (0.25 * engagement_sub_score)
        + (0.20 * reach_sub_score)
        + (0.20 * authenticity_sub_score)
        + (0.15 * retention_sub_score)
        + (0.10 * growth_sub_score)
        + (0.10 * brand_fit_sub_score)
    )

    return CreatorScore(
        final_score=round(final_score, 2),
        interpretation=_interpret(final_score),
        engagement_metrics=engagement_metrics,
        reach_metrics=reach_metrics,
        retention_metrics=retention_metrics,
        growth_metrics=growth_metrics,
        fake_follower_signals=fake_follower_signals,
    )


def calculate_creator_score(posts: list[SinglePostInsights], account_data: dict[str, Any]) -> CreatorScore:
    """Backward-compatible alias for creator scoring entrypoint."""
    return generate_creator_score(posts, account_data)


__all__ = ["generate_creator_score", "calculate_creator_score"]
