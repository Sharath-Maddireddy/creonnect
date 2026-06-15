import asyncio
import json
import random
from pathlib import Path
from dotenv import load_dotenv

# Load env variables before importing database or LLMClient
load_dotenv("backend/.env", override=True)

from sqlalchemy.dialects.postgresql import insert
from backend.app.infra.database import init_db, get_async_sessionmaker
from backend.app.infra.models import CreatorVector, CreatorDiscoveryMeta
from backend.app.ai.llm_client import LLMClient
from backend.app.utils.logger import logger

NICHE_KEYWORDS = {
    "fitness": ["fit", "gym", "workout", "protein", "muscle", "abs", "training", "sports", "coach"],
    "food": ["cook", "chef", "food", "recipe", "kitchen", "meal", "baking", "diet"],
    "tech": ["tech", "gadget", "software", "ai", "pc", "unboxed", "unboxing", "review"],
    "fashion": ["style", "fashion", "outfit", "wear", "dress", "apparel"],
    "travel": ["travel", "wander", "explore", "trip", "vacation", "nature", "adventure"],
    "gaming": ["game", "play", "streaming", "twitch", "esports"],
    "beauty": ["beauty", "makeup", "skincare", "glow", "cosmetics"]
}

def guess_niche_and_tags(username: str, all_captions: str) -> tuple[str, list[str]]:
    dominant_category = "lifestyle"
    tags = ["lifestyle"]
    all_captions_lower = all_captions.lower()
    
    import re
    
    for cat, keywords in NICHE_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(kw)}\b", all_captions_lower) for kw in keywords):
            dominant_category = cat
            tags = [cat] + random.sample(keywords, min(2, len(keywords)))
            break
            
    if "cristiano" in username.lower():
        dominant_category = "sports"
        tags = ["sports", "football", "athlete"]
        
    return dominant_category, tags

