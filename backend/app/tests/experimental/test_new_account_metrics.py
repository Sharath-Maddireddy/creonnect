"""
Test script: validates new account-level metrics (engagement signals, vision summary,
creator intelligence) against real fixture data.

Run from repo root:
    python test_new_account_metrics.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# ── synthetic fixture: build 3 realistic SinglePostInsights objects ─────────
from backend.app.domain.post_models import (
    AudienceRelevanceScore,
    BrandSafetyScore,
    BenchmarkMetrics,
    CaptionEffectivenessScore,
    ContentClarityScore,
    CoreMetrics,
    DerivedMetrics,
    EngagementPotentialScore,
    SinglePostInsights,
    VisionAnalysis,
    VisionSignal,
    VisualQualityScore,
    WeightedPostScore,
)
from backend.app.analytics.account_health_engine import (
    compute_account_engagement_signals,
    compute_account_vision_summary,
)
from backend.app.services.account_ai_intelligence import generate_creator_intelligence
from backend.app.domain.account_models import (
    AccountEngagementSignals,
    AccountVisionSummary,
    CreatorIntelligence,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_post(
    media_id: str,
    caption: str,
    save_rate: float | None,
    share_rate: float | None,
    profile_visit_rate: float | None,
    watch_through_rate: float | None,
    comment_rate: float | None,
    engagement_rate: float | None,
    cringe_score: int,
    production_level: str,
    hook_strength: float,
    technical_flaws: list[str],
    p_score: float,
    shareability: float = 6.0,
) -> SinglePostInsights:
    vision_signal = VisionSignal(
        objects=["person", "gym"],
        scene_description="Athlete working out in gym",
        visual_style="High-energy fitness",
        hook_strength_score=hook_strength,
        production_level=production_level,
        cringe_score=cringe_score,
        technical_flaws=technical_flaws,
        adult_content_detected=False,
    )
    return SinglePostInsights(
        account_id="test_creator",
        media_id=media_id,
        media_type="REEL",
        caption_text=caption,
        core_metrics=CoreMetrics(likes=1000, comments=50, saves=80, shares=30, impressions=10000),
        derived_metrics=DerivedMetrics(
            engagement_rate=engagement_rate,
            save_rate=save_rate,
            share_rate=share_rate,
            watch_through_rate=watch_through_rate,
            profile_visit_rate=profile_visit_rate,
            comment_rate=comment_rate,
        ),
        benchmark_metrics=BenchmarkMetrics(),
        vision_analysis=VisionAnalysis(provider="gemini", status="ok", signals=[vision_signal]),
        visual_quality_score=VisualQualityScore(composition=8.0, lighting=8.0, subject_clarity=9.0, aesthetic_quality=8.0, total=40.0),
        content_clarity_score=ContentClarityScore(message_singularity=7.0, context_clarity=8.0, caption_alignment=7.0, visual_message_support=7.0, cognitive_load=7.0, total=36.0),
        caption_effectiveness_score=CaptionEffectivenessScore(hook_score_0_100=75, length_score_0_100=60, hashtag_score_0_100=50, cta_score_0_100=55, s2_raw_0_100=60, total_0_50=30.0),
        audience_relevance_score=AudienceRelevanceScore(post_category="fitness", creator_dominant_category="fitness", affinity_band="EXACT", s4_raw_0_100=90, total_0_50=45.0),
        brand_safety_score=BrandSafetyScore(s6_raw_0_100=95, total_0_50=47.5),
        engagement_potential_score=EngagementPotentialScore(emotional_resonance=7.0, shareability=shareability, save_worthiness=8.0, comment_potential=6.0, novelty_or_value=7.0, total=34.0),
        weighted_post_score=WeightedPostScore(post_type="REEL", score=p_score, normalized_score_0_50=p_score/2),
    )


def _sep(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


# ── build test posts ──────────────────────────────────────────────────────────

posts = [
    _make_post("post_1", "Morning grind 💪 #fitness #gym", save_rate=0.05, share_rate=0.03,
               profile_visit_rate=0.04, watch_through_rate=0.72, comment_rate=0.02,
               engagement_rate=0.08, cringe_score=15, production_level="high",
               hook_strength=0.82, technical_flaws=[], p_score=78.0, shareability=8.0),
    _make_post("post_2", "Meal prep Sunday 🥗", save_rate=0.07, share_rate=0.02,
               profile_visit_rate=0.03, watch_through_rate=0.65, comment_rate=0.03,
               engagement_rate=0.06, cringe_score=22, production_level="high",
               hook_strength=0.71, technical_flaws=["slight overexposure"], p_score=72.0, shareability=7.0),
    _make_post("post_3", "HIIT at home 🔥", save_rate=0.04, share_rate=0.04,
               profile_visit_rate=0.05, watch_through_rate=0.80, comment_rate=0.025,
               engagement_rate=0.09, cringe_score=8, production_level="medium",
               hook_strength=0.90, technical_flaws=["slight overexposure", "shaky camera"], p_score=81.0, shareability=9.0),
]


# ── Test 1: engagement signals ────────────────────────────────────────────────
_sep("TEST 1: compute_account_engagement_signals")
signals: AccountEngagementSignals = compute_account_engagement_signals(posts)
print(f"  avg_save_rate:          {signals.avg_save_rate}")
print(f"  avg_share_rate:         {signals.avg_share_rate}")
print(f"  avg_watch_through_rate: {signals.avg_watch_through_rate}")
print(f"  avg_profile_visit_rate: {signals.avg_profile_visit_rate}")
print(f"  audience_trust_index:   {signals.audience_trust_index}")
print(f"  virality_potential:     {signals.virality_potential}")
print(f"  consistency_score:      {signals.consistency_score}")

assert signals.avg_save_rate is not None, "avg_save_rate should not be None"
assert signals.avg_share_rate is not None, "avg_share_rate should not be None"
assert signals.audience_trust_index is not None, "audience_trust_index should not be None"
assert 0 <= signals.audience_trust_index <= 100, "audience_trust_index out of range"
assert signals.virality_potential is not None, "virality_potential should not be None"
assert 0 <= signals.virality_potential <= 100, "virality_potential out of range"
print("\n  ✅ engagement signals PASSED")


# ── Test 2: vision summary ────────────────────────────────────────────────────
_sep("TEST 2: compute_account_vision_summary")
vsummary: AccountVisionSummary = compute_account_vision_summary(posts)
print(f"  avg_cringe_score:       {vsummary.avg_cringe_score}")
print(f"  avg_hook_strength:      {vsummary.avg_hook_strength}")
print(f"  avg_production_level:   {vsummary.avg_production_level}")
print(f"  flagged_posts_count:    {vsummary.flagged_posts_count}")
print(f"  common_technical_flaws: {vsummary.common_technical_flaws}")

assert vsummary.avg_cringe_score is not None, "avg_cringe_score should not be None"
assert vsummary.avg_cringe_score == round((15 + 22 + 8) / 3, 1), f"cringe avg wrong: {vsummary.avg_cringe_score}"
assert vsummary.avg_hook_strength is not None, "avg_hook_strength should not be None"
assert vsummary.flagged_posts_count == 0, f"no posts should be flagged, got {vsummary.flagged_posts_count}"
assert "slight overexposure" in vsummary.common_technical_flaws, "expected 'slight overexposure' in flaws"
assert len(vsummary.common_technical_flaws) <= 5, "max 5 flaws"
print("\n  ✅ vision summary PASSED")


# ── Test 3: AccountHealthScore model with new fields ─────────────────────────
_sep("TEST 3: AccountHealthScore with new fields")
from backend.app.domain.account_models import AccountHealthScore, PillarScore, AccountHealthMetadata

ahs = AccountHealthScore(
    ahs_score=74.5,
    ahs_band="STRONG",
    engagement_signals=signals,
    vision_summary=vsummary,
)
dumped = ahs.model_dump(mode="python")
assert "engagement_signals" in dumped, "engagement_signals missing from dump"
assert "vision_summary" in dumped, "vision_summary missing from dump"
assert "creator_intelligence" in dumped, "creator_intelligence missing from dump"
print(f"  ahs_score:              {dumped['ahs_score']}")
print(f"  engagement_signals:     present ✓")
print(f"  vision_summary:         present ✓")
print(f"  creator_intelligence:   {dumped['creator_intelligence']}")
print("\n  ✅ AccountHealthScore model PASSED")


# ── Test 4: CreatorIntelligence (LLM call — live) ────────────────────────────
_sep("TEST 4: generate_creator_intelligence (LIVE LLM call)")
print("  Calling OpenAI... (may take up to 45s)")

async def _run_intel():
    return await generate_creator_intelligence(
        posts=posts,
        account_id="test_creator",
        username="fitnesscreator",
        bio="Daily fitness motivation, HIIT workouts, meal prep 💪",
        niche_tags=["fitness", "hiit", "mealprep", "gym"],
        creator_dominant_category="fitness",
        follower_count=85000,
    )

intel: CreatorIntelligence = asyncio.run(_run_intel())
print(f"\n  creator_persona:\n    {intel.creator_persona}")
print(f"\n  content_style_summary:\n    {intel.content_style_summary}")
print(f"\n  top_performing_themes:  {intel.top_performing_themes}")
print(f"\n  brand_fit.fit_categories: {intel.brand_fit.fit_categories}")
print(f"  brand_fit.red_flags:    {intel.brand_fit.red_flags}")

assert intel.creator_persona is not None, "creator_persona should not be None from LLM"
assert isinstance(intel.top_performing_themes, list), "top_performing_themes should be a list"
assert isinstance(intel.brand_fit.fit_categories, list), "fit_categories should be a list"
print("\n  ✅ CreatorIntelligence PASSED")


# ── Summary ───────────────────────────────────────────────────────────────────
_sep("ALL TESTS PASSED ✅")
