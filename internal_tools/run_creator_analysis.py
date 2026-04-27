"""Run full creator account analysis on synthetic_mid_creator and print all results."""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.getcwd())

from backend.app.ingestion.instagram_mapper import map_instagram_to_ai_inputs
from backend.app.analytics.account_health_engine import (
    compute_account_health_score,
    compute_account_engagement_signals,
    compute_account_vision_summary,
    compute_content_quality_breakdown,
)
from backend.app.services.account_ai_intelligence import generate_creator_intelligence
from backend.app.services.post_insights_service import _coerce_single_post_insights, build_single_post_insights
from backend.app.domain.post_models import DerivedMetrics
from backend.app.ai.schemas import CreatorPostAIInput
from backend.app.ai.niche import detect_creator_niche

SEP = "─" * 64

def fmt(v, pct=False, of10=False, of100=False):
    if v is None:
        return "N/A"
    if pct:
        return f"{v * 100:.2f}%"
    if of10:
        return f"{v:.1f}/10"
    if of100:
        return f"{v:.1f}/100"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)

def bar(value, max_val=100, width=30):
    if value is None:
        return "[" + "─" * width + "] N/A"
    filled = int((value / max_val) * width)
    filled = max(0, min(filled, width))
    return "[" + "█" * filled + "─" * (width - filled) + f"] {value:.1f}"


# ── Load synthetic data ───────────────────────────────────────────────────────
with open("backend/app/tests/synthetic_mid_profile.json") as f:
    raw_profile = json.load(f)
with open("backend/app/tests/synthetic_mid_media.json") as f:
    raw_media = json.load(f)

profile, posts = map_instagram_to_ai_inputs(raw_profile, raw_media)

print(f"\n{'═'*64}")
print(f"  CREONNECT — Creator Account Analysis")
print(f"  @{profile.username}  |  {profile.followers_count:,} followers")
print(f"{'═'*64}")

# ── Detect niche ──────────────────────────────────────────────────────────────
niche = detect_creator_niche(profile, posts)
print(f"\n🎯  NICHE DETECTION")
print(f"  Primary Niche:   {niche.get('primary_niche', 'Unknown')}")
print(f"  Top Hashtags:    {', '.join((niche.get('hashtags') or [])[:5])}")

# ── Build SinglePostInsights models ──────────────────────────────────────────
single_post_models = []
for post in posts:
    creator_post = CreatorPostAIInput(
        post_id=str(post.post_id or ""),
        creator_id=profile.username,
        platform="instagram",
        post_type="REEL" if str(post.post_type or "").upper() == "REEL" else "IMAGE",
        media_url=str(post.media_url or ""),
        thumbnail_url=str(post.thumbnail_url or ""),
        caption_text=str(post.caption_text or ""),
        hashtags=[str(h) for h in (post.hashtags or []) if isinstance(h, str)],
        likes=int(post.likes or 0),
        comments=int(post.comments or 0),
        views=int(post.views) if post.views is not None else None,
        audio_name=str(post.audio_name) if isinstance(post.audio_name, str) else None,
        posted_at=post.posted_at.isoformat() if post.posted_at else None,
    )
    spi = _coerce_single_post_insights(creator_post)
    followers = profile.followers_count or 1
    if post.views and post.views > 0:
        er = (post.likes + post.comments) / post.views
    else:
        er = (post.likes + post.comments) / followers
    spi.derived_metrics = DerivedMetrics(
        engagement_rate=round(er, 6),
        like_rate=round(post.likes / max(post.views or followers, 1), 6),
        comment_rate=round(post.comments / max(post.views or followers, 1), 6),
        engagements_total=post.likes + post.comments,
    )
    single_post_models.append(spi)

print(f"\n📦  Posts analyzed: {len(single_post_models)}")

# ── 1. Account Health Score ───────────────────────────────────────────────────
ahs = compute_account_health_score(
    posts=single_post_models,
    account_avg_engagement_rate=None,
    niche_avg_engagement_rate=None,
    follower_band="10k-100k",
)
print(f"\n{SEP}")
print(f"🏆  ACCOUNT HEALTH SCORE: {ahs.ahs_score:.1f}/100  [{ahs.ahs_band}]")
print(f"{SEP}")
for name, pillar in ahs.pillars.items():
    label = name.replace("_", " ").title()
    print(f"  {label:<26} {bar(pillar.score, 100, 20)}  [{pillar.band}]")

print(f"\n  ⚡ Key Drivers:")
for d in ahs.drivers[:3]:
    print(f"    • {d.label}: {d.explanation[:80]}")

print(f"\n  💡 Top Recommendations:")
for r in ahs.recommendations[:3]:
    print(f"    [{r.impact_level}] {r.text}")

