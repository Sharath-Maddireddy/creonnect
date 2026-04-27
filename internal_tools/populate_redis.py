import asyncio
from backend.app.infra.redis_client import set_json
from backend.app.services.post_snapshot_store import POST_INSIGHTS_CACHE_KEY_PREFIX
from backend.app.demo.synthetic_loader import load_synthetic

async def main():
    print("Loading synthetic data...")
    profile, posts = load_synthetic()
    for post in posts[:2]:
        print(f"Mocking AI analysis for {post.post_id}...")
        # Since we might not want to wait for real LLM calls if keys aren't set, 
        # let's just construct a dummy payload mimicking what it returns.
        dummy_result = {
            "post": {
                "media_id": post.post_id,
                "media_url": post.media_url,
                "caption_text": post.caption_text,
                "published_at": post.posted_at.isoformat() if post.posted_at else None,
                "reach_breakdown": {
                    "home": 12000,
                    "explore": 8000,
                    "hashtags": 3000,
                    "profile": 1000
                },
                "engagement_timeline": [
                    {"timestamp": "2026-03-20T10:00:00Z", "cumulative_engagement": 100},
                    {"timestamp": "2026-03-20T11:00:00Z", "cumulative_engagement": 350},
                    {"timestamp": "2026-03-20T15:00:00Z", "cumulative_engagement": 900},
                    {"timestamp": "2026-03-21T08:00:00Z", "cumulative_engagement": 1200}
                ],
                "core_metrics": {
                    "impressions": 25000,
                    "reach": 24000,
                    "likes": 1100,
                    "comments": 150,
                    "saves": 300,
                    "shares": 50
                },
                "benchmark_metrics": {
                    "percentile_engagement_rank": 0.85,
                    "reach_percent_vs_avg": 12.5,
                    "impressions_percent_vs_avg": 5.0,
                    "likes_percent_vs_avg": 20.0,
                    "comments_percent_vs_avg": 40.0,
                    "saves_percent_vs_avg": -2.0,
                    "shares_percent_vs_avg": 15.0
                },
                "derived_metrics": {}
            },
            "ai_analysis": {
                "summary": "This post performed exceptionally well due to the strong hook in the first 3 seconds, drawing higher engagement from the Explore page than your usual average.",
                "ai_content_score": 88,
                "ai_content_band": "HIGH_POTENTIAL",
                "drivers": [
                    {"type": "POSITIVE", "label": "Visual Quality", "explanation": "High contrast and saturated colors stopped scrollers."},
                    {"type": "POSITIVE", "label": "Caption Effectiveness", "explanation": "The call-to-action generated a surge in comments."},
                    {"type": "LIMITING", "label": "Hashtag Relevance", "explanation": "Used overly broad tags preventing niche discovery."}
                ],
                "recommendations": [
                    {"text": "Replicate this strong visual hook in your next Reel.", "impact_level": "HIGH"},
                    {"text": "Use more specific hashtags next time.", "impact_level": "LOW"}
                ],
                "niche_context": {
                    "category": "Tech Education",
                    "follower_band": "10k-50k",
                    "commentary": "Your engagement rate of 5% vastly outperforms the 2% niche average for this post type."
                }
            }
        }
        
        set_json(f"{POST_INSIGHTS_CACHE_KEY_PREFIX}{post.post_id}", dummy_result, ttl_seconds=86400)
        
        print(f"Successfully wrote mock snapshot into Redis for {post.post_id}")

if __name__ == "__main__":
    asyncio.run(main())
