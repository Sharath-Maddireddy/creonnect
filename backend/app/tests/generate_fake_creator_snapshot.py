"""
Synthetic Creator Snapshot Generator

Generates realistic aggregated creator profile + posts data for demo/testing purposes.
Output format matches human-readable snapshot structure.

Supports multiple tiers and niches for diverse training data.
"""

import json
import random
from pathlib import Path


# =============================================================================
# TIER CONFIGURATION
# =============================================================================

TIERS = {
    "micro": {
        "followers_range": (1000, 8000),
        "views_multiplier": (0.3, 0.8),
        "engagement_rate": (0.04, 0.09),
    },
    "mid": {
        "followers_range": (10000, 100000),
        "views_multiplier": (0.4, 1.5),
        "engagement_rate": (0.02, 0.07),
    },
    "macro": {
        "followers_range": (120000, 500000),
        "views_multiplier": (0.5, 2.0),
        "engagement_rate": (0.01, 0.04),
    },
    "dead": {
        "followers_range": (2000, 50000),
        "views_multiplier": (0.05, 0.2),
        "engagement_rate": (0.003, 0.01),
    },
}

TIER_WEIGHTS = {
    "micro": 40,
    "mid": 35,
    "macro": 15,
    "dead": 10,
}


# =============================================================================
# NICHE CONFIGURATION
# =============================================================================

NICHES = ["fitness", "lifestyle", "food", "tech", "fashion"]

NICHE_CONFIG = {
    "fitness": {
        "captions": [
            "Morning routine hits different 💪",
            "Push yourself because no one else will",
            "Consistency over intensity 🔥",
            "5 min ab routine - save this!",
            "Leg day never gets easier",
            "Full body workout - no equipment needed",
            "3 month progress update 📈",
            "Quick post-workout shake recipe",
            "Trust the process 💯",
            "POV: You finally start your journey",
        ],
        "hashtags": ["fitness", "workout", "gym", "fitfam", "health", "gains", "training", "bodybuilding"],
        "bios": [
            "Fitness Coach | Helping you transform 💪",
            "Personal Trainer | DM for coaching",
            "🏋️ Fitness enthusiast | Health tips daily",
            "On a mission to inspire 🔥 | Fitness tips",
        ],
        "username_prefix": "fit",
    },
    "lifestyle": {
        "captions": [
            "Living my best life ✨",
            "Slow mornings are the best mornings",
            "Mindset is everything",
            "Small steps, big results",
            "New week, new goals",
            "This changed everything for me",
            "Rest day vibes 🧘",
            "Self care Sunday 💆",
            "Daily routines that work",
            "Gratitude journaling changed my life",
        ],
        "hashtags": ["lifestyle", "motivation", "wellness", "mindset", "selfcare", "dailyroutine", "positivity"],
        "bios": [
            "Lifestyle creator | Mindset • Growth",
            "Living intentionally ✨ | Daily inspo",
            "Wellness advocate | Self-improvement tips",
            "Creating the life I love 🌿",
        ],
        "username_prefix": "life",
    },
    "food": {
        "captions": [
            "Made this from scratch! Recipe in bio 👨‍🍳",
            "When comfort food hits different 🍝",
            "Quick 15-minute dinner idea",
            "Sunday brunch done right ☕🥞",
            "Healthy meal prep for the week 📦",
            "This dessert is to die for 🍰",
            "Cooking tip: always season at every step!",
            "Easy recipe anyone can make",
            "Restaurant quality at home",
            "Food is love 🍕",
        ],
        "hashtags": ["foodie", "cooking", "recipe", "homemade", "yummy", "delicious", "foodporn", "chef"],
        "bios": [
            "Home Chef 👨‍🍳 | Recipes & Food Tips",
            "Food Blogger | Making cooking easy",
            "🍕 Food lover sharing daily recipes",
            "Cooking made simple | DM for collabs",
        ],
        "username_prefix": "chef",
    },
    "tech": {
        "captions": [
            "This gadget changed my workflow 🔥",
            "iPhone vs Android - my honest take",
            "Best apps for productivity 📱",
            "Tech tip: most people don't know this",
            "Unboxing the latest release",
            "Setup tour 2024 🖥️",
            "Is this worth the hype? Let's find out",
            "Budget tech that performs",
            "AI tools everyone should use",
            "Coding life 💻",
        ],
        "hashtags": ["tech", "gadgets", "technology", "coding", "programming", "apps", "setup", "developer"],
        "bios": [
            "Tech Reviewer | Honest opinions 💻",
            "Software Dev | Tech tips & tutorials",
            "🔧 Gadget geek | Tech made simple",
            "Building the future 🚀 | Tech content",
        ],
        "username_prefix": "tech",
    },
    "fashion": {
        "captions": [
            "Outfit of the day 🔥",
            "Thrift flip transformation",
            "Wardrobe essentials everyone needs",
            "How to style one piece 5 ways",
            "Get ready with me 💄",
            "Fashion week vibes ✨",
            "Budget fashion finds",
            "This trend is everything",
            "Capsule wardrobe tips",
            "Accessorize like a pro 👜",
        ],
        "hashtags": ["fashion", "style", "ootd", "outfit", "streetstyle", "fashionista", "trendy", "wardrobe"],
        "bios": [
            "Fashion Creator | Style tips daily 👗",
            "OOTD inspo | Sustainable fashion",
            "✨ Fashion lover | Thrift queen",
            "Style is self-expression | DM for collabs",
        ],
        "username_prefix": "style",
    },
}