# ── 2. Engagement Signals ─────────────────────────────────────────────────────
eng = compute_account_engagement_signals(single_post_models)
print(f"\n{SEP}")
print(f"📊  ENGAGEMENT SIGNALS")
print(f"{SEP}")
print(f"  Audience Trust Index   {bar(eng.audience_trust_index, 100, 20)}")
print(f"  Virality Potential     {bar(eng.virality_potential, 100, 20)}")
print(f"  Consistency Score      {bar(eng.consistency_score, 100, 20)}")
print(f"\n  Avg Save Rate:         {fmt(eng.avg_save_rate, pct=True)}")
print(f"  Avg Share Rate:        {fmt(eng.avg_share_rate, pct=True)}")
print(f"  Avg Watch-Through:     {fmt(eng.avg_watch_through_rate, pct=True)}")
print(f"  Avg Profile Visit Rate:{fmt(eng.avg_profile_visit_rate, pct=True)}")

# ── 3. Vision Summary ─────────────────────────────────────────────────────────
vis = compute_account_vision_summary(single_post_models)
print(f"\n{SEP}")
print(f"👁️   VISION SUMMARY")
print(f"{SEP}")
hook_pct = (eng.avg_save_rate or 0)  # fallback if no vision
print(f"  Avg Hook Strength:     {fmt(vis.avg_hook_strength)}")
print(f"  Avg Cringe Score:      {fmt(vis.avg_cringe_score)}/100 (lower = better)")
print(f"  Production Level:      {vis.avg_production_level or 'N/A'}")
print(f"  Flagged Posts:         {vis.flagged_posts_count}")
if vis.common_technical_flaws:
    print(f"  Technical Flaws:")
    for flaw in vis.common_technical_flaws:
        print(f"    ⚠️  {flaw}")
else:
    print(f"  Technical Flaws:       None detected")

# ── 4. Content Quality Breakdown ─────────────────────────────────────────────
cqb = compute_content_quality_breakdown(single_post_models)
print(f"\n{SEP}")
print(f"🎨  CONTENT QUALITY BREAKDOWN  (sub-scores)")
print(f"{SEP}")

for section, scores in cqb.items():
    label_map = {
        "visual_quality": "S1 Visual Quality",
        "caption": "S2 Caption Analysis",
        "content_clarity": "S3 Content Clarity",
        "engagement_potential": "S5 Engagement Potential",
    }
    max_val = 100 if section == "caption" else 10
    print(f"\n  {label_map.get(section, section)}:")
    for sub, val in scores.items():
        label = sub.replace("_", " ").title()
        b = bar(val, max_val, 18) if val is not None else "[──────────────────] N/A"
        print(f"    {label:<24} {b}")

# ── 5. AI Creator Intelligence ────────────────────────────────────────────────
print(f"\n{SEP}")
print(f"🤖  AI CREATOR INTELLIGENCE  (LLM call)")
print(f"{SEP}")
print("  Running AI analysis... ", end="", flush=True)

intel = asyncio.run(generate_creator_intelligence(
    posts=single_post_models,
    account_id=profile.username,
    username=profile.username,
    bio=getattr(profile, "biography", None),
    niche_tags=list(niche.get("hashtags", [])) if isinstance(niche.get("hashtags"), list) else [],
    creator_dominant_category=niche.get("primary_niche"),
    follower_count=profile.followers_count,
))
print("done ✅")

print(f"\n  👤 Creator Persona:")
print(f"     {intel.creator_persona or 'N/A'}")
print(f"\n  🎬 Content Style:")
print(f"     {intel.content_style_summary or 'N/A'}")
print(f"\n  🔥 Top Performing Themes:")
for theme in intel.top_performing_themes:
    print(f"     • {theme}")
print(f"\n  ✅ Brand Fit Categories:")
for cat in intel.brand_fit.fit_categories:
    print(f"     ✓ {cat}")
if intel.brand_fit.red_flags:
    print(f"\n  🚩 Red Flags:")
    for flag in intel.brand_fit.red_flags:
        print(f"     ✗ {flag}")

# ── 6. Top 3 vs Bottom 3 Posts ───────────────────────────────────────────────
print(f"\n{SEP}")
print(f"📈  POST PERFORMANCE LEADERBOARD")
print(f"{SEP}")
ranked = sorted(
    zip(posts, single_post_models),
    key=lambda x: x[1].weighted_post_score.score,
    reverse=True
)
print("  TOP 3 POSTS:")
for i, (post, spi) in enumerate(ranked[:3], 1):
    caption = (post.caption_text or "No caption")[:50]
    print(f"    #{i}  P={spi.weighted_post_score.score:.1f}  👍{post.likes:,}  💬{post.comments}  | {caption}...")

print("\n  BOTTOM 3 POSTS:")
for i, (post, spi) in enumerate(reversed(ranked[-3:]), 1):
    caption = (post.caption_text or "No caption")[:50]
    print(f"    #{i}  P={spi.weighted_post_score.score:.1f}  👍{post.likes:,}  💬{post.comments}  | {caption}...")

print(f"\n{'═'*64}")
print(f"  ANALYSIS COMPLETE ✅")
print(f"{'═'*64}\n")
