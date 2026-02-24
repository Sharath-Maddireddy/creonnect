"""
Post Comparison Engine

Compares consecutive posts to analyze performance trends.
"""


def compare_posts(current_post: dict, previous_post: dict) -> dict:
    """
    Compare current post against previous post.
    
    Args:
        current_post: dict with views, likes, comments
        previous_post: dict with views, likes, comments
    
    Returns:
        Comparison result with deltas, engagement change, and explanation
    """
    # Extract metrics with defensive .get()
    current_views = current_post.get("views", 0) or 0
    current_likes = current_post.get("likes", 0) or 0
    current_comments = current_post.get("comments", 0) or 0
    
    previous_views = previous_post.get("views", 0) or 0
    previous_likes = previous_post.get("likes", 0) or 0
    previous_comments = previous_post.get("comments", 0) or 0
    
    # Compute deltas
    delta_views = current_views - previous_views
    delta_likes = current_likes - previous_likes
    delta_comments = current_comments - previous_comments
    
    # Compute engagement rates
    engagement_current = (current_likes + current_comments) / max(current_views, 1)
    engagement_previous = (previous_likes + previous_comments) / max(previous_views, 1)
    
    # Engagement change percentage
    special_case_explanation = False
    if engagement_previous == 0 and engagement_current == 0:
        engagement_change_pct = 0.0
        explanation = "Engagement is unchanged at zero for both posts."
        special_case_explanation = True
    elif engagement_previous == 0 and engagement_current > 0:
        engagement_change_pct = None
        explanation = "First engagement recorded."
    else:
        engagement_change_pct = (
            (engagement_current - engagement_previous) / engagement_previous
        ) * 100
    
    # Determine relative performance label
    if engagement_current > engagement_previous:
        relative_performance_label = "better"
    elif engagement_current < engagement_previous:
        relative_performance_label = "worse"
    else:
        relative_performance_label = "same"
    
    # Generate explanation
    if not special_case_explanation:
        if engagement_change_pct is None:
            explanation = explanation
        else:
            abs_change = abs(round(engagement_change_pct, 1))
            if relative_performance_label == "better":
                explanation = f"This post performed better than your previous one with {abs_change}% higher engagement."
            elif relative_performance_label == "worse":
                explanation = f"This post performed worse than your previous one with {abs_change}% lower engagement."
            else:
                explanation = "This post performed similarly to your previous one."
    
    return {
        "delta_views": delta_views,
        "delta_likes": delta_likes,
        "delta_comments": delta_comments,
        "engagement_change_pct": round(engagement_change_pct, 2) if engagement_change_pct is not None else None,
        "relative_performance_label": relative_performance_label,
        "explanation": explanation
    }