async def seed_database():
    try:
        logger.info("Initializing database (verifying connection)...")
        await init_db(strict=True)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.error("Please make sure your Supabase project is active and the DATABASE_URL in backend/.env is correct.")
        return

    session_maker = get_async_sessionmaker()
    llm_client = LLMClient()
    
    files_to_parse = [
        "20_more_creators.json",
        "combined_new_batch_profiles_2026-05-03.json",
        "session_scraped_profiles_2026-05-07.json",
        "internal_tools/fixtures/combined_scraped_profiles.json"
    ]
    
    all_profiles = []
    
    # Read all files
    for file_path in files_to_parse:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"File {file_path} not found. Skipping.")
            continue
            
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                all_profiles.extend(data)
                logger.info(f"Loaded {len(data)} profiles from {file_path}")
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")

    # Process and deduplicate by username
    processed_usernames = set()
    records_to_insert = []
    
    for p in all_profiles:
        username = p.get("username", "unknown")
        if username in processed_usernames or username == "unknown":
            continue
            
        processed_usernames.add(username)
        
        followers = p.get("followers", 0)
        items = p.get("items", [])
        
        if not items:
            continue
            
        total_likes = 0
        total_comments = 0
        total_views = 0
        all_captions = ""
        
        for item in items:
            total_likes += item.get("like_count", 0)
            total_comments += item.get("comment_count", 0)
            views = item.get("view_count") or (item.get("raw", {}).get("video_views", 0)) or 0
            total_views += views
            all_captions += " " + (item.get("caption_text") or "").lower()
            
        avg_likes = int(total_likes / len(items))
        avg_comments = int(total_comments / len(items))
        avg_views = int(total_views / len(items))
        
        predicted_er = 0.0
        if followers > 0:
            predicted_er = (avg_likes + avg_comments) / followers
            
        dominant_category, tags = guess_niche_and_tags(username, all_captions)
        account_id = f"{username}_id"
        bio = p.get("biography", f"Scraped profile for {username}")
        
        # Construct a rich text block for the embedding
        source_text = f"Creator: {username}. Niche: {dominant_category}. Tags: {', '.join(tags)}. Bio: {bio}. Recent topics: {all_captions[:500]}"
        
        records_to_insert.append({
            "account_id": account_id,
            "username": username,
            "follower_count": followers,
            "creator_dominant_category": dominant_category,
            "niche_tags": tags,
            "bio": bio,
            "predicted_engagement_rate": predicted_er,
            "avg_views": avg_views,
            "avg_likes": avg_likes,
            "avg_comments": avg_comments,
            "ahs_score": random.randint(60, 90),
            "avg_visual_quality_score": random.randint(35, 48),
            "avg_brand_safety_score": random.randint(40, 50),
            "adult_content_detected": False,
            "posts_per_week": round(random.uniform(2.0, 7.0), 1),
            "source_text": source_text
        })
        
    logger.info(f"Prepared {len(records_to_insert)} unique profiles for insertion.")
    
    async with session_maker() as session:
        for idx, rec in enumerate(records_to_insert):
            logger.info(f"[{idx+1}/{len(records_to_insert)}] Generating embedding for {rec['username']}...")
            embedding = llm_client.embed(rec["source_text"])
            
            if not embedding:
                logger.error(f"Failed to generate embedding for {rec['username']}, skipping.")
                continue
                
            # Upsert into CreatorVector
            stmt_vector = insert(CreatorVector).values(
                account_id=rec["account_id"],
                embedding=embedding,
                source_text=rec["source_text"]
            )
            stmt_vector = stmt_vector.on_conflict_do_update(
                index_elements=['account_id'],
                set_={
                    'embedding': stmt_vector.excluded.embedding,
                    'source_text': stmt_vector.excluded.source_text,
                    'updated_at': stmt_vector.excluded.updated_at if hasattr(stmt_vector.excluded, 'updated_at') else None
                }
            )
            
            # Upsert into CreatorDiscoveryMeta
            stmt_meta = insert(CreatorDiscoveryMeta).values(
                account_id=rec["account_id"],
                username=rec["username"],
                follower_count=rec["follower_count"],
                creator_dominant_category=rec["creator_dominant_category"],
                niche_tags=rec["niche_tags"],
                bio=rec["bio"],
                predicted_engagement_rate=rec["predicted_engagement_rate"],
                avg_views=rec["avg_views"],
                avg_likes=rec["avg_likes"],
                avg_comments=rec["avg_comments"],
                ahs_score=rec["ahs_score"],
                avg_visual_quality_score=rec["avg_visual_quality_score"],
                avg_brand_safety_score=rec["avg_brand_safety_score"],
                adult_content_detected=rec["adult_content_detected"],
                posts_per_week=rec["posts_per_week"]
            )
            stmt_meta = stmt_meta.on_conflict_do_update(
                index_elements=['account_id'],
                set_={
                    'username': stmt_meta.excluded.username,
                    'follower_count': stmt_meta.excluded.follower_count,
                    'creator_dominant_category': stmt_meta.excluded.creator_dominant_category,
                    'niche_tags': stmt_meta.excluded.niche_tags,
                    'bio': stmt_meta.excluded.bio,
                    'predicted_engagement_rate': stmt_meta.excluded.predicted_engagement_rate,
                    'avg_views': stmt_meta.excluded.avg_views,
                    'avg_likes': stmt_meta.excluded.avg_likes,
                    'avg_comments': stmt_meta.excluded.avg_comments,
                    'updated_at': stmt_meta.excluded.updated_at if hasattr(stmt_meta.excluded, 'updated_at') else None
                }
            )
            
            try:
                await session.execute(stmt_vector)
                await session.execute(stmt_meta)
                await session.commit()
                logger.info(f"Successfully inserted {rec['username']}!")
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to insert {rec['username']} into DB: {e}")

    logger.info("Done seeding the database!")

if __name__ == "__main__":
    asyncio.run(seed_database())
