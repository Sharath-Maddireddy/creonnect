from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ENV_PATH = REPO_ROOT / "backend" / ".env"

if BACKEND_ENV_PATH.exists():
    load_dotenv(dotenv_path=BACKEND_ENV_PATH)
else:
    load_dotenv()

if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.app.analytics.brand_match_engine import score_creator_against_brand
from backend.app.domain.brand_models import BrandProfile
from backend.app.services.creator_pool_service import get_all_creators


def run_test() -> None:
    creators = get_all_creators()
    print(f"Total creators fetched: {len(creators)}")

    brand = BrandProfile(
        brand_name="TestBrand",
        niche="fitness",
        min_followers=10000,
        max_followers=500000,
        min_engagement_rate=0.01,
        required_brand_safety_min=40.0,
    )

    failed_cases: list[dict] = []

    for creator in creators:
        try:
            score = score_creator_against_brand(
                account_id=creator.get("account_id"),
                brand=brand,
                creator_dominant_category=creator.get("creator_dominant_category"),
                brand_search_embedding=None,
                creator_embedding=creator.get("embedding"),
                follower_count=creator.get("follower_count"),
                avg_views=creator.get("avg_views"),
                avg_likes=creator.get("avg_likes"),
                avg_comments=creator.get("avg_comments"),
                ahs_score=creator.get("ahs_score"),
                predicted_engagement_rate=creator.get("predicted_engagement_rate"),
                visual_quality_score_total=creator.get("avg_visual_quality_score"),
                brand_safety_score_total_0_50=creator.get("avg_brand_safety_score"),
                adult_content_detected=creator.get("adult_content_detected"),
            )

            if score.disqualified:
                failed_cases.append(
                    {
                        "account_id": creator.get("account_id"),
                        "reason": "disqualified",
                        "details": score.disqualify_reasons,
                        "score": score.total_match_score,
                    }
                )
        except Exception as exc:
            import traceback

            failed_cases.append(
                {
                    "account_id": creator.get("account_id"),
                    "reason": "exception",
                    "details": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )

    print(f"\nFailed cases found: {len(failed_cases)}")
    for index, failed_case in enumerate(failed_cases[:10], start=1):
        if failed_case["reason"] == "exception":
            print(f"{index}. Exception for {failed_case['account_id']}: {failed_case['details']}")
            print(failed_case["traceback"])
        else:
            print(
                f"{index}. Disqualified {failed_case['account_id']}: "
                f"{failed_case['details']} (Score: {failed_case['score']})"
            )


if __name__ == "__main__":
    run_test()
