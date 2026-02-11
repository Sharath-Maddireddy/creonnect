"""
Synthetic Instagram Creator Data Generator

Generates realistic creator profiles and posts for demo/testing purposes.
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path


# Niche configurations
NICHE_CONFIG = {
    "fitness": {
        "hashtags": ["fitness", "workout", "gym", "fitfam", "bodybuilding", "health", "gains", "training"],
        "captions": [
            "💪 Morning workout complete! Who else hits the gym early?",
            "Push yourself because no one else is going to do it for you 🔥",
            "5-minute ab routine you can do anywhere! Save this for later",
            "Rest day vibes. Recovery is just as important as training 🧘‍♂️",
            "Leg day never gets easier, you just get stronger 🦵",
            "Full body workout - no equipment needed! Perfect for home",
            "Progress update: 3 months of consistency 📈",
            "Quick protein shake recipe for post-workout gains 🥤"
        ],
        "bio_templates": [
            "Fitness Coach | Helping you transform 💪",
            "Personal Trainer | DM for coaching",
            "🏋️ Fitness enthusiast | Health tips daily"
        ]
    },
    "food": {
        "hashtags": ["foodie", "cooking", "recipe", "homemade", "yummy", "delicious", "foodporn", "chef"],
        "captions": [
            "Made this from scratch! Recipe in bio 👨‍🍳",
            "When comfort food hits different 🍝",
            "Quick 15-minute dinner idea for busy weeknights",
            "Trying out a new recipe - thoughts? 🤔",
            "Sunday brunch done right ☕🥞",
            "Healthy meal prep for the week ahead 📦",
            "This dessert is absolutely to die for 🍰",
            "Cooking tip: always season at every step!"
        ],
        "bio_templates": [
            "Home Chef 👨‍🍳 | Recipes & Food Tips",
            "Food Blogger | Making cooking easy",
            "🍕 Food lover sharing daily recipes"
        ]
    },
    "travel": {
        "hashtags": ["travel", "wanderlust", "explore", "adventure", "vacation", "travelblogger", "travelgram"],
        "captions": [
            "Found a hidden gem! 📍 Adding this to your must-visit list",
            "Chasing sunsets around the world 🌅",
            "The best views come after the hardest climbs ⛰️",
            "Living out of a suitcase and loving every moment ✈️",
            "This place exceeded all expectations 😍",
            "Budget travel tip: book flights mid-week!",
            "Exploring local culture is the best part of travel",
            "POV: You finally booked that dream trip 🏝️"
        ],
        "bio_templates": [
            "Travel Blogger ✈️ | 30+ countries",
            "Wanderlust 🌍 | Tips & Guides",
            "Adventure seeker | Budget travel expert"
        ]
    }
}


def generate_synthetic_creator(
    niche: str = "fitness",
    followers: int = None,
    num_posts: int = 10,
    username: str = None
) -> dict:
    """Generate a synthetic creator profile with posts."""
    
    config = NICHE_CONFIG.get(niche, NICHE_CONFIG["fitness"])
    
    # Generate random follower count if not provided
    if followers is None:
        followers = random.randint(10000, 500000)
    
    # Generate username if not provided
    if username is None:
        username = f"demo_{niche}_creator"
    
    # Calculate realistic metrics based on follower count
    engagement_rate = random.uniform(3.0, 12.0)  # 3-12% engagement
    avg_views = int(followers * random.uniform(0.3, 1.5))
    avg_likes = int(avg_views * engagement_rate / 100 * 0.85)
    avg_comments = int(avg_views * engagement_rate / 100 * 0.15)
    
    # Generate profile
    profile = {
        "username": username,
        "bio": random.choice(config["bio_templates"]),
        "followers": followers,
        "following": random.randint(200, 1500),
        "total_posts": random.randint(100, 500),
        "avg_likes": avg_likes,
        "avg_comments": avg_comments,
        "avg_views": avg_views,
        "posts_per_week": round(random.uniform(2.0, 7.0), 1),
        "niche": niche
    }
    
    # Generate posts
    posts = []
    base_time = datetime.utcnow()
    
    for i in range(num_posts):
        # Vary performance per post
        post_multiplier = random.uniform(0.5, 2.0)
        post_views = int(avg_views * post_multiplier)
        post_likes = int(avg_likes * post_multiplier * random.uniform(0.8, 1.2))
        post_comments = int(avg_comments * post_multiplier * random.uniform(0.5, 1.5))
        
        # Random hashtags subset
        post_hashtags = random.sample(config["hashtags"], k=random.randint(3, 6))
        
        post = {
            "post_id": f"post_{i+1:03d}",
            "post_type": "reel" if random.random() > 0.3 else "post",
            "caption_text": random.choice(config["captions"]),
            "hashtags": post_hashtags,
            "likes": post_likes,
            "comments": post_comments,
            "views": post_views,
            "posted_at": (base_time - timedelta(days=i*2 + random.randint(0, 1))).isoformat()
        }
        posts.append(post)
    
    return {
        "profile": profile,
        "posts": posts,
        "generated_at": datetime.utcnow().isoformat()
    }


def save_synthetic_creator(
    output_path: str = None,
    niche: str = "fitness",
    followers: int = None,
    num_posts: int = 10,
    username: str = None
):
    """Generate and save synthetic creator to JSON file."""
    
    data = generate_synthetic_creator(
        niche=niche,
        followers=followers,
        num_posts=num_posts,
        username=username
    )
    
    if output_path is None:
        output_path = Path(__file__).parent.parent / "demo" / "synthetic_creator.json"
    else:
        output_path = Path(output_path)
    
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    
    print(f"✓ Generated synthetic {niche} creator: @{data['profile']['username']}")
    print(f"  Followers: {data['profile']['followers']:,}")
    print(f"  Posts: {len(data['posts'])}")
    print(f"  Saved to: {output_path}")
    
    return data


if __name__ == "__main__":
    # Generate default fitness creator
    save_synthetic_creator(niche="fitness", followers=75000, num_posts=10)


