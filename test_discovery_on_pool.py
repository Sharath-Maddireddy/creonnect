import sys
import json
from backend.app.ai.llm_client import LLMClient
from backend.app.services.campaign_prompt_service import parse_campaign_prompt, build_brand_profile_from_parsed
from backend.app.services.creator_pool_service import get_all_creators, reload_creator_pool, _CREATOR_EMBEDDINGS_CACHE, find_lookalikes
from backend.app.analytics.brand_match_engine import score_creator_against_brand

def run_test(prompt: str, log_file):
    def log(msg):
        log_file.write(msg + "\n")
        print(msg)
        
    log(f"\n{'='*60}")
    log(f" BRAND PROMPT: '{prompt}'")
    log(f"{'='*60}\n")
    
    # 1. AI Parsing
    log("[1] AI is extracting requirements...")
    parsed = parse_campaign_prompt(prompt, brand_name="TestBrand")
    log(f"Parsed JSON: {json.dumps(parsed, indent=2)}\n")
    
    brand_profile = build_brand_profile_from_parsed(parsed)
    
    # Generate Semantic Embedding for search
    log("[1.5] Generating Semantic Embedding for prompt...")
    llm = LLMClient()
    brand_search_embedding = llm.embed(prompt)
    if brand_search_embedding:
        log("      -> Embedding generated successfully.")
    else:
        log("      -> Failed to generate embedding!")
    
    # 2. Score all creators in the DB
    reload_creator_pool() # ensure cache is fresh
    creators = get_all_creators()
    log(f"[2] Scoring {len(creators)} scraped creators from database...\n")
    
    results = []
    for c in creators:
        account_id = c.get("account_id", "unknown")
        creator_embedding = _CREATOR_EMBEDDINGS_CACHE.get(account_id)

        score = score_creator_against_brand(
            account_id=account_id,
            brand=brand_profile,
            creator_dominant_category=c.get("creator_dominant_category"),
            brand_search_embedding=brand_search_embedding,
            creator_embedding=creator_embedding,
            follower_count=c.get("follower_count"),
            avg_views=c.get("avg_views", 0),
            avg_likes=c.get("avg_likes", 0),
            avg_comments=c.get("avg_comments", 0),
            ahs_score=c.get("ahs_score"),
            predicted_engagement_rate=c.get("predicted_engagement_rate"),
            visual_quality_score_total=c.get("avg_visual_quality_score", 0.0),
            brand_safety_score_total_0_50=c.get("avg_brand_safety_score", 50.0),
            adult_content_detected=c.get("adult_content_detected")
        )
        results.append((c.get('username','unknown'), c.get('follower_count',0), c.get('creator_dominant_category','unknown'), score))
        
    # Sort by score descending
    results.sort(key=lambda x: x[3].total_match_score, reverse=True)
    
    # Print Top 3
    log("--- TOP LIKELY MATCHES ---")
    for rank, (uname, followers, category, match) in enumerate(results[:3], 1):
        if match.disqualified:
            continue
        log(f"#{rank} @{uname} ({category} | {followers:,} followers)")
        log(f"    Match Band : {match.match_band} ({match.total_match_score:.2f} / 100)")
        log(f"    Breakdowns : Niche Fit={match.niche_fit}/20, Audience Size={match.audience_size_fit}/20, Safety={match.brand_safety_fit}/20")
        log("")
        
    log("--- DISQUALIFIED/WEAK MATCHES (Bottom 2) ---")
    for uname, followers, category, match in results[-2:]:
        log(f"@{uname} ({category} | {followers:,} followers) -> Score: {match.total_match_score:.2f} (Disqualified: {match.disqualified})")
        if match.disqualified:
            for reason in match.disqualify_reasons:
                log(f"    Reason: {reason}")

def run_lookalike_test(log_file):
    def log(msg):
        log_file.write(msg + "\n")
        print(msg)
        
    log(f"\n{'='*60}")
    log(f" LOOKALIKE DISCOVERY TEST")
    log(f"{'='*60}\n")
    
    target_id = "ann.le.do_id"  # Usually fitness/sports
    log(f"Finding lookalikes for {target_id}...")
    lookalikes = find_lookalikes(target_id, k=3)
    
    if not lookalikes:
        log("No lookalikes found! Embedded cache might be empty.")
    else:
        for idx, l in enumerate(lookalikes, 1):
            log(f"#{idx} @{l.get('username')} (Category: {l.get('creator_dominant_category')} | Followers: {l.get('follower_count')})")
            log(f"    Tags: {l.get('niche_tags')}")

if __name__ == "__main__":
    prompts = [
        "Find me fitness creators with over 100k followers to promote my new whey protein. Safe content only.",
        "Looking for a family or parenting blogger in fashion/lifestyle. Needs a minimum of 200k followers."
    ]
    
    with open("discovery_results.txt", "w", encoding="utf-8") as f:
        for p in prompts:
            run_test(p, f)
            
        run_lookalike_test(f)
