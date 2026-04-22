"""
Fraud Detection Module

Deterministic, explainable signals for non-organic behavior detection.
"""

from __future__ import annotations

from datetime import datetime
from math import sqrt
from typing import Dict, List, Optional, Tuple


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _sorted_snapshots(snapshots: List[Dict]) -> List[Dict]:
    if not snapshots:
        return []

    parsed = []
    has_dates = True
    for snap in snapshots:
        dt = _parse_date(snap.get("date"))
        if dt is None:
            has_dates = False
        parsed.append((dt, snap))

    if not has_dates:
        return snapshots

    parsed.sort(key=lambda item: item[0])
    return [item[1] for item in parsed]


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: List[float], mean_value: float) -> float:
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean_value) ** 2 for v in values) / len(values)
    return sqrt(variance)


def _compute_daily_deltas(snapshots: List[Dict]) -> List[Dict]:
    ordered = _sorted_snapshots(snapshots)
    if len(ordered) < 2:
        return []

    deltas = []
    for i in range(1, len(ordered)):
        current = ordered[i]
        previous = ordered[i - 1]

        current_followers = _safe_float(current.get("followers"))
        previous_followers = _safe_float(previous.get("followers"))
        raw_delta = current_followers - previous_followers

        current_date = _parse_date(current.get("date"))
        previous_date = _parse_date(previous.get("date"))
        days = 1
        if current_date and previous_date:
            days_diff = (current_date - previous_date).days
            if days_diff > 0:
                days = days_diff

        delta_per_day = raw_delta / max(days, 1)
        deltas.append({
            "date": current.get("date"),
            "delta_per_day": delta_per_day,
            "days": days
        })

    return deltas


def _compute_engagement_rate(post: Dict) -> Optional[float]:
    rate = post.get("engagement_rate_by_views")
    if rate is not None:
        try:
            return float(rate)
        except (TypeError, ValueError):
            return None

    likes = _safe_float(post.get("likes"))
    comments = _safe_float(post.get("comments"))
    views = _safe_float(post.get("views"))
    if views <= 0:
        return None
    return (likes + comments) / views


def _follower_spike_anomaly(snapshots: List[Dict]) -> Tuple[float, Optional[str]]:
    deltas = _compute_daily_deltas(snapshots)
    if len(deltas) < 2:
        return 0.0, None

    max_ratio = 0.0
    max_delta = 0.0
    max_avg = 0.0

    rolling = []
    for item in deltas:
        delta = item.get("delta_per_day", 0.0)
        if rolling:
            avg = _mean(rolling)
            if avg > 0 and delta > 3 * avg:
                ratio = delta / avg
                if ratio > max_ratio:
                    max_ratio = ratio
                    max_delta = delta
                    max_avg = avg
        rolling.append(delta)

    if max_ratio <= 3:
        return 0.0, None

    explanation = (
        f"A follower spike of about {max_delta:.0f} per day exceeded the recent "
        f"average by {max_ratio:.1f}x. This can indicate non-organic growth." 
    )
    return 1.0, explanation


def _post_performance_instability(posts: List[Dict]) -> Tuple[float, Optional[str]]:
    rates = []
    for idx, post in enumerate(posts):
        rate = _compute_engagement_rate(post)
        if rate is not None:
            rates.append((idx, rate))

    if len(rates) < 3:
        return 0.0, None

    values = [rate for _, rate in rates]
    mean_value = _mean(values)
    std_value = _std(values, mean_value)
    if std_value <= 0:
        return 0.0, None

    rate_map = {idx: rate for idx, rate in rates}
    for idx, rate in rates:
        z = (rate - mean_value) / std_value
        if z > 3:
            next_one = rate_map.get(idx + 1)
            next_two = rate_map.get(idx + 2)
            if next_one is None or next_two is None:
                continue
            z1 = (next_one - mean_value) / std_value
            z2 = (next_two - mean_value) / std_value
            if abs(z1) <= 1 and abs(z2) <= 1:
                explanation = (
                    "A post significantly outperformed typical engagement, but the next "
                    "two posts returned to normal levels. This pattern can reflect short-term "
                    "artificial boosts." 
                )
                return 1.0, explanation

    return 0.0, None


