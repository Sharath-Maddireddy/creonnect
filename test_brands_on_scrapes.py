"""
Test the brand match engine against the scraped Cristiano JSON files.

Since the scraped data has null for follower_count and creator_dominant_category,
we supplement with known facts about the creator and test multiple brand scenarios.
"""
import json
import sys

sys.path.insert(0, ".")

from backend.app.domain.brand_models import BrandProfile
from backend.app.analytics.brand_match_engine import score_creator_against_brand
from backend.app.services.campaign_prompt_service import parse_campaign_prompt, build_brand_profile_from_parsed


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_result(label: str, res) -> None:
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")
    print(f"  Total Match Score : {res.total_match_score:.2f} / 100")
    print(f"  Match Band        : {res.match_band}")
    print(f"  Disqualified      : {res.disqualified}")
    if res.disqualify_reasons:
        for r in res.disqualify_reasons:
            print(f"   ⚠ {r}")
    print(f"\n  Sub-scores (each out of 20):")
    print(f"    Niche Fit         : {res.niche_fit}")
    print(f"    Audience Size Fit : {res.audience_size_fit}")
    print(f"    Engagement Quality: {res.engagement_quality}")
    print(f"    Brand Safety Fit  : {res.brand_safety_fit}")
    print(f"    Content Quality   : {res.content_quality_fit}")


def main() -> None:
    print("\n=== Brand Match Engine — Scraped Data Test ===")
    print("Account: cristiano (real Instagram data)")

    account_data = load_json("cristiano_account_result.json")
    post_data = load_json("cristiano_result.json")

    # --- Extract what's available from JSONs ---
    account_id = post_data.get("account_id", "cristiano")
    ahs_score = account_data.get("ahs_score", 52.45)  # from account result

    # Post-level metrics
    visual_quality_total = post_data["visual_quality_score"]["total"]            # 20.25
    brand_safety_total = post_data["brand_safety_score"]["total_0_50"]           # 50.0
    adult_content = post_data["brand_safety_score"]["flags"]["adult_content_detected"]  # False

    # Null in scraped data => supplement with known facts
    creator_category = "sports"     # Cristiano is a top sports/lifestyle creator
    follower_count = 650_000_000    # ~650M followers on Instagram
    predicted_er = None             # null in scraped data

    print(f"\n  AHS Score         : {ahs_score}")
    print(f"  Visual Quality    : {visual_quality_total}/50")
    print(f"  Brand Safety      : {brand_safety_total}/50")
    print(f"  Adult Content     : {adult_content}")
    print(f"  Follower Count    : {follower_count:,} (supplemented)")
    print(f"  Category          : {creator_category} (supplemented)")

    def score(brand: BrandProfile) -> object:
        return score_creator_against_brand(
            account_id=account_id,
            brand=brand,
            creator_dominant_category=creator_category,
            follower_count=follower_count,
            ahs_score=ahs_score,
            predicted_engagement_rate=predicted_er,
            visual_quality_score_total=visual_quality_total,
            brand_safety_score_total_0_50=brand_safety_total,
            adult_content_detected=adult_content,
        )

    # ===== Scenario 1: Perfect fit (sports macro brand) =====
    brand_sports_macro = BrandProfile(
        brand_name="Nike",
        niche="sports",
        min_followers=10_000_000,
        max_followers=None,
        required_brand_safety_min=70.0,
    )
    print_result("SCENARIO 1: Nike (sports, macro) — EXPECTED: High match", score(brand_sports_macro))

    # ===== Scenario 2: Niche mismatch (tech startup, nano) =====
    brand_tech_nano = BrandProfile(
        brand_name="TechStartup",
        niche="tech",
        max_followers=50_000,
        required_brand_safety_min=60.0,
    )
    print_result("SCENARIO 2: TechStartup (tech, nano <50k) — EXPECTED: Poor match", score(brand_tech_nano))

    # ===== Scenario 3: Safety mismatch (requires very high brand safety) =====
    brand_strict_safety = BrandProfile(
        brand_name="KidsEdu",
        niche="sports",
        min_followers=1_000_000,
        required_brand_safety_min=95.0,  # very strict, our S6=100 scaled = 100 so passes
    )
    print_result("SCENARIO 3: KidsEdu (sports, very strict safety 95) — EXPECTED: Pass safety, good match", score(brand_strict_safety))

    # ===== Scenario 4: Lifestyle brand, partial niche match =====
    brand_lifestyle = BrandProfile(
        brand_name="GucciSport",
        niche="lifestyle",
        min_followers=5_000_000,
        required_brand_safety_min=60.0,
    )
    print_result("SCENARIO 4: GucciSport (lifestyle, partial match) — EXPECTED: Moderate match", score(brand_lifestyle))

    # ===== Scenario 5: Engagement rate minimum set, but ER is null =====
    brand_er_required = BrandProfile(
        brand_name="FitFuel",
        niche="sports",
        min_followers=1_000_000,
        min_engagement_rate=0.03,    # requires 3% ER, but creator's is null
        required_brand_safety_min=70.0,
    )
    print_result("SCENARIO 5: FitFuel (sports, needs 3% ER) — EXPECTED: No ER disqualify since ER is null", score(brand_er_required))

    # ===== Scenario 6: AI Prompt Driven =====
    prompt_str = "show me creators in tech field with minimum 50k folowers and good engagement rate"
    print(f"\n{'='*50}")
    print(f"  SCENARIO 6: AI Prompt Driven")
    print(f"  Prompt: '{prompt_str}'")
    print(f"  Calling LLM to parse...")
    try:
        parsed_brief = parse_campaign_prompt(prompt_str, brand_name="TechCorp AI Test")
        print(f"  Parsed JSON: {json.dumps(parsed_brief, indent=2)}")
        brand_ai = build_brand_profile_from_parsed(parsed_brief)
        print_result("SCENARIO 6: Match Results", score(brand_ai))
    except Exception as e:
        print(f"  AI Parsing failed: {e}")

    print(f"\n{'='*50}")
    print("  Done.")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
