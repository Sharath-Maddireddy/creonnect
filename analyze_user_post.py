import asyncio
import json
import os
from pathlib import Path
from datetime import datetime
from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.services.post_insights_service import build_single_post_insights

# Load env variables from backend/.env if it exists
env_path = Path("backend/.env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

async def analyze_user_post():
    # Data extracted from https://www.instagram.com/p/DV1UI3Dk2km/
    media_url = "https://instagram.fhyd3-1.fna.fbcdn.net/v/t51.82787-15/651751402_18427632301188392_5865403673126278636_n.jpg?stp=dst-jpegr_e35_tt6&_nc_cat=101&ig_cache_key=Mzg1MjA3MzYyNjA4NzE1NjAwNg%3D%3D.3-ccb7-5&ccb=7-5&_nc_sid=58cdad&efg=eyJ2ZW5jb2RlX3RhZyI6InhwaWRzLjE0NDB4MTkyMC5oZHIuQzMifQ%3D%3D&_nc_ohc=Go9cG5UrNY0Q7kNvwGRMPee&_nc_oc=Adlrz-IjiorIGpGsHhqV-4yVA4Tt-uWjrqifYEmNKFbUTLoZa5eEkJ1ay650B5V_VKs&_nc_zt=23&_nc_ht=instagram.fhyd3-1.fna&_nc_gid=TFeVrLX2wXK5LP_MKF4jzw&_nc_ss=8&oh=00_AfzMnNfANmctrZR_mhnd1_-x-mDW-kQnD16LAnrUiexhpQ&oe=69BC7207"
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
    output_path = Path("user_post_analysis_result.json")
    # Convert SinglePostInsights to dict
    post_data = res["post"].model_dump(mode="python")
    # Clean up non-serializable objects (like datetime)
    def json_serial(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError (f"Type {type(obj)} not serializable")

    output_path.write_text(json.dumps(res, indent=2, default=str)) # Use str as generic fallback for non-serializables
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
