"""
Run the NEW creator account analysis on every creator in creator_pool.json.
This builds realistic SinglePostInsights from the pool's aggregate metrics
and runs the full intelligence suite: engagement signals, vision summary,
content quality breakdown, and AI creator intelligence.
"""
from __future__ import annotations
import asyncio
import json
import math
import sys
import random

sys.path.insert(0, ".")

from backend.app.domain.post_models import (
    AudienceRelevanceScore, BrandSafetyScore, BenchmarkMetrics,
    CaptionEffectivenessScore, ContentClarityScore, CoreMetrics,
    DerivedMetrics, EngagementPotentialScore, SinglePostInsights,
    VisionAnalysis, VisionSignal, VisualQualityScore, WeightedPostScore,
)
from backend.app.analytics.account_health_engine import (
    compute_account_health_score,
    compute_account_engagement_signals,
    compute_account_vision_summary,
    compute_content_quality_breakdown,
)
from backend.app.services.account_ai_intelligence import generate_creator_intelligence

random.seed(42)


def _build_posts_from_pool(creator: dict, n: int = 10) -> list[SinglePostInsights]:
    """Synthesize realistic SinglePostInsights from creator_pool aggregates."""
    followers = max(creator["follower_count"], 1)
    avg_views = creator.get("avg_views", 0) or 0
    avg_likes = creator["avg_likes"]
    avg_comments = creator["avg_comments"]
    er = creator["predicted_engagement_rate"]
    vqs = creator["avg_visual_quality_score"]
    bss = creator["avg_brand_safety_score"]

    posts = []
    for i in range(n):
        # Vary each post ±20%
        jitter = 1.0 + random.uniform(-0.2, 0.2)
        likes = int(avg_likes * jitter)
        comments = int(avg_comments * jitter)
        views = int(avg_views * jitter) if avg_views > 0 else None
        reach = views if views else followers

        save_rate = round(er * 0.6 * jitter, 6)
        share_rate = round(er * 0.3 * jitter, 6)
        comment_rate = round(comments / max(reach, 1), 6)
        profile_visit_rate = round(er * 0.4 * jitter, 6)
        watch_through = round(random.uniform(0.50, 0.85) * jitter, 4)

        cringe = random.randint(5, 30)
        hook = round(random.uniform(0.6, 0.9) * jitter, 3)
        hook = max(0.0, min(1.0, hook))
        prod = random.choice(["medium", "high"])
        flaws = random.choice([[], [], ["slight overexposure"], ["shaky camera"]])

        # Scale S1 from avg_visual_quality_score (0-50 → 0-10 per sub)
        s1_base = round((vqs / 50.0) * 10.0, 1)
        posts.append(SinglePostInsights(
            account_id=creator["account_id"],
            media_id=f"post_{i+1}",
            media_type="REEL" if avg_views > 0 else "IMAGE",
            caption_text=f"Post #{i+1} by @{creator['username']}",
            core_metrics=CoreMetrics(likes=likes, comments=comments, saves=int(likes*0.08), shares=int(likes*0.03), impressions=reach),
            derived_metrics=DerivedMetrics(
                engagement_rate=round(er * jitter, 6),
                like_rate=round(likes / reach, 6),
                comment_rate=comment_rate,
                save_rate=save_rate,
                share_rate=share_rate,
                watch_through_rate=watch_through,
                profile_visit_rate=profile_visit_rate,
                engagements_total=likes + comments,
            ),
            benchmark_metrics=BenchmarkMetrics(),
            vision_analysis=VisionAnalysis(provider="gemini", status="ok", signals=[
                VisionSignal(
                    hook_strength_score=hook,
                    production_level=prod,
                    cringe_score=cringe,
                    technical_flaws=flaws,
                    adult_content_detected=creator.get("adult_content_detected", False),
                )
            ]),
            visual_quality_score=VisualQualityScore(
                composition=s1_base, lighting=s1_base,
                subject_clarity=min(s1_base+0.5, 10.0), aesthetic_quality=s1_base, total=s1_base*4
            ),
            content_clarity_score=ContentClarityScore(
                message_singularity=7.0, context_clarity=7.5, caption_alignment=6.5,
                visual_message_support=7.0, cognitive_load=7.0, total=35.0
            ),
            caption_effectiveness_score=CaptionEffectivenessScore(
                hook_score_0_100=65, length_score_0_100=60,
                hashtag_score_0_100=50, cta_score_0_100=55,
                s2_raw_0_100=58, total_0_50=29.0
            ),
            audience_relevance_score=AudienceRelevanceScore(
                post_category=creator["creator_dominant_category"],
                creator_dominant_category=creator["creator_dominant_category"],
                affinity_band="EXACT", s4_raw_0_100=88, total_0_50=44.0
            ),
            brand_safety_score=BrandSafetyScore(s6_raw_0_100=bss, total_0_50=round(bss/2, 1)),
            engagement_potential_score=EngagementPotentialScore(
                emotional_resonance=7.0, shareability=round(share_rate*100, 1),
                save_worthiness=8.0, comment_potential=6.5, novelty_or_value=7.0, total=35.0
            ),
            weighted_post_score=WeightedPostScore(
                post_type="REEL" if avg_views > 0 else "IMAGE",
                score=round(creator["ahs_score"] * jitter, 1),
                normalized_score_0_50=round(creator["ahs_score"] * jitter / 2, 1),
            ),
        ))
    return posts