# =============================================================================
# AUDIO OPTIONS
# =============================================================================

AUDIO_OPTIONS = [
    "original audio",
    "original audio",
    "original audio",
    "Trending Beat 2024",
    "Viral Sound",
    "Popular Track",
    "Remix Mix",
    "Summer Energy",
    "Chill Vibes",
]


# =============================================================================
# GENERATOR FUNCTIONS
# =============================================================================

def select_tier() -> str:
    """Select a tier based on weighted probabilities."""
    tiers = list(TIER_WEIGHTS.keys())
    weights = list(TIER_WEIGHTS.values())
    return random.choices(tiers, weights=weights, k=1)[0]


def select_niche() -> str:
    """Randomly select a niche."""
    return random.choice(NICHES)


def generate_creator_snapshot() -> dict:
    """Generate a synthetic creator snapshot with aggregated metrics and posts."""
    
    # Select tier and niche
    tier = select_tier()
    niche = select_niche()
    
    tier_config = TIERS[tier]
    niche_config = NICHE_CONFIG[niche]
    
    # Followers based on tier
    followers = random.randint(*tier_config["followers_range"])
    
    # Following: reasonable ratio
    following = random.randint(200, 1200)
    
    # Total posts: established creator
    total_posts = random.randint(80, 400)
    
    # Posts per week: 2-6 realistic posting frequency
    estimated_posts_per_week = round(random.uniform(2.0, 6.0), 1)
    
    # Avg views based on tier multiplier
    view_mult_low, view_mult_high = tier_config["views_multiplier"]
    avg_views = int(followers * random.uniform(view_mult_low, view_mult_high))
    
    # Engagement rate based on tier
    eng_low, eng_high = tier_config["engagement_rate"]
    engagement_rate = random.uniform(eng_low, eng_high)
    
    # Avg likes: engagement rate of avg_views (likes are ~85% of engagement)
    avg_likes = int(avg_views * engagement_rate * 0.85)
    
    # Avg comments: ~15% of engagement
    avg_comments = int(avg_views * engagement_rate * 0.15)
    avg_comments = max(avg_comments, random.randint(1, 5))  # minimum comments
    
    # Generate username based on niche
    username = f"{niche_config['username_prefix']}_creator_{random.randint(100, 999)}"
    
    # Generate 3-8 posts
    num_posts = random.randint(3, 8)
    posts = []
    
    for i in range(num_posts):
        # Views: randomized around avg_views (0.5x - 1.8x variance)
        variance = random.uniform(0.5, 1.8)
        post_views = int(avg_views * variance)
        
        # Likes: derived from views with engagement rate + small variance
        post_eng_rate = engagement_rate * random.uniform(0.8, 1.2)
        post_likes = int(post_views * post_eng_rate * 0.85)
        
        # Comments: derived from engagement
        post_comments = int(post_views * post_eng_rate * 0.15)
        post_comments = max(post_comments, random.randint(0, 5))
        
        # Hashtags: sometimes empty, usually 0-6 tags
        if random.random() < 0.15:
            post_hashtags = []
        else:
            num_tags = min(random.randint(2, 6), len(niche_config["hashtags"]))
            post_hashtags = random.sample(niche_config["hashtags"], k=num_tags)
        
        # Post type: mostly reels
        post_type = "reel" if random.random() > 0.25 else "photo"
        
        # Audio: only for reels
        if post_type == "reel":
            audio_name = random.choice(AUDIO_OPTIONS)
        else:
            audio_name = None
        
        post = {
            "post_id": f"post_{i+1:03d}",
            "post_type": post_type,
            "caption": random.choice(niche_config["captions"]),
            "hashtags": post_hashtags,
            "likes": post_likes,
            "comments": post_comments,
            "views": post_views,
            "audio_name": audio_name
        }
        posts.append(post)
    
    # Build snapshot
    snapshot = {
        "username": username,
        "bio": random.choice(niche_config["bios"]),
        "niche": niche,
        "tier": tier,
        "followers": followers,
        "following": following,
        "total_posts": total_posts,
        "estimated_posts_per_week": estimated_posts_per_week,
        "avg_likes": avg_likes,
        "avg_comments": avg_comments,
        "avg_views": avg_views,
        "posts": posts
    }
    
    return snapshot


def save_creator_snapshot(output_path: str = None) -> dict:
    """Generate and save creator snapshot to JSON file."""
    
    snapshot = generate_creator_snapshot()
    
    if output_path is None:
        output_path = Path(__file__).parent / "synthetic_creator_snapshot.json"
    else:
        output_path = Path(output_path)
    
    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)
    
    # Print summary
    print("=" * 50)
    print("Creator Snapshot Generated")
    print("=" * 50)
    print(f"  Tier:       {snapshot['tier']}")
    print(f"  Niche:      {snapshot['niche']}")
    print(f"  Followers:  {snapshot['followers']:,}")
    print(f"  Avg Views:  {snapshot['avg_views']:,}")
    print(f"  Post Count: {len(snapshot['posts'])}")
    print("=" * 50)
    print(f"Saved to: {output_path}")
    
    return snapshot


if __name__ == "__main__":
    save_creator_snapshot()
