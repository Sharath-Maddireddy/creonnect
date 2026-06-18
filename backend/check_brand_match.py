import os
import sys

from dotenv import load_dotenv
load_dotenv(dotenv_path="c:/Users/ASUS/Documents/augment-projects/creonnect/backend/.env")

# Must set PYTHONPATH or run from backend dir
sys.path.append("c:/Users/ASUS/Documents/augment-projects/creonnect")

from backend.app.services.creator_pool_service import get_all_creators
from backend.app.analytics.brand_match_engine import score_creator_against_brand
from backend.app.domain.brand_models import BrandProfile

def run_test():
    creators = get_all_creators()
    print(f"Total creators fetched: {len(creators)}")
    
    brand = BrandProfile(
        brand_name="TestBrand",
        niche="fitness",
        min_followers=10000,
        max_followers=500000,
        min_engagement_rate=0.01,
        required_brand_safety_min=40.0
    )
    
    failed_cases = []
    
    for c in creators:
        try:
            score = score_creator_against_brand(
                account_id=c.get("account_id"),
                brand=brand,
                creator_dominant_category=c.get("creator_dominant_category"),
                brand_search_embedding=None,
                creator_embedding=c.get("embedding"),
                follower_count=c.get("follower_count"),
                avg_views=c.get("avg_views"),
                avg_likes=c.get("avg_likes"),
                avg_comments=c.get("avg_comments"),
                ahs_score=c.get("ahs_score"),
                predicted_engagement_rate=c.get("predicted_engagement_rate"),
                visual_quality_score_total=c.get("avg_visual_quality_score"),
                brand_safety_score_total_0_50=c.get("avg_brand_safety_score"),
                adult_content_detected=c.get("adult_content_detected")
            )
            
            if score.disqualified:
                failed_cases.append({
                    "account_id": c.get("account_id"),
                    "reason": "disqualified",
                    "details": score.disqualify_reasons,
                    "score": score.total_match_score
                })
        except Exception as e:
            import traceback
            failed_cases.append({
                "account_id": c.get("account_id"),
                "reason": "exception",
                "details": str(e),
                "traceback": traceback.format_exc()
            })

    print(f"\nFailed cases found: {len(failed_cases)}")
    for i, fc in enumerate(failed_cases[:10]):
        if fc['reason'] == 'exception':
            print(f"{i+1}. Exception for {fc['account_id']}: {fc['details']}")
            print(fc['traceback'])
        else:
            print(f"{i+1}. Disqualified {fc['account_id']}: {fc['details']} (Score: {fc['score']})")

if __name__ == "__main__":
    run_test()
