"""
Dashboard API Router

Exposes creator metrics in a frontend-friendly format for charts and graphs.
All computations are done server-side - frontend only plots.
"""

from fastapi import APIRouter
from backend.app.tests.load_synthetic import load_synthetic
from backend.app.ai.niche import detect_creator_niche
from backend.app.ai.growth_score import compute_growth_score
from backend.app.ai.post_insights import analyze_posts


router = APIRouter(prefix="/api", tags=["Dashboard"])


@router.get("/creator/dashboard")
def creator_dashboard():
    """
    Get complete creator dashboard data including:
    - Summary metrics
    - Post insights
    - Time-series data for charts
    """
    profile, posts = load_synthetic()

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

    return {
        "summary": {
            "username": profile.username,
            "followers": profile.followers_count,
            "growth_score": growth["growth_score"],
            "avg_engagement_rate_by_views": growth["metrics"]["avg_engagement_rate_by_views"],
            "avg_views": growth["metrics"]["avg_views"],
            "views_to_followers_ratio": growth["metrics"]["views_to_followers_ratio"],
            "posts_per_week": growth["metrics"]["posts_per_week"],
            "niche": niche
        },

        "posts": post_insights,

        "charts": {
            "engagement_over_time": engagement_series,
            "views_over_time": views_series
        }
    }
