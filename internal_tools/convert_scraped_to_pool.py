import json
import random
from pathlib import Path

def convert():
    fixture_path = Path("internal_tools/fixtures/combined_scraped_profiles.json")
    out_path = Path("backend/app/demo/creator_pool.json")
    
    with open(fixture_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)
        
    pool = []
    
    # Simple keyword mapping for niche
    niche_keywords = {
        "fitness": ["fit", "gym", "workout", "protein", "muscle", "abs", "training", "sports"],
        "food": ["cook", "chef", "food", "recipe", "kitchen", "meal"],
        "tech": ["tech", "gadget", "software", "ai", "pc", "unboxed", "unboxing"],
        "fashion": ["style", "fashion", "outfit", "wear", "dress"],
        "travel": ["travel", "wander", "explore", "trip", "vacation"],
        "gaming": ["game", "play", "streaming", "twitch", "esports"],
        "beauty": ["beauty", "makeup", "skincare", "glow", "cosmetics"]
    }

    for p in profiles:
        username = p.get("username", "unknown")
        followers = p.get("followers", 0)
        items = p.get("items", [])
        
        if not items:
            continue
            
        total_likes = 0
        total_comments = 0
        total_views = 0
        
        # Combine all captions to guess the niche
        all_captions = ""
        
        for item in items:
            total_likes += item.get("like_count", 0)
            total_comments += item.get("comment_count", 0)
            views = item.get("view_count") or (item.get("raw", {}).get("video_views", 0)) or 0
            total_views += views
            all_captions += " " + (item.get("caption_text") or "").lower()
            
        avg_likes = total_likes / len(items)
        avg_comments = total_comments / len(items)
        avg_views = total_views / len(items)
        
        # Compute Engagement Rate
        predicted_er = 0.0
        if followers > 0:
            predicted_er = (avg_likes + avg_comments) / followers
            
        # Guess Niche
        dominant_category = "lifestyle"  # default
        tags = ["lifestyle"]
        for cat, keywords in niche_keywords.items():
            if any(kw in all_captions for kw in keywords):
                dominant_category = cat
                tags = [cat] + random.sample(keywords, min(2, len(keywords)))
                break
                
        # If it's Cristiano, hardcode sports
        if "cristiano" in username.lower():
            dominant_category = "sports"
            tags = ["sports", "football", "athlete"]

        pool.append({
            "account_id": f"{username}_id",
            "username": username,
            "creator_dominant_category": dominant_category,
            "follower_count": followers,
            # Assign decent default scores for testing
            "ahs_score": random.randint(60, 90),
            "predicted_engagement_rate": round(predicted_er, 4),
            "avg_visual_quality_score": random.randint(35, 48),
            "avg_brand_safety_score": random.randint(40, 50),
            "adult_content_detected": False,
            "bio": f"Scraped profile for {username}",
            "avg_views": int(avg_views),
            "avg_likes": int(avg_likes),
            "avg_comments": int(avg_comments),
            "posts_per_week": round(random.uniform(2.0, 7.0), 1),
            "niche_tags": tags
        })
        
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2)
        
    print(f"Successfully converted {len(pool)} scraped profiles into a new mock database at {out_path}!")

if __name__ == "__main__":
    convert()
