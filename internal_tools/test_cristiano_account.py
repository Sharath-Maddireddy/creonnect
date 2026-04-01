import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.services.post_insights_service import build_single_post_insights
from backend.app.services.account_analysis_service import analyze_account_health
from backend.app.ai.schemas import CreatorPostAIInput

async def run_cristiano_account_analysis():
    print("Loading Cristiano data...")
    fixture_path = Path("internal_tools/fixtures/ig_cristiano_raw.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Convert to CreatorPostAIInput format
    posts_input = []
    for item in data["items"]:
        try:
            timestamp_str = item["raw"]["timestamp"]
            try:
                posted_at = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except ValueError:
                posted_at = datetime.utcnow()

            post_input = CreatorPostAIInput(
                post_id=item["post_id"],
                creator_id=data["username"],
                platform="instagram",
                post_type="IMAGE" if not item["raw"].get("is_video") else "REEL",
                media_url=item["media_url"],
                thumbnail_url=item.get("thumbnail_url", ""),
                caption_text=item.get("caption_text", ""),
                hashtags=[],
                likes=item["like_count"],
                comments=item["comment_count"],
                views=item["view_count"] if item["view_count"] > 0 else None,
                audio_name=None,
                posted_at=posted_at
            )
            posts_input.append(post_input)
        except Exception as e:
            print(f"Error parsing post {item.get('post_id')}: {e}")

    print(f"Loaded {len(posts_input)} posts. Converting to SinglePostInsights via AI pipeline...")
    
    analyzed_posts = []
    
    # Analyze all 10 posts to get SinglePostInsights objects
    for i, p_input in enumerate(posts_input):
        print(f"  Analyzing post {i+1}/10 ({p_input.post_id})...")
        try:
            # We don't need historical context for basic mapping here to keep the test fast
            # We also disable AI for speed, since AccountHealth primarily relies on the core/derived metrics + S1-S6 scalars
            result = await build_single_post_insights(
                target_post=p_input,
                historical_posts=[],
                run_ai=False,
                run_advanced_caption_ai=False,
                run_advanced_audience_ai=False
            )
            analyzed_posts.append(result["post"])
        except Exception as e:
            print(f"  Failed to analyze post {p_input.post_id}: {e}")
            
    print(f"\nSuccessfully built {len(analyzed_posts)} SinglePostInsights objects.")
    print("Running Account Health Analysis...")
    
    try:
        health_score = analyze_account_health(
            posts=analyzed_posts,
            account_avg_engagement_rate=0.04,  # Synthetic baseline
            niche_avg_engagement_rate=0.03,    # Synthetic baseline
            follower_band="macro",
            use_cache=False
        )
        
        # Write exactly how we did for the single post
        output_file = Path("cristiano_account_result.json")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(health_score.model_dump_json(indent=2))
            
        print("\n--- Account Health Analysis Success ---")
        print(f"Data written to {output_file}")
        
    except Exception as e:
        print(f"\nAccount Analysis Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_cristiano_account_analysis())
