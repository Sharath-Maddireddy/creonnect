"""
Build Training Dataset

Generate training examples for future fine-tuning.
Loads synthetic snapshot, runs AI pipeline, constructs training record.
No model training. No OpenAI calls. Pure dataset creation.
"""

import sys
import json
import uuid
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
    
    # Calculate avg_engagement_rate_by_views (ratio)
    if avg_views > 0:
        avg_engagement_rate_by_views = (avg_likes + avg_comments) / avg_views
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
            post_type=post_data.get("post_type", "IMAGE"),
            media_url=post_data.get("media_url", ""),
            thumbnail_url=post_data.get("thumbnail_url", ""),
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


def build_training_record(snapshot: dict, profile, posts, niche_result, growth_result, post_insights):
    """
    Construct training record in the specified format.
    """
    # Build input.profile
    input_profile = {
        "username": snapshot["username"],
        "followers": snapshot["followers"],
        "avg_likes": snapshot["avg_likes"],
        "avg_comments": snapshot["avg_comments"],
        "avg_views": snapshot["avg_views"],
        "posts_per_week": snapshot.get("estimated_posts_per_week", 3.0)
    }
    
    # Build input.posts
    input_posts = []
    for post_data in snapshot.get("posts", []):
        input_posts.append({
            "caption": post_data.get("caption", ""),
            "likes": post_data.get("likes", 0),
            "comments": post_data.get("comments", 0),
            "views": post_data.get("views", 0)
        })
    
    # Build training record
    training_record = {
        "example_id": uuid.uuid4().hex,
        "created_at": datetime.utcnow().isoformat(),
        "input": {
            "profile": input_profile,
            "posts": input_posts
        },
        "output": {
            "niche": niche_result,
            "growth": growth_result,
            "post_insights": post_insights
        },
        "quality": "good"
    }
    
    return training_record


def append_to_jsonl(record: dict, output_path: Path):
    """Append training record as JSON line to file."""
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def build_training_example():
    """Build and append one training example from the current snapshot."""
    
    # 1) Load snapshot
    snapshot = load_snapshot()
    
    # 2) Convert to AI inputs
    profile, posts = convert_to_ai_inputs(snapshot)
    
    # 3) Run AI pipeline
    niche_result = detect_creator_niche(profile, posts)
    growth_result = compute_growth_score(profile, posts)
    post_insights = analyze_posts(profile, posts)
    
    # 4) Construct training record
    training_record = build_training_record(
        snapshot=snapshot,
        profile=profile,
        posts=posts,
        niche_result=niche_result,
        growth_result=growth_result,
        post_insights=post_insights
    )
    
    # 5) Append as JSON line to training_data.jsonl
    output_path = Path(__file__).parent / "training_data.jsonl"
    append_to_jsonl(training_record, output_path)
    
    # 6) Print confirmation
    print("Training example appended.")


if __name__ == "__main__":
    build_training_example()


