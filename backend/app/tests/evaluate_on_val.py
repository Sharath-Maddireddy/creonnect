"""
Evaluate AI Pipeline on Validation Set

Runs the AI pipeline on val.jsonl and computes metrics:
- Niche accuracy (predicted vs stored)
- Average growth score error
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.app.ai.schemas import CreatorProfileAIInput, CreatorPostAIInput
from backend.app.ai.niche import detect_creator_niche
from backend.app.ai.growth_score import compute_growth_score
from backend.app.ai.post_insights import analyze_posts


def load_val_data():
    """Load validation examples from val.jsonl."""
    val_file = Path(__file__).parent / "val.jsonl"
    examples = []
    
    with open(val_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    examples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    
    return examples


def reconstruct_inputs(example: dict):
    """Reconstruct AI input objects from stored example."""
    input_data = example["input"]
    profile_data = input_data["profile"]
    posts_data = input_data["posts"]
    
    # Build profile
    profile = CreatorProfileAIInput(
        creator_id="eval_creator",
        platform="instagram",
        username=profile_data["username"],
        bio_text="",
        followers_count=profile_data["followers"],
        following_count=500,
        total_posts=100,
        account_type="creator",
        avg_likes=profile_data["avg_likes"],
        avg_comments=profile_data["avg_comments"],
        avg_views=profile_data.get("avg_views"),
        posts_per_week=profile_data.get("posts_per_week", 3.0),
        historical_engagement={},
        posting_frequency_per_week=profile_data.get("posts_per_week", 3.0),
        profile_last_updated=datetime.now()
    )
    
    # Build posts
    posts = []
    for i, p in enumerate(posts_data):
        post = CreatorPostAIInput(
            post_id=f"post_{i+1:03d}",
            creator_id="eval_creator",
            platform="instagram",
            post_type="reel",
            caption_text=p.get("caption", ""),
            hashtags=[],
            likes=p.get("likes", 0),
            comments=p.get("comments", 0),
            views=p.get("views"),
            audio_name=None,
            posted_at=datetime.now()
        )
        posts.append(post)
    
    return profile, posts


def evaluate():
    """Run evaluation on validation set."""
    examples = load_val_data()
    
    if not examples:
        print("No validation examples found in val.jsonl")
        return
    
    total = len(examples)
    niche_correct = 0
    growth_errors = []
    
    print("=" * 50)
    print("EVALUATING ON VALIDATION SET")
    print("=" * 50)
    print(f"Loading {total} examples...\n")
    
    for i, example in enumerate(examples):
        try:
            # Reconstruct inputs
            profile, posts = reconstruct_inputs(example)
            
            # Run AI pipeline
            niche_result = detect_creator_niche(profile, posts)
            growth_result = compute_growth_score(profile, posts)
            
            # Get predictions
            predicted_niche = niche_result.get("primary_niche", "unknown")
            predicted_growth = growth_result.get("growth_score", 0)
            
            # Get stored values
            stored_output = example["output"]
            stored_niche = stored_output.get("niche", {}).get("primary_niche", "unknown")
            stored_growth = stored_output.get("growth", {}).get("growth_score", 0)
            
            # Compare niche
            if predicted_niche == stored_niche:
                niche_correct += 1
            
            # Compute growth error
            growth_error = abs(predicted_growth - stored_growth)
            growth_errors.append(growth_error)
            
            # Progress
            print(f"  [{i+1}/{total}] {profile.username}: niche={'OK' if predicted_niche == stored_niche else 'MISS'}, growth_err={growth_error}")
            
        except Exception as e:
            print(f"  [{i+1}/{total}] Error: {e}")
            continue
    
    # Compute metrics
    niche_accuracy = (niche_correct / total) * 100 if total > 0 else 0
    avg_growth_error = sum(growth_errors) / len(growth_errors) if growth_errors else 0
    
    # Print summary
    print("\n" + "=" * 50)
    print("EVALUATION RESULTS")
    print("=" * 50)
    print(f"  Total evaluated:       {total}")
    print(f"  Niche accuracy:        {niche_accuracy:.1f}% ({niche_correct}/{total})")
    print(f"  Avg growth score error: {avg_growth_error:.2f}")
    print("=" * 50)


if __name__ == "__main__":
    evaluate()
