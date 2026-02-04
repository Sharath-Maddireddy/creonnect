"""
Dashboard Service

Orchestrates creator dashboard data assembly.
"""

from datetime import date, timedelta

from backend.app.demo.synthetic_loader import load_synthetic
from backend.app.ai.niche import detect_creator_niche
from backend.app.ai.growth_score import compute_growth_score
from backend.app.ai.post_insights import analyze_posts
from backend.app.ai.rag import retrieve, generate_action_plan
from backend.core.snapshots import build_creator_snapshot
from backend.core.momentum import calculate_momentum
from backend.core.best_time import get_best_posting_hours


def build_creator_dashboard(creator_id: str) -> dict:
    """
    Build the full creator dashboard response.

    Raises:
        ValueError: if creator not found
    """
    profile, posts = load_synthetic()

    if profile.username != creator_id and creator_id != "demo":
        raise ValueError("Creator not found")

    niche = detect_creator_niche(profile, posts)
    growth = compute_growth_score(profile, posts)
    post_insights = analyze_posts(profile, posts)

    # Time-series for charts
    engagement_series = []
    views_series = []

    for p, insight in zip(posts, post_insights):
        engagement_series.append({
            "date": p.posted_at.isoformat() if p.posted_at else None,
            "value": insight.get("engagement_rate_by_views")
        })

        views_series.append({
            "date": p.posted_at.isoformat() if p.posted_at else None,
            "value": p.views
        })

    # Generate simulated snapshot history for momentum calculation
    # In production, this would come from a database
    today = date.today()
    simulated_snapshots = []
    base_followers = profile.followers_count - 500  # Simulate growth
    for i in range(7):
        day = today - timedelta(days=6 - i)
        simulated_snapshots.append({
            "date": day.isoformat(),
            "followers": base_followers + (i * 80)  # ~80 followers/day growth
        })

    # Calculate momentum
    momentum = calculate_momentum(simulated_snapshots)

    # Calculate best posting times
    posts_for_time_analysis = [
        {
            "created_at": p.posted_at.isoformat() if p.posted_at else None,
            "likes": p.likes,
            "comments": p.comments,
            "views": p.views or 0
        }
        for p in posts
    ]
    best_time = get_best_posting_hours(posts_for_time_analysis)

    # Retrieve knowledge for action plan
    query = f"{niche.get('primary_niche', 'creator')} growth strategies engagement tips"
    knowledge_chunks = retrieve(query, k=3)

    # Generate action plan
    creator_metrics = {
        "followers": profile.followers_count,
        "growth_score": growth["growth_score"],
        "avg_views": growth["metrics"]["avg_views"],
        "avg_engagement_rate_by_views": growth["metrics"]["avg_engagement_rate_by_views"],
        "posts_per_week": growth["metrics"]["posts_per_week"]
    }

    recent_posts = [
        {
            "likes": p.likes,
            "comments": p.comments,
            "views": p.views or 0
        }
        for p in posts[-3:]  # Last 3 posts
    ]

    action_plan = generate_action_plan(
        creator_metrics=creator_metrics,
        niche_data=niche,
        momentum=momentum,
        best_time=best_time,
        recent_posts=recent_posts,
        knowledge_chunks=knowledge_chunks
    )

    # Build snapshot (kept for parity with existing pipeline usage)
    _ = build_creator_snapshot({
        "username": profile.username,
        "followers": profile.followers_count,
        "avg_views": profile.avg_views or 0,
        "avg_likes": profile.avg_likes,
        "avg_comments": profile.avg_comments,
        "growth_score": growth.get("growth_score", 0)
    })

    return {
        "summary": {
            "username": profile.username,
            "followers": profile.followers_count,
            "growth_score": growth["growth_score"],
            "avg_engagement_rate_by_views": growth["metrics"]["avg_engagement_rate_by_views"],
            "avg_views": growth["metrics"]["avg_views"],
            "views_to_followers_ratio": growth["metrics"]["views_to_followers_ratio"],
            "posts_per_week": growth["metrics"]["posts_per_week"],
            "niche": niche,
            "momentum": momentum,
            "best_time_to_post": best_time
        },

        "posts": post_insights,

        "charts": {
            "engagement_over_time": engagement_series,
            "views_over_time": views_series
        },

        "action_plan": action_plan
    }
