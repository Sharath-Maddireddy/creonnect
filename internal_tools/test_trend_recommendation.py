import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / "backend" / ".env", override=True)

from backend.app.domain.account_models import CreatorIntelligence
from backend.app.domain.trend_models import GlobalTrend
from backend.app.analytics.trend_recommendation_engine import generate_trend_recommendations

async def main():
    print("Testing Trend Recommendation Engine...")
    
    # Mock intelligence
    intel = CreatorIntelligence(
        creator_persona="A tech enthusiast who loves reviewing gadgets.",
        content_style_summary="Fast-paced, energetic, with deep technical dives.",
        creator_strengths=["Technical depth", "High energy", "Engaging editing"],
        top_performing_themes=["Smartphone reviews", "AI tool testing"]
    )
    
    # Mock trends
    trends = [
        GlobalTrend(
            topic_name="AI Image Generation Tips",
            trend_type="topic",
            momentum="rising",
            description="Tips and tricks for getting the best results from AI image generators like Midjourney."
        ),
        GlobalTrend(
            topic_name="Tech Gadgets Under $50",
            trend_type="topic",
            momentum="peaking",
            description="Showcasing budget-friendly tech gadgets that are highly useful."
        )
    ]
    
    try:
        recs, gaps, insights, bullets = await generate_trend_recommendations(intel, trends, recommendation_count=2)
        print(f"\nGenerated {len(recs)} recommendations:")
        for idx, r in enumerate(recs, 1):
            print(f"\n{idx}. {r.suggested_title}")
            print(f"   Rationale: {r.rationale}")
            print(f"   Impact: {r.expected_impact}")
            print(f"   Trend Ref: {r.trend_reference}")
            print(f"   Hook: {r.hook}")
            print(f"   Style: {r.content_style}")
            print(f"   Opp Score: {r.opportunity_score}")
        
        print("\nOpportunity Bullets:")
        for b in bullets:
            print(f"- {b}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
