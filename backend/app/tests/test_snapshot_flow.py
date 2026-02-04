"""
Test Snapshot Flow

Load synthetic_creator_snapshot.json and run full AI pipeline.
No scraping. No APIs. No frontend. Just console output.
"""

import sys
import json
from datetime import datetime
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.app.ai.schemas import CreatorProfileAIInput, CreatorPostAIInput
from backend.app.ai.niche import detect_creator_niche
from backend.app.ai.growth_score import compute_growth_score
from backend.app.ai.post_insights import analyze_posts


def load_snapshot() -> dict:
    """Load synthetic_creator_snapshot.json"""
    snapshot_path = Path(__file__).parent / "synthetic_creator_snapshot.json"
    with open(snapshot_path, "r") as f:
        return json.load(f)


def convert_to_ai_inputs(snapshot: dict):
    """
    Convert JSON snapshot into CreatorProfileAIInput and list of CreatorPostAIInput.
    
    Returns:
        Tuple[CreatorProfileAIInput, List[CreatorPostAIInput]]
    """
    # Extract profile fields
    username = snapshot["username"]
    followers = snapshot["followers"]
    following = snapshot.get("following", 0)
    total_posts = snapshot.get("total_posts", 0)
    avg_likes = snapshot["avg_likes"]
    avg_comments = snapshot["avg_comments"]
    avg_views = snapshot["avg_views"]
    estimated_posts_per_week = snapshot.get("estimated_posts_per_week", 3.0)
    bio = snapshot.get("bio", "")
    
    # Calculate avg_engagement_rate_by_views
    if avg_views > 0:
        avg_engagement_rate_by_views = ((avg_likes + avg_comments) / avg_views) * 100
    else:
        avg_engagement_rate_by_views = 0.0
    
    # Build historical_engagement
    historical_engagement = {
        "avg_likes": avg_likes,
        "avg_comments": avg_comments,
        "avg_views": avg_views,
        "avg_engagement_rate_by_views": avg_engagement_rate_by_views
    }
    
    # Build CreatorProfileAIInput
    profile = CreatorProfileAIInput(
        creator_id=username,
        platform="instagram",
        username=username,
        bio_text=bio,
        followers_count=followers,
        following_count=following,
        total_posts=total_posts,
        avg_likes=avg_likes,
        avg_comments=avg_comments,
        avg_views=avg_views,
        posts_per_week=estimated_posts_per_week,
        posting_frequency_per_week=estimated_posts_per_week,
        historical_engagement=historical_engagement,
        profile_last_updated=datetime.utcnow()
    )
    
    # Build list of CreatorPostAIInput
    posts = []
    for post_data in snapshot.get("posts", []):
        post = CreatorPostAIInput(
            post_id=post_data["post_id"],
            creator_id=username,
            platform="instagram",
            post_type=post_data.get("post_type", "reel"),
            caption_text=post_data.get("caption", ""),
            hashtags=post_data.get("hashtags", []),
            likes=post_data.get("likes", 0),
            comments=post_data.get("comments", 0),
            views=post_data.get("views", None),
            audio_name=post_data.get("audio_name", None),
            posted_at=datetime.utcnow()
        )
        posts.append(post)
    
    return profile, posts


def run_snapshot_flow():
    """Run the full AI pipeline on the loaded snapshot."""
    
    print("=" * 60)
    print("SNAPSHOT FLOW TEST")
    print("=" * 60)
    
    # 1) Load snapshot
    print("\n[1] Loading synthetic_creator_snapshot.json...")
    snapshot = load_snapshot()
    print(f"    Loaded snapshot for @{snapshot['username']}")
    
    # 2) Convert to AI inputs
    print("\n[2] Converting to AI inputs...")
    profile, posts = convert_to_ai_inputs(snapshot)
    print(f"    Profile: @{profile.username} ({profile.followers_count:,} followers)")
    print(f"    Posts: {len(posts)} loaded")
    
    # 3) Run detect_creator_niche
    print("\n[3] Running detect_creator_niche...")
    niche_result = detect_creator_niche(profile, posts)
    print("\n--- NICHE RESULT ---")
    print(f"    Primary Niche:    {niche_result.get('primary_niche', 'N/A')}")
    print(f"    Confidence:       {niche_result.get('confidence', 'N/A')}")
    if niche_result.get('secondary_niches'):
        print(f"    Secondary Niches: {niche_result.get('secondary_niches')}")
    
    # 4) Run compute_growth_score
    print("\n[4] Running compute_growth_score...")
    growth_result = compute_growth_score(profile, posts)
    print("\n--- GROWTH SCORE ---")
    print(f"    Growth Score: {growth_result.get('growth_score', 'N/A')}")
    
    breakdown = growth_result.get("breakdown", {})
    if breakdown:
        print("\n    Breakdown:")
        for key, value in breakdown.items():
            print(f"      - {key}: {value}")
    
    metrics = growth_result.get("metrics", {})
    if metrics:
        print("\n    Metrics:")
        for key, value in metrics.items():
            if isinstance(value, float):
                print(f"      - {key}: {value:.2f}")
            else:
                print(f"      - {key}: {value}")
    
    # 5) Run analyze_posts
    print("\n[5] Running analyze_posts...")
    post_insights = analyze_posts(profile, posts)
    print("\n--- FIRST POST INSIGHT ---")
    if post_insights and len(post_insights) > 0:
        first_insight = post_insights[0]
        print(f"    Post ID:    {first_insight.get('post_id', 'N/A')}")
        print(f"    Post Type:  {first_insight.get('post_type', 'N/A')}")
        caption = first_insight.get('caption_text', 'N/A') or 'N/A'
        print(f"    Caption:    {caption[:50]}...")
        likes = first_insight.get('likes', 0)
        comments = first_insight.get('comments', 0)
        views = first_insight.get('views', 0)
        print(f"    Likes:      {likes:,}")
        print(f"    Comments:   {comments:,}")
        print(f"    Views:      {views:,}")
        
        if first_insight.get("performance_label"):
            print(f"    Performance: {first_insight.get('performance_label')}")
        if first_insight.get("engagement_rate"):
            print(f"    Engagement Rate: {first_insight.get('engagement_rate'):.2f}%")
    else:
        print("    No post insights returned.")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Followers:   {profile.followers_count:,}")
    avg_views_val = int(profile.avg_views) if profile.avg_views else 0
    print(f"  Avg Views:   {avg_views_val:,}")
    print(f"  Post Count:  {len(posts)}")
    print("=" * 60)
    print("[OK] Snapshot flow completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    run_snapshot_flow()
