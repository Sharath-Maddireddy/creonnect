import sys
import json
import asyncio
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.services.post_insights_service import build_single_post_insights
from backend.app.ai.schemas import CreatorPostAIInput
from datetime import datetime

async def run_cristiano_test():
    print("Loading Cristiano data...")
    fixture_path = Path("internal_tools/fixtures/ig_cristiano_raw.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Convert to CreatorPostAIInput format
    posts = []
    for item in data["items"]:
        try:
            # Handle date parsing
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
                hashtags=[], # Extracted later by pipeline if needed, or parse from caption
                likes=item["like_count"],
                comments=item["comment_count"],
                views=item["view_count"] if item["view_count"] > 0 else None,
                audio_name=None,
                posted_at=posted_at
            )
            posts.append(post_input)
        except Exception as e:
            print(f"Error parsing post {item.get('post_id')}: {e}")

    print(f"Loaded {len(posts)} posts. Running analysis on the most recent post...")
    
    if not posts:
        print("No posts found to analyze.")
        return

    target_post = posts[0]
    historical_posts = posts[1:]

    print(f"\n--- Target Post Details ---")
    print(f"ID: {target_post.post_id}")
    print(f"Likes: {target_post.likes:,}")
    print(f"Comments: {target_post.comments:,}")
    print(f"Caption: {target_post.caption_text[:100]}...")

    print("\n--- Running AI Pipeline ---")
    try:
        result = await build_single_post_insights(
            target_post=target_post,
            historical_posts=historical_posts,
            run_ai=True,
            run_advanced_caption_ai=True,
            run_advanced_audience_ai=True
        )
        with open("cristiano_result.json", "w", encoding="utf-8") as f:
            f.write(result["post"].model_dump_json(indent=2))
        
        print("\n--- Analysis Success ---")
        print("Data written to cristiano_result.json")
        
        # Display derived metrics
        derived = result["post"].derived_metrics
        print("\nDerived Metrics:")
        print(f"  Engagement Rate (by Reach): {derived.engagement_rate}")
        print(f"  Like Rate: {derived.like_rate}")
        print(f"  Comment Rate: {derived.comment_rate}")

        # Display benchmark metrics
        benchmarks = result["post"].benchmark_metrics
        print("\nBenchmark Metrics (vs Historical):")
        if benchmarks:
            print(f"  Likes vs Avg: {benchmarks.likes_percent_vs_avg}%")
            print(f"  Comments vs Avg: {benchmarks.comments_percent_vs_avg}%")
            print(f"  Engagement Percentile: {benchmarks.percentile_engagement_rank}")
        else:
            print("  No benchmark metrics available.")

        # Display AI Scores
        print("\nAI Scores:")
        content_score = result.get("content_score", {})
        print(f"  Content Score: {content_score.get('score_0_100', 'N/A')}/100 ({content_score.get('band', 'N/A')})")
        
        s2 = result["post"].caption_effectiveness_score
        if s2:
            print(f"  S2 Caption Score: {s2.s2_raw_0_100}/100")
            print(f"  S2 Hook Strength: {s2.hook_score_0_100}")
        
        # Display AI Analysis
        ai = result.get("ai_analysis", {})
        if ai:
            print("\nAI Insights:")
            print(f"  Summary: {ai.get('summary', 'N/A')[:100]}...")
            
            drivers = ai.get("drivers", [])
            print(f"\nDrivers ({len(drivers)}):")
            for d in drivers:
                print(f"  - [{d.get('type')}] {d.get('label')}: {d.get('explanation')}")
                
            recs = ai.get("recommendations", [])
            print(f"\nRecommendations ({len(recs)}):")
            for r in recs:
                print(f"  - [{r.get('impact_level')}] {r.get('text')}")
        else:
            print("\nNo AI Analysis returned.")

    except Exception as e:
        print(f"\nPipeline Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_cristiano_test())
