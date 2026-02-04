"""
Creator Momentum Tracking

Calculates momentum based on daily follower snapshots.
"""

from datetime import datetime
from typing import List, Dict


def calculate_momentum(snapshots: List[Dict]) -> Dict:
    """
    Calculate creator momentum from daily snapshots.
    
    Args:
        snapshots: List of snapshot dicts ordered by date ascending.
                   Each snapshot should have 'followers' and 'date' fields.
    
    Returns:
        Dict with momentum_value and momentum_label
    """
    # Handle insufficient data
    if not snapshots or len(snapshots) < 2:
        return {
            "momentum_value": 0.0,
            "momentum_label": "flat"
        }
    
    # Use last 7 days if available, otherwise all snapshots
    window = snapshots[-7:] if len(snapshots) >= 7 else snapshots
    
    # Extract followers with defensive .get()
    latest_followers = window[-1].get("followers", 0) or 0
    previous_followers = window[0].get("followers", 0) or 0
    
    # Calculate number of days in window
    try:
        latest_date = window[-1].get("date", "")
        previous_date = window[0].get("date", "")
        
        if latest_date and previous_date:
            # Parse dates (handle both string and date objects)
            if isinstance(latest_date, str):
                latest_dt = datetime.fromisoformat(latest_date)
            else:
                latest_dt = latest_date
                
            if isinstance(previous_date, str):
                previous_dt = datetime.fromisoformat(previous_date)
            else:
                previous_dt = previous_date
            
            number_of_days = (latest_dt - previous_dt).days
        else:
            number_of_days = len(window) - 1
    except (ValueError, TypeError):
        number_of_days = len(window) - 1
    
    # Calculate momentum value (followers gained per day)
    momentum_value = (latest_followers - previous_followers) / max(number_of_days, 1)
    
    # Determine momentum label
    if momentum_value > 0:
        momentum_label = "accelerating"
    elif momentum_value < 0:
        momentum_label = "declining"
    else:
        momentum_label = "flat"
    
    return {
        "momentum_value": round(momentum_value, 2),
        "momentum_label": momentum_label
    }
