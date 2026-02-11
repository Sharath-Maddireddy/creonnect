"""
Synthetic Instagram API Data Generator

Generates realistic Instagram Graph API–style JSON data for testing.
Compatible with backend/app/ingestion/instagram_mapper.py

Output:
- synthetic_instagram_profile.json
- synthetic_instagram_media.json

Usage:
    python backend/app/tests/generate_fake_instagram_api.py
"""

import json
import random
import uuid
import sys
from datetime import datetime, timedelta
from pathlib import Path


# ------------------------------------------------
# Configuration
# ------------------------------------------------

MODE_CONFIG = {
    "micro": {
        "followers_range": (500, 8000),
        "views_multiplier": (0.2, 0.6),
        "engagement_rate": (0.03, 0.07),
        "bio": "trying to grow | fitness journey 💪"
    },
    "mid": {
        "followers_range": (10000, 150000),
        "views_multiplier": (0.4, 1.6),
        "engagement_rate": (0.025, 0.08),
        "bio": "fitness | lifestyle | consistency 🔥"
    },
    "macro": {
        "followers_range": (200000, 1500000),
        "views_multiplier": (0.6, 2.2),
        "engagement_rate": (0.015, 0.05),
        "bio": "athlete | brands | community 🏆"
    },
    "dead": {
        "followers_range": (2000, 50000),
        "views_multiplier": (0.05, 0.2),
        "engagement_rate": (0.005, 0.02),
        "bio": "old account 📸"
    }
}

FITNESS_CAPTIONS = [
    "💪 Morning workout complete! Who else hits the gym early?",
    "Push yourself because no one else is going to do it for you 🔥",
    "5-minute ab routine you can do anywhere! Save this for later",
    "Rest day vibes. Recovery is just as important as training 🧘‍♂️",
    "Leg day never gets easier, you just get stronger 🦵",
    "Full body workout - no equipment needed! Perfect for home",
    "Progress update: 3 months of consistency 📈",
    "Quick protein shake recipe for post-workout gains 🥤",
    "This workout changed everything for me 🙌",
    "Trust the process. Results take time ⏰",
    "Form check! Am I doing this right? 🤔",
    "New PR today! Feeling unstoppable 💥",
    "Meal prep Sunday vibes 🍗🥦",
    "Your only limit is you. Let's go! 🚀",
    "Before vs After - consistency is key 📊"
]


# ------------------------------------------------
# Generator Functions
# ------------------------------------------------

def generate_profile(mode: str = "mid") -> dict:
    """Generate Instagram API profile JSON."""
    config = MODE_CONFIG.get(mode, MODE_CONFIG["mid"])
    
    followers = random.randint(*config["followers_range"])
    
    return {
        "id": str(random.randint(1000000000, 9999999999)),
        "username": f"synthetic_{mode}_creator",
        "name": f"Synthetic {mode.title()} Creator",
        "biography": config["bio"],
        "followers_count": followers,
        "follows_count": random.randint(200, 1500),
        "media_count": random.randint(50, 500),
        "account_type": "CREATOR",
        "profile_picture_url": f"https://instagram.com/synthetic_{mode}_creator/profile.jpg"
    }


def generate_media(followers: int, mode: str = "mid", count: int = 10) -> list:
    """Generate Instagram API media list JSON."""
    config = MODE_CONFIG.get(mode, MODE_CONFIG["mid"])
    
    media = []
    base_time = datetime.utcnow()
    
    # Spread timestamps based on mode
    days_spread = 90 if mode == "dead" else 14
    
    for i in range(count):
        # Variance: some posts viral, some weak
        variance = random.choice([0.5, 0.75, 1.0, 1.0, 1.0, 1.25, 1.5, 2.0])
        
        # Calculate views
        base_views = followers * random.uniform(*config["views_multiplier"])
        views = int(base_views * variance)
        
        # Calculate engagement
        engagement_rate = random.uniform(*config["engagement_rate"])
        total_interactions = int(views * engagement_rate)
        
        # Split into likes and comments (comments = 5-15% of interactions)
        comment_ratio = random.uniform(0.05, 0.15)
        comments = int(total_interactions * comment_ratio)
        likes = total_interactions - comments
        
        # Timestamp
        days_ago = random.randint(0, days_spread) + (i * (days_spread // count))
        hours_ago = random.randint(0, 23)
        timestamp = (base_time - timedelta(days=days_ago, hours=hours_ago)).isoformat() + "Z"
        
        post_id = str(uuid.uuid4()).replace("-", "")[:17]
        
        media.append({
            "id": post_id,
            "media_type": "VIDEO",
            "media_url": f"https://instagram.com/p/{post_id}/media",
            "permalink": f"https://instagram.com/p/{post_id}/",
            "caption": random.choice(FITNESS_CAPTIONS),
            "like_count": likes,
            "comments_count": comments,
            "video_view_count": views,
            "timestamp": timestamp,
            "thumbnail_url": f"https://instagram.com/p/{post_id}/thumbnail.jpg"
        })
    
    # Sort by timestamp (newest first)
    media.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return media


def save_data(profile: dict, media: list, mode: str, output_dir: Path):
    """Save generated data to JSON files."""
    profile_path = output_dir / f"synthetic_{mode}_profile.json"
    media_path = output_dir / f"synthetic_{mode}_media.json"
    
    with open(profile_path, "w") as f:
        json.dump(profile, f, indent=2)
    
    with open(media_path, "w") as f:
        json.dump(media, f, indent=2)
    
    return profile_path, media_path


def print_summary(profile: dict, media: list, mode: str):
    """Print generation summary."""
    avg_views = sum(m["video_view_count"] for m in media) / len(media) if media else 0
    avg_engagement = sum(
        (m["like_count"] + m["comments_count"]) / m["video_view_count"] * 100
        for m in media if m["video_view_count"] > 0
    ) / len(media) if media else 0
    
    print("\n" + "=" * 50)
    print("SYNTHETIC INSTAGRAM API DATA GENERATED")
    print("=" * 50)
    print(f"Mode:            {mode}")
    print(f"Username:        @{profile['username']}")
    print(f"Followers:       {profile['followers_count']:,}")
    print(f"Posts Generated: {len(media)}")
    print(f"Avg Views:       {int(avg_views):,}")
    print(f"Avg Engagement:  {avg_engagement:.2f}%")
    print("=" * 50 + "\n")


# ------------------------------------------------
# Main
# ------------------------------------------------

def main():
    # Parse mode from CLI
    mode = "mid"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in MODE_CONFIG:
            mode = arg
        else:
            print(f"Unknown mode: {arg}")
            print(f"Available modes: {', '.join(MODE_CONFIG.keys())}")
            sys.exit(1)
    
    # Generate data
    profile = generate_profile(mode)
    media = generate_media(profile["followers_count"], mode, count=10)
    
    # Save to files
    output_dir = Path(__file__).parent
    profile_path, media_path = save_data(profile, media, mode, output_dir)
    
    # Print summary
    print_summary(profile, media, mode)
    print(f"Saved: {profile_path.name}")
    print(f"Saved: {media_path.name}")


if __name__ == "__main__":
    main()