SEP = "─" * 66
def bar(v, mx=100, w=22):
    if v is None: return "[──────────────────────] N/A"
    f = max(0, min(int((v/mx)*w), w))
    return f"[{'█'*f}{'─'*(w-f)}] {v:.1f}"


async def analyze_all(creators):
    for creator in creators:
        posts = _build_posts_from_pool(creator, n=10)

        ahs = compute_account_health_score(posts, follower_band="10k-100k")
        eng = compute_account_engagement_signals(posts)
        vis = compute_account_vision_summary(posts)
        cqb = compute_content_quality_breakdown(posts)
        intel = await generate_creator_intelligence(
            posts=posts,
            account_id=creator["account_id"],
            username=creator["username"],
            bio=creator.get("bio"),
            niche_tags=creator.get("niche_tags", []),
            creator_dominant_category=creator["creator_dominant_category"],
            follower_count=creator["follower_count"],
        )

        print(f"\n{'═'*66}")
        print(f"  @{creator['username']}  |  {creator['follower_count']:,} followers  |  {creator['creator_dominant_category'].upper()}")
        print(f"{'═'*66}")

        print(f"\n  🏆 AHS Score:  {ahs.ahs_score:.1f}/100  [{ahs.ahs_band}]")
        for k, p in ahs.pillars.items():
            print(f"     {k.replace('_',' ').title():<24} {bar(p.score,100,16)}  [{p.band}]")

        print(f"\n  📊 Engagement Signals:")
        print(f"     Audience Trust     {bar(eng.audience_trust_index)}")
        print(f"     Virality Potential {bar(eng.virality_potential)}")
        print(f"     Consistency        {bar(eng.consistency_score)}")
        print(f"     Save Rate:  {(eng.avg_save_rate or 0)*100:.2f}%   Share Rate: {(eng.avg_share_rate or 0)*100:.2f}%   Watch-Through: {(eng.avg_watch_through_rate or 0)*100:.1f}%")

        print(f"\n  👁  Vision:")
        print(f"     Hook Strength: {vis.avg_hook_strength:.2f}/1.0   Cringe: {vis.avg_cringe_score}/100 (low=good)   Production: {vis.avg_production_level}")
        if vis.common_technical_flaws:
            print(f"     Flaws: {', '.join(vis.common_technical_flaws)}")

        print(f"\n  🎨 Content Quality (avg sub-scores):")
        for k, v in cqb["visual_quality"].items():
            print(f"     S1 {k:<22} {bar(v,10,14)}")
        for k, v in cqb["engagement_potential"].items():
            print(f"     S5 {k:<22} {bar(v,10,14)}")

        print(f"\n  🤖 AI Intelligence:")
        print(f"     Persona:  {(intel.creator_persona or 'N/A')[:120]}")
        print(f"     Style:    {(intel.content_style_summary or 'N/A')[:100]}")
        print(f"     Themes:   {' · '.join(intel.top_performing_themes)}")
        print(f"     Brands:   {' · '.join(intel.brand_fit.fit_categories)}")
        if intel.brand_fit.red_flags:
            print(f"     🚩 Flags: {' · '.join(intel.brand_fit.red_flags)}")
        print()


with open("backend/app/demo/creator_pool.json") as f:
    creators = json.load(f)

# Run on first 4 creators (to keep runtime reasonable)
print(f"\nRunning NEW Creator Account Analysis on {min(4, len(creators))} creators from creator_pool.json...")
asyncio.run(analyze_all(creators[:4]))
print("✅  DONE")
