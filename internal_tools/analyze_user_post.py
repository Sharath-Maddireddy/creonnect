import asyncio
import json
import os
from datetime import date, datetime
from pathlib import Path

from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.services.post_insights_service import build_single_post_insights

REPO_ROOT = Path(__file__).resolve().parents[1]
INTERNAL_TOOLS_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = INTERNAL_TOOLS_DIR / "artifacts"

# Load env variables from backend/.env if it exists
env_path = REPO_ROOT / "backend" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _to_jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value

async def analyze_user_post():
    # Instagram CDN media URLs expire. Provide a fresh one at runtime before rerunning.
    media_url = (os.getenv("ANALYZE_USER_POST_MEDIA_URL") or "").strip()
    if not media_url:
        raise RuntimeError(
            "Set ANALYZE_USER_POST_MEDIA_URL to a fresh Instagram CDN media URL before running this script."
        )
    caption_text = "Fuel the rage. Lift harder."
    
    creator_post = CreatorPostAIInput(
        post_id="DV1UI3Dk2km",
        creator_id="ig_user",
        platform="instagram",
        post_type="REEL",
        media_url=media_url,
        thumbnail_url="",
        caption_text=caption_text,
        hashtags=[],
        likes=41,
        comments=2,
        views=1500 # Estimated or observed
    )
    
    print(f"Analyzing post DV1UI3Dk2km...")
    res = await build_single_post_insights(
        target_post=creator_post,
        historical_posts=[],
        run_ai=True,
        run_advanced_caption_ai=True,
        run_advanced_audience_ai=True,
    )
    
    # Save the result
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = ARTIFACTS_DIR / "user_post_analysis_result.json"
    serialized_result = _to_jsonable(res)
    output_path.write_text(json.dumps(serialized_result, indent=2))
    print(f"Analysis complete. Results saved to {output_path}")
    
    # Print a summary to the console
    ai_analysis = res.get("ai_analysis", {})
    print("\n--- AI ANALYSIS SUMMARY ---")
    print(ai_analysis.get("summary", "No summary available."))
    
    print("\n--- SCORES ---")
    post = res["post"]
    print(f"Visual Quality (S1): {post.visual_quality_score.total}/10")
    print(f"Caption Effectiveness (S2): {post.caption_effectiveness_score.total_0_50}/50")
    print(f"Audience Relevance (S4): {post.audience_relevance_score.total_0_50}/50")
    print(f"Final Weighted Score: {post.weighted_post_score.score}/100")

if __name__ == "__main__":
    asyncio.run(analyze_user_post())
