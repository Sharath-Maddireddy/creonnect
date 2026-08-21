"""Smoke-test the brand tool-calling system against the live Supabase creator pool.

Exercises:
  1. ToolOrchestrator -- each tool dispatched directly against real DB data
  2. brand_chat_discover -- full agentic loop with live LLM + real DB
  3. Results written to internal_tools/artifacts/tool_calling_smoke_results.json

Requires:
  - backend/.env with DATABASE_URL (Supabase) and OPENAI_API_KEY
  - Creators already seeded via seed_supabase_creators.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
sys.path.insert(0, str(REPO_ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / "backend" / ".env", override=True)

from backend.app.services.creator_pool_service import (
    get_all_creators,
    query_creator_pool,
    find_lookalikes,
)
from backend.app.services.tool_orchestrator import ToolOrchestrator
from backend.app.utils.logger import logger


# ── Pretty printers ─────────────────────────────────────────────
def _header(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def _tool_result(response, indent: int = 2) -> None:
    prefix = " " * indent
    status = "✅ SUCCESS" if response.success else "❌ FAILED"
    print(f"{prefix}{status}  tool={response.tool}  message={response.message}")
    if response.meta:
        lat = response.meta.get("latency_ms", 0)
        count = response.meta.get("result_count", "?")
        print(f"{prefix}  latency={lat:.0f}ms  result_count={count}")
    if response.ui:
        print(f"{prefix}  ui={response.ui}")
    if response.success and response.data:
        if isinstance(response.data, list):
            print(f"{prefix}  returned {len(response.data)} item(s)")
            for item in response.data[:3]:
                uname = item.get("username", item.get("account_id", "?"))
                fc = item.get("follower_count", "?")
                cat = item.get("creator_dominant_category", "?")
                print(f"{prefix}    @{uname} | {cat} | {fc:,} followers" if isinstance(fc, int) else f"{prefix}    @{uname} | {cat}")
            if len(response.data) > 3:
                print(f"{prefix}    ... and {len(response.data) - 3} more")
        elif isinstance(response.data, dict):
            # Print select keys
            for key in ("account_id", "total_match_score", "match_band", "question", "min_cost_usd", "max_cost_usd", "draft_message"):
                if key in response.data:
                    val = response.data[key]
                    if key == "draft_message":
                        val = val[:120] + "..." if len(str(val)) > 120 else val
                    print(f"{prefix}    {key}: {val}")


# ── Phase 1: Direct orchestrator tool tests ─────────────────────
def run_orchestrator_tests() -> list[dict]:
    """Call each tool via ToolOrchestrator against real DB. Returns audit list."""
    _header("PHASE 1: Tool Orchestrator — Direct Dispatch Against Supabase")

    orchestrator = ToolOrchestrator()
    results = []

    # Pre-flight: count creators
    all_creators = get_all_creators()
    print(f"\n  Pool size: {len(all_creators)} creators with embeddings")
    if not all_creators:
        print("  ⚠ No creators in pool! Run seed_supabase_creators.py first.")
        return results

    # Pick a known creator for targeted tests
    sample = next((c for c in all_creators if c.get("creator_dominant_category") == "fitness"), all_creators[0])
    sample_id = sample["account_id"]
    sample_uname = sample.get("username", "?")
    print(f"  Sample creator for tests: @{sample_uname} (id={sample_id})")

    # ── Test 1: search_creator_pool ──
    print(f"\n  [1/6] search_creator_pool (niche=fitness, limit=5)")
    r = orchestrator.execute_tool("search_creator_pool", {"niche": "fitness", "min_followers": 10000, "limit": 5})
    _tool_result(r)
    results.append({"test": "search_creator_pool", "success": r.success, "result_count": len(r.data) if isinstance(r.data, list) else 0})

    # ── Test 2: find_lookalike_creators ──
    print(f"\n  [2/6] find_lookalike_creators (account_id={sample_id})")
    r = orchestrator.execute_tool("find_lookalike_creators", {"account_id": sample_id, "limit": 3})
    _tool_result(r)
    results.append({"test": "find_lookalike_creators", "success": r.success, "result_count": len(r.data) if isinstance(r.data, list) else 0})

    # ── Test 3: score_creator_brand_fit ──
    print(f"\n  [3/6] score_creator_brand_fit (account_id={sample_id}, niche=fitness)")
    r = orchestrator.execute_tool("score_creator_brand_fit", {"account_id": sample_id, "brand_niche": "fitness", "min_followers": 5000})
    _tool_result(r)
    results.append({"test": "score_creator_brand_fit", "success": r.success, "score": r.data.get("total_match_score") if isinstance(r.data, dict) else None})

    # ── Test 4: get_creator_analysis ──
    print(f"\n  [4/6] get_creator_analysis (account_id={sample_id})")
    r = orchestrator.execute_tool("get_creator_analysis", {"account_id": sample_id})
    _tool_result(r)
    results.append({"test": "get_creator_analysis", "success": r.success, "has_data": r.data is not None})

    # ── Test 5: ask_brand_clarification ──
    print(f"\n  [5/6] ask_brand_clarification")
    r = orchestrator.execute_tool("ask_brand_clarification", {"question": "What follower range are you targeting?", "suggested_options": ["Nano (1k-10k)", "Micro (10k-100k)", "Macro (100k+)"]})
    _tool_result(r)
    results.append({"test": "ask_brand_clarification", "success": r.success})

    # ── Test 6: estimate_campaign_cost ──
    print(f"\n  [6/6] estimate_campaign_cost (account_id={sample_id}, REEL)")
    r = orchestrator.execute_tool("estimate_campaign_cost", {"account_id": sample_id, "deliverable_type": "REEL", "deliverable_count": 2})
    _tool_result(r)
    results.append({"test": "estimate_campaign_cost", "success": r.success, "cost_range": f"${r.data.get('min_cost_usd',0):.0f}-${r.data.get('max_cost_usd',0):.0f}" if isinstance(r.data, dict) else None})

    return results


# ── Phase 2: Full agentic chat loop with live LLM ──────────────
def run_chat_loop_tests() -> list[dict]:
    """Run brand briefs through the full tool-calling chat loop."""
    _header("PHASE 2: Agentic Chat Loop — Live LLM + Supabase")

    if not os.getenv("OPENAI_API_KEY"):
        print("  ⚠ OPENAI_API_KEY not set — skipping live chat loop tests.")
        return []

    from backend.app.services.brand_chat_service import brand_chat_discover

    prompts = [
        {
            "prompt": "Find me fitness creators with over 50k followers who have good engagement. I need them for a protein supplement launch.",
            "brand_name": "FitFuel",
            "label": "Fitness creator search (filter-based)",
        },
        {
            "prompt": "I need fashion and lifestyle creators with at least 100k followers. Brand safety is very important — no adult content.",
            "brand_name": "LuxeStyle",
            "label": "Fashion + safety filter",
        },
        {
            "prompt": "Find travel creators and then score the top result against my brand. I want someone who posts Reels.",
            "brand_name": "Wanderlust Co",
            "label": "Multi-tool: search + score",
        },
    ]

    results = []
    for i, test in enumerate(prompts, 1):
        print(f"\n  [{i}/{len(prompts)}] {test['label']}")
        print(f"  Prompt: \"{test['prompt'][:80]}...\"")
        print(f"  Brand: {test['brand_name']}")
        print(f"  Calling brand_chat_discover()...")

        t0 = time.perf_counter()
        try:
            response = brand_chat_discover(test["prompt"], test.get("brand_name"))
            elapsed = (time.perf_counter() - t0) * 1000

            print(f"\n  ✅ Completed in {elapsed:.0f}ms (service reported {response.total_latency_ms:.0f}ms)")
            print(f"  Tool calls made: {len(response.tool_calls_made)}")
            for tc in response.tool_calls_made:
                args_preview = json.dumps(tc.get("args", {}), default=str)
                if len(args_preview) > 80:
                    args_preview = args_preview[:80] + "..."
                print(f"    → {tc['name']}({args_preview}) [{tc.get('latency_ms',0):.0f}ms]")

            print(f"  Results returned: {len(response.results)} creator(s)")
            for cr in response.results[:3]:
                uname = cr.get("username", cr.get("account_id", "?"))
                cat = cr.get("creator_dominant_category", "?")
                fc = cr.get("follower_count", 0)
                score = cr.get("total_match_score")
                score_str = f" | score={score:.1f}" if score else ""
                print(f"    @{uname} | {cat} | {fc:,} followers{score_str}" if isinstance(fc, int) else f"    @{uname} | {cat}{score_str}")

            if response.clarification:
                print(f"  Clarification: {response.clarification.get('question', '?')}")

            print(f"\n  AI Response (preview):")
            preview = response.final_response[:300]
            for line in preview.split("\n"):
                print(f"    {line}")
            if len(response.final_response) > 300:
                print(f"    ... ({len(response.final_response)} chars total)")

            results.append({
                "label": test["label"],
                "success": True,
                "tool_calls": [tc["name"] for tc in response.tool_calls_made],
                "num_results": len(response.results),
                "latency_ms": round(elapsed),
                "final_response_preview": response.final_response[:200],
            })

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            print(f"\n  ❌ FAILED after {elapsed:.0f}ms: {exc}")
            logger.exception("Chat loop test failed")
            results.append({
                "label": test["label"],
                "success": False,
                "error": str(exc),
                "latency_ms": round(elapsed),
            })

    return results


# ── Main ────────────────────────────────────────────────────────
def main() -> None:
    print("\n" + "#" * 70)
    print("  CREONNECT TOOL-CALLING SMOKE TEST -- LIVE SUPABASE DATA")
    print("#" * 70)

    orchestrator_results = run_orchestrator_tests()
    chat_results = run_chat_loop_tests()

    # ── Summary ──
    _header("SUMMARY")
    all_tests = orchestrator_results + chat_results
    passed = sum(1 for t in all_tests if t.get("success"))
    failed = sum(1 for t in all_tests if not t.get("success"))
    print(f"  Total: {len(all_tests)}  |  ✅ Passed: {passed}  |  ❌ Failed: {failed}")
    for t in all_tests:
        icon = "✅" if t.get("success") else "❌"
        label = t.get("test") or t.get("label", "?")
        extra = ""
        if "score" in t and t["score"] is not None:
            extra = f" (score={t['score']:.1f})"
        if "cost_range" in t and t["cost_range"]:
            extra = f" ({t['cost_range']})"
        if "num_results" in t:
            extra = f" ({t['num_results']} creators, {t.get('latency_ms',0)}ms)"
        if "tool_calls" in t:
            extra += f" tools=[{', '.join(t['tool_calls'])}]"
        print(f"    {icon} {label}{extra}")

    # ── Write artifact ──
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = ARTIFACTS_DIR / "tool_calling_smoke_results.json"
    output_path.write_text(
        json.dumps(
            {
                "orchestrator_tests": orchestrator_results,
                "chat_loop_tests": chat_results,
                "summary": {"total": len(all_tests), "passed": passed, "failed": failed},
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n  Results saved to {output_path}")
    print()


if __name__ == "__main__":
    main()
