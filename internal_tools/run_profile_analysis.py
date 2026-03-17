"""Standalone profile analysis runner — no Redis or RQ required.

Usage:
    python internal_tools/run_profile_analysis.py --fixture internal_tools/fixtures/ig_ig_dhirendra_raw.json
    python internal_tools/run_profile_analysis.py --fixture internal_tools/fixtures/ig_dhirendra_raw.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]

# Load env vars (GEMINI_API_KEY, OPENAI_API_KEY, etc.)
load_dotenv(REPO_ROOT / "backend" / ".env", override=False)
load_dotenv(override=False)

from backend.app.domain.post_models import BenchmarkMetrics, CoreMetrics, DerivedMetrics, SinglePostInsights
from backend.app.services.account_analysis_service import analyze_account_health
from backend.app.services.post_insights_service import build_single_post_insights
from backend.app.tools.fixture_to_creator_input import build_creator_post_ai_input_from_fixture


def _safe_int_or_none(value: Any) -> int | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_seed_post(fixture_item: dict[str, Any], account_id: str) -> SinglePostInsights:
    creator_post = build_creator_post_ai_input_from_fixture(fixture_item)
    view_count = _safe_int_or_none(fixture_item.get("view_count"))
    like_count = _safe_int_or_none(fixture_item.get("like_count"))
    comment_count = _safe_int_or_none(fixture_item.get("comment_count"))

    core_metrics = CoreMetrics(
        reach=view_count,
        impressions=view_count,
        likes=like_count,
        comments=comment_count,
        shares=None,
        saves=None,
        profile_visits=None,
        website_taps=None,
        source_engagement_rate=None,
    )

    return SinglePostInsights(
        account_id=account_id,
        media_id=creator_post.post_id,
        media_url=creator_post.media_url or None,
        media_type=creator_post.post_type,
        caption_text=creator_post.caption_text,
        post_category=None,
        creator_dominant_category=None,
        extracted_brand_mentions=[],
        safety_extra_flags={},
        follower_count=_safe_int_or_none(fixture_item.get("follower_count")),
        published_at=creator_post.posted_at,
        core_metrics=core_metrics,
        derived_metrics=DerivedMetrics(),
        benchmark_metrics=BenchmarkMetrics(),
    )


async def _run_post_analysis(post: SinglePostInsights, all_posts: list[SinglePostInsights]) -> SinglePostInsights:
    historical = [p for p in all_posts if p.media_id != post.media_id]
    result = await build_single_post_insights(
        target_post=post,
        historical_posts=historical,
        run_ai=True,
    )
    return result["post"]


async def _analyze_all_posts(posts: list[SinglePostInsights], concurrency: int) -> list[SinglePostInsights]:
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 3)))
    results: list[SinglePostInsights] = []

    async def _run_one(post: SinglePostInsights) -> SinglePostInsights | None:
        async with semaphore:
            try:
                return await _run_post_analysis(post, posts)
            except Exception as exc:
                print(f"  [WARN] Failed post {post.media_id}: {exc}")
                return None

    tasks = [asyncio.create_task(_run_one(p)) for p in posts]
    for i, task in enumerate(asyncio.as_completed(tasks), start=1):
        result = await task
        if result is not None:
            results.append(result)
        print(f"  [{i}/{len(posts)}] posts analyzed...", flush=True)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run profile analysis from fixture, no Redis needed.")
    parser.add_argument(
        "--fixture",
        required=True,
        help="Path to fixture JSON (e.g. internal_tools/fixtures/ig_ig_dhirendra_raw.json)",
    )
    parser.add_argument("--account-id", default=None, help="Override account_id (defaults to 'username' in fixture)")
    parser.add_argument("--concurrency", type=int, default=2, help="Max concurrent AI post analyses (max 3)")
    parser.add_argument("--out", default=None, help="Output JSON path for results (default: <fixture_stem>_result.json)")
    args = parser.parse_args()

    fixture_path = Path(args.fixture)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    items = fixture.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Fixture must have a non-empty 'items' list.")

    account_id = (args.account_id or fixture.get("username") or "fixture_account").strip()
    out_path = Path(args.out) if args.out else fixture_path.parent / f"{fixture_path.stem}_result.json"

    print(f"=== Profile Analysis: {account_id} ===")
    print(f"Fixture   : {fixture_path} ({len(items)} posts)")
    print(f"Output    : {out_path}")
    gemini_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    print(f"Gemini API: {'✓ set' if gemini_key else '✗ NOT SET — vision disabled'}")
    print(f"OpenAI API: {'✓ set' if openai_key else '✗ NOT SET'}")
    print()

    print(f"Step 1/3: Building seed posts...")
    seed_posts = [_build_seed_post(item, account_id=account_id) for item in items]
    print(f"  → {len(seed_posts)} seed posts built")

    print(f"Step 2/3: Running per-post AI analysis (concurrency={min(args.concurrency, 3)})...")
    analyzed_posts = asyncio.run(_analyze_all_posts(seed_posts, concurrency=args.concurrency))
    print(f"  → {len(analyzed_posts)} / {len(seed_posts)} posts analyzed successfully")

    if not analyzed_posts:
        raise RuntimeError("No posts were analyzed. Check API keys and rerun.")

    print(f"Step 3/3: Computing account health score...")
    health = analyze_account_health(posts=analyzed_posts, use_cache=False)
    result_payload = health.model_dump(mode="python")

    # Add a posts summary
    posts_summary = []
    for post in analyzed_posts:
        posts_summary.append({
            "post_id": post.media_id,
            "post_type": post.media_type,
            "caption_preview": (post.caption_text or "")[:120],
            "scores": {
                "S1_visual": post.visual_quality_score.total if post.visual_quality_score else None,
                "S2_caption": post.caption_effectiveness_score.total_0_50 if post.caption_effectiveness_score else None,
                "S3_clarity": post.content_clarity_score.total if post.content_clarity_score else None,
                "S4_relevance": post.audience_relevance_score.total_0_50 if post.audience_relevance_score else None,
                "S5_engagement": post.engagement_potential_score.total if post.engagement_potential_score else None,
                "S6_safety": post.brand_safety_score.total_0_50 if post.brand_safety_score else None,
                "P_score": post.weighted_post_score.score if post.weighted_post_score else None,
                "predicted_er": post.predicted_engagement_rate,
            }
        })
    result_payload["posts_summary"] = posts_summary
    result_payload["account_id"] = account_id
    result_payload["posts_analyzed"] = len(analyzed_posts)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result_payload, f, indent=2, ensure_ascii=True, default=str)

    print(f"\n✓ Done! Results written to: {out_path}")

    # Print top-level summary
    print("\n=== ACCOUNT HEALTH SUMMARY ===")
    overall = result_payload.get("overall_score")
    if overall is not None:
        print(f"  Overall Health Score : {overall}")
    tier = result_payload.get("tier")
    if tier:
        print(f"  Tier                 : {tier}")
    for k, v in result_payload.items():
        if k.startswith("score_") or k in ("consistency_score", "engagement_health_score", "content_quality_score"):
            print(f"  {k:<30}: {v}")
    print()


if __name__ == "__main__":
    main()
