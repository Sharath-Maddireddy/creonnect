import asyncio
import json
import os
from pathlib import Path
from datetime import datetime
from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.services.post_insights_service import build_single_post_insights

env_path = Path("backend/.env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

async def test_post():
    target_url = "https://www.instagram.com/p/DV1UI3Dk2km/?utm_source=ig_web_copy_link&igsh=MzRlODBiNWFlZA=="
    creator_post = CreatorPostAIInput(
        post_id="DV1UI3Dk2km",
        creator_id="test_user",
        platform="instagram",
        post_type="REEL",
        media_url="https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=800",
        thumbnail_url="",
        caption_text="Fuel the rage. Lift harder.", 
        likes=28,
        comments=1,
        views=1000
    )
    res = await build_single_post_insights(
        target_post=creator_post,
        historical_posts=[],
        run_ai=True,
        run_advanced_caption_ai=True,
        run_advanced_audience_ai=True,
    )
    print("SUCCESS")
    
    # Also write the result to a file for easy viewing
    dump_res = res["post"].model_dump(mode="python")
    Path("test_analysis_result.json").write_text(json.dumps(dump_res, indent=2, default=str))

if __name__ == "__main__":
    asyncio.run(test_post())