def _engagement_quality(posts: List[Dict], creator: Dict) -> Tuple[float, Optional[str]]:
    likes_list = [
        _safe_float(post.get("likes"))
        for post in posts
        if post.get("likes") is not None
    ]
    if not likes_list:
        return 0.0, None

    creator_avg_likes = creator.get("avg_likes")
    if creator_avg_likes is None:
        avg_likes = _mean(likes_list)
    else:
        avg_likes = _safe_float(creator_avg_likes)
        if avg_likes <= 0:
            avg_likes = _mean(likes_list)

    if avg_likes <= 0:
        return 0.0, None

    high_like_posts = 0
    flagged = 0

    for post in posts:
        likes = _safe_float(post.get("likes"))
        comments = _safe_float(post.get("comments"))
        if likes <= 0:
            continue
        if likes >= avg_likes:
            high_like_posts += 1
            ratio = comments / likes
            if ratio < 0.005:
                flagged += 1

    if high_like_posts == 0 or flagged == 0:
        return 0.0, None

    score = min(1.0, flagged / high_like_posts)
    explanation = (
        "Several high-like posts have very low comment-to-like ratios (below 0.5%). "
        "This can suggest low-quality or non-organic engagement." 
    )
    return score, explanation


def _momentum_inconsistency(snapshots: List[Dict]) -> Tuple[float, Optional[str]]:
    deltas = _compute_daily_deltas(snapshots)
    if len(deltas) < 2:
        return 0.0, None

    abs_values = [abs(item.get("delta_per_day", 0.0)) for item in deltas]
    avg_abs = _mean(abs_values)
    if avg_abs <= 0:
        return 0.0, None

    for i in range(len(deltas) - 1):
        current_delta = deltas[i].get("delta_per_day", 0.0)
        next_delta = deltas[i + 1].get("delta_per_day", 0.0)
        if current_delta > 2 * avg_abs and next_delta < 0:
            explanation = (
                "A strong one-day follower gain was immediately followed by a decline. "
                "This swing can indicate non-organic activity." 
            )
            return 1.0, explanation

    return 0.0, None


def _label_for_score(score: int) -> str:
    if score >= 75:
        return "High Risk"
    if score >= 50:
        return "Likely Artificial"
    if score >= 25:
        return "Slightly Suspicious"
    return "Clean"


def detect_fraud_signals(
    creator: Dict,
    posts: List[Dict],
    snapshots: List[Dict]
) -> Dict:
    """
    Detect deterministic fraud signals from creator metrics.
    """

    posts = posts or []
    snapshots = snapshots or []

    if len(posts) < 3 or len(snapshots) < 3:
        return {
            "fraud_risk_score": 0,
            "fraud_label": "Insufficient Data",
            "fraud_signals": [
                "Not enough data to assess authenticity yet."
            ]
        }

    follower_score, follower_expl = _follower_spike_anomaly(snapshots)
    performance_score, performance_expl = _post_performance_instability(posts)
    engagement_score, engagement_expl = _engagement_quality(posts, creator)
    momentum_score, momentum_expl = _momentum_inconsistency(snapshots)

    weighted_score = (
        follower_score * 0.35 +
        performance_score * 0.25 +
        engagement_score * 0.25 +
        momentum_score * 0.15
    )
    final_score = int(round(weighted_score * 100))

    explanations = [
        expl for expl in [
            follower_expl,
            performance_expl,
            engagement_expl,
            momentum_expl
        ] if expl
    ]

    if not explanations:
        explanations.append("No unusual patterns detected in recent metrics.")

    return {
        "fraud_risk_score": final_score,
        "fraud_label": _label_for_score(final_score),
        "fraud_signals": explanations
    }
