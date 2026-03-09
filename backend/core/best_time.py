"""
Best Posting Time Analysis

Analyzes post performance by hour to determine optimal posting times.
"""

from datetime import datetime
from typing import Dict, List
from collections import defaultdict


def get_best_posting_hours(posts: List[Dict]) -> Dict:
    """
    Analyze posts to determine best posting hours.
    
    Args:
        posts: List of post dicts with created_at, likes, comments, views
    
    Returns:
        Dict with best_posting_hours and hourly_engagement breakdown
    """
    if not posts:
        return {
            "best_posting_hours": [],
            "hourly_engagement": {}
        }
    
    # Group engagement by hour
    hour_engagement = defaultdict(list)
    
    for post in posts:
        # Extract posting hour
        created_at = post.get("created_at") or post.get("posted_at")
        
        if not created_at:
            continue
        
        # Parse datetime if string
        try:
            if isinstance(created_at, str):
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            elif isinstance(created_at, datetime):
                dt = created_at
            else:
                continue
            
            hour = dt.hour
        except (ValueError, TypeError):
            continue
        
        # Calculate engagement rate by views
        likes = post.get("likes", 0) or 0
        comments = post.get("comments", 0) or 0
        views = post.get("views", 0) or 0
        
        engagement_rate = (likes + comments) / max(views, 1)
        hour_engagement[hour].append(engagement_rate)
    
    # Calculate average engagement per hour
    hourly_avg = {}
    for hour, rates in hour_engagement.items():
        hourly_avg[hour] = sum(rates) / len(rates) if rates else 0.0
    
    # Sort hours by average engagement descending
    sorted_hours = sorted(hourly_avg.keys(), key=lambda h: hourly_avg[h], reverse=True)
    
    # Get top 2 best hours (or fewer if not available)
    best_hours = sorted_hours[:2] if len(sorted_hours) >= 2 else sorted_hours
    
    # Convert hourly_engagement keys to strings
    hourly_engagement_str = {
        str(hour): round(avg, 4) for hour, avg in hourly_avg.items()
    }
    
    return {
        "best_posting_hours": best_hours,
        "hourly_engagement": hourly_engagement_str
    }


