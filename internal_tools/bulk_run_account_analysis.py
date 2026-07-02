import asyncio
import json
import logging
import argparse
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load env variables before importing backend logic
load_dotenv("backend/.env", override=True)

from backend.app.infra.database import init_db
from backend.app.services.account_analysis_jobs import enqueue_account_analysis_job_async
from internal_tools.seed_supabase_creators import guess_niche_and_tags

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bulk_analysis")

async def bulk_enqueue_analysis(json_file: str, max_profiles: int = 50):
    try:
        await init_db(strict=True)
    except Exception as e:
        logger.error(f"Failed to connect to DB: {e}")
        return

    path = Path(json_file)
    if not path.exists():
        logger.error(f"File not found: {json_file}")
        return

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            profiles = json.load(f)
            logger.info(f"Loaded {len(profiles)} profiles from {json_file}")
    except Exception as e:
        logger.error(f"Error reading {json_file}: {e}")
        return

    enqueued = 0
    for idx, p in enumerate(profiles):
        if enqueued >= max_profiles:
            break

        username = p.get("username")
        if not username:
            continue
            
        followers = p.get("followers", 0)
        items = p.get("items", [])
        if not items:
            continue

        account_id = f"{username}_id"
        bio = p.get("biography", f"Scraped profile for {username}")
        
        # Calculate some basic metrics for the payload
        total_likes = sum(item.get("like_count", 0) for item in items)
        total_comments = sum(item.get("comment_count", 0) for item in items)
        
        avg_likes = int(total_likes / len(items))
        avg_comments = int(total_comments / len(items))
        
        predicted_er = 0.0
        if followers > 0:
            predicted_er = (avg_likes + avg_comments) / followers

        all_captions = " ".join((item.get("caption_text") or "").lower() for item in items)
        dominant_category, tags = guess_niche_and_tags(username, all_captions)

        # Build posts array
        mapped_posts = []
        for item in items[:30]:  # Limit to 30 posts per account analysis logic
            mapped_posts.append({
                "media_id": item.get("id"),
                "media_url": item.get("video_versions", [{}])[0].get("url") if item.get("video_versions") else None, # Simplified
                "caption_text": item.get("caption_text", ""),
                "media_type": "REEL" if item.get("video_versions") else "IMAGE",
                "core_metrics": {
                    "likes": item.get("like_count", 0),
                    "comments": item.get("comment_count", 0),
                    "impressions": item.get("view_count", 0) or (item.get("raw", {}).get("video_views", 0)),
                }
            })

        payload = {
            "account_id": account_id,
            "username": username,
            "bio": bio,
            "follower_count": followers,
            "creator_dominant_category": dominant_category,
            "niche_tags": tags,
            "account_avg_engagement_rate": predicted_er * 100, # Assuming percentage
            "post_limit": 30,
            "posts": mapped_posts,
            "source": "bulk_script"
        }

        try:
            response = await enqueue_account_analysis_job_async(payload)
            logger.info(f"[{idx+1}] Enqueued {username} - Job ID: {response['job_id']}")
            enqueued += 1
            # Add a small delay to avoid hammering Redis/DB too fast
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Failed to enqueue {username}: {e}")

    logger.info(f"Done! Successfully enqueued {enqueued} analysis jobs.")
    logger.info("Ensure your backend workers (Celery/ARQ/etc) are running to process these.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk enqueue account analysis from scraped JSON")
    parser.add_argument("--file", type=str, default="internal_tools/fixtures/combined_scraped_profiles.json", help="Path to scraped JSON file")
    parser.add_argument("--limit", type=int, default=50, help="Max profiles to enqueue")
    args = parser.parse_args()

    asyncio.run(bulk_enqueue_analysis(args.file, args.limit))
