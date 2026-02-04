from typing import Dict, List, Optional
from datetime import datetime

from backend.app.ai.schemas import CreatorPostAIInput, CreatorProfileAIInput
from backend.core.post_comparison import compare_posts


# ------------------------------------------------
# PDF-Based Instagram Metric Calculations
# ------------------------------------------------

def _calculate_total_interactions(likes: int, comments: int) -> int:
    """Total interactions = likes + comments"""
    return likes + comments


def _calculate_engagement_rate_by_views(
    total_interactions: int,
    views: Optional[int]
) -> Optional[float]:
    """
    Engagement Rate by Views = total_interactions / views
    This is the PRIMARY metric for Instagram in 2025+
    """
    if not views or views <= 0:
        return None
    return round(total_interactions / views, 4)


def _calculate_like_rate(likes: int, views: Optional[int]) -> Optional[float]:
    """Like Rate = (likes / views) * 100"""
    if not views or views <= 0:
        return None
    return round((likes / views) * 100, 2)


def _calculate_comment_rate(comments: int, views: Optional[int]) -> Optional[float]:
    """Comment Rate = (comments / views) * 100"""
    if not views or views <= 0:
        return None
    return round((comments / views) * 100, 2)


def _calculate_relative_performance(
    post_engagement_rate: Optional[float],
    creator_avg_engagement_rate: Optional[float]
) -> Optional[float]:
    """
    Relative Performance = post_engagement_rate / creator_average_engagement_rate
    > 1.0 means above average, < 1.0 means below average
    """
    if post_engagement_rate is None or creator_avg_engagement_rate is None:
        return None
    if creator_avg_engagement_rate <= 0:
        return None
    return round(post_engagement_rate / creator_avg_engagement_rate, 2)


def _has_caption_context(caption: str) -> bool:
    """Caption has context if >=3 words"""
    if not caption:
        return False
    return len(caption.split()) >= 3


def _has_cta(caption: str) -> bool:
    """Check for call-to-action keywords"""
    if not caption:
        return False

    cta_keywords = [
        "comment", "share", "save", "follow",
        "link in bio", "dm", "tell me", "what do you think"
    ]
    text = caption.lower()
    return any(k in text for k in cta_keywords)


def _generate_insights(
    engagement_rate_by_views: Optional[float],
    relative_performance: Optional[float],
    like_rate: Optional[float],
    comment_rate: Optional[float],
    caption_context_present: bool,
    cta_present: bool,
    views: Optional[int]
) -> List[str]:
    """Generate human-readable insights based on metrics"""
    insights = []

    # View-based engagement insight
    if engagement_rate_by_views is not None:
        if engagement_rate_by_views >= 0.10:
            insights.append(
                f"Excellent engagement rate by views ({engagement_rate_by_views * 100:.2f}%). "
                "Content is resonating strongly with viewers."
            )
        elif engagement_rate_by_views >= 0.05:
            insights.append(
                f"Good engagement rate by views ({engagement_rate_by_views * 100:.2f}%). "
                "Above average for Instagram content."
            )
        elif engagement_rate_by_views >= 0.02:
            insights.append(
                f"Average engagement rate by views ({engagement_rate_by_views * 100:.2f}%). "
                "Room for improvement in viewer engagement."
            )
        else:
            insights.append(
                f"Low engagement rate by views ({engagement_rate_by_views * 100:.2f}%). "
                "Consider optimizing content for better viewer interaction."
            )
    elif views is None or views == 0:
        insights.append(
            "No view data available. Engagement rate by views cannot be calculated."
        )

    # Relative performance insight
    if relative_performance is not None:
        if relative_performance >= 1.5:
            insights.append(
                f"This post performed {relative_performance}x your average - "
                "a standout piece of content."
            )
        elif relative_performance >= 1.0:
            insights.append(
                f"This post performed {relative_performance}x your average - "
                "in line with or above your typical content."
            )
        else:
            insights.append(
                f"This post performed {relative_performance}x your average - "
                "below your typical engagement."
            )

    # Comment rate insight
    if comment_rate is not None and like_rate is not None:
        if comment_rate > 0 and like_rate > 0:
            comment_to_like_ratio = comment_rate / like_rate
            if comment_to_like_ratio >= 0.1:
                insights.append(
                    "High comment-to-like ratio indicates strong audience conversation."
                )

    # Caption context insight
    if not caption_context_present:
        insights.append(
            "Caption provides minimal context. Adding more detail could improve retention."
        )

    # CTA insight
    if not cta_present:
        insights.append(
            "No call-to-action detected. Adding a CTA can boost interactions."
        )

    return insights


# ------------------------------------------------
# Public API: Single Post Analysis
# ------------------------------------------------

def analyze_post(
    post: CreatorPostAIInput,
    creator_profile: CreatorProfileAIInput
) -> Dict:
    """
    Analyze a single Instagram post using PDF-based metrics.
    
    Primary metrics:
    - engagement_rate_by_views (interactions / views)
    - like_rate (likes / views)
    - comment_rate (comments / views)
    - relative_performance (vs creator average)
    """

    # Calculate total interactions
    total_interactions = _calculate_total_interactions(post.likes, post.comments)

    # Get views (may be None for static posts)
    views = post.views

    # Calculate view-based metrics
    engagement_rate_by_views = _calculate_engagement_rate_by_views(
        total_interactions, views
    )
    like_rate = _calculate_like_rate(post.likes, views)
    comment_rate = _calculate_comment_rate(post.comments, views)

    # Get creator's average engagement rate for relative performance
    hist_engagement = creator_profile.historical_engagement or {}
    creator_avg_engagement_rate = hist_engagement.get("avg_engagement_rate_by_views")

    relative_performance = _calculate_relative_performance(
        engagement_rate_by_views,
        creator_avg_engagement_rate
    )

    # Caption analysis
    caption_context_present = _has_caption_context(post.caption_text)
    cta_present = _has_cta(post.caption_text)

    # Generate insights
    insights = _generate_insights(
        engagement_rate_by_views,
        relative_performance,
        like_rate,
        comment_rate,
        caption_context_present,
        cta_present,
        views
    )

    return {
        "post_id": post.post_id,
        "total_interactions": total_interactions,
        "engagement_rate_by_views": engagement_rate_by_views,
        "like_rate": like_rate,
        "comment_rate": comment_rate,
        "relative_performance": relative_performance,
        "caption_context_present": caption_context_present,
        "cta_present": cta_present,
        "insights": insights
    }


# ------------------------------------------------
# Public API: Batch Post Analysis
# ------------------------------------------------

def analyze_posts(
    creator_profile: CreatorProfileAIInput,
    posts: List[CreatorPostAIInput]
) -> List[Dict]:
    """
    Batch wrapper for analyze_post.
    Analyzes all posts and returns list of results.
    Includes comparison_to_previous for each post (except the first).
    """

    results = []

    for i, post in enumerate(posts):
        try:
            result = analyze_post(post, creator_profile)
            
            # Add comparison to previous post (except for first post)
            if i > 0:
                current_post_data = {
                    "views": post.views or 0,
                    "likes": post.likes,
                    "comments": post.comments
                }
                previous_post = posts[i - 1]
                previous_post_data = {
                    "views": previous_post.views or 0,
                    "likes": previous_post.likes,
                    "comments": previous_post.comments
                }
                result["comparison_to_previous"] = compare_posts(
                    current_post_data, previous_post_data
                )
            
            results.append(result)
        except Exception as e:
            results.append({
                "post_id": post.post_id,
                "error": str(e)
            })

    return results

