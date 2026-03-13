"""Run the full end-to-end smoke test inline (bypassing RQ worker).

Steps performed:
1. Load .env for API keys
2. Load fixture -> build seed posts
3. Analyze each post via the single-post pipeline (vision + LLM)
4. Run account-level analysis job function directly
5. Write results: job status + per-post sample to JSON files
"""
import os
import sys
import asyncio
import json
import traceback
from pathlib import Path

# ── Load .env BEFORE any backend imports ──────────────────────────
env_path = Path("backend/.env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

print(f"[smoke] GEMINI_API_KEY set: {bool(os.getenv('GEMINI_API_KEY'))}", flush=True)
print(f"[smoke] OPENAI_API_KEY set: {bool(os.getenv('OPENAI_API_KEY'))}", flush=True)

from backend.app.tools.enqueue_account_analysis_from_fixture import (
    _build_seed_post,
    _analyze_posts,
)
from backend.app.services.account_analysis_jobs import (
    run_account_analysis_job,
    initialize_job_status,
)
from backend.app.infra.redis_client import DEFAULT_REDIS_URL, get_redis


def main() -> None:
    # ── Flush stale Redis data ────────────────────────────────────
    r = get_redis()
    redis_url = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)
    host = None
    try:
        host = r.connection_pool.connection_kwargs.get("host")
    except Exception:
        host = None
    is_local = host in {"localhost", "127.0.0.1"} if isinstance(host, str) else (
        "localhost" in redis_url or "127.0.0.1" in redis_url
    )
    if not is_local:
        print(f"[smoke] FATAL: Refusing to flushdb on non-local Redis: {redis_url}", flush=True)
        sys.exit(1)
    r.flushdb()
    print("[smoke] Redis database flushed", flush=True)

    fixture_path = Path("fixtures/ig_dhirendra_raw.json")
    if not fixture_path.exists():
        print(f"[smoke] FATAL: Fixture not found at {fixture_path.resolve()}", flush=True)
        sys.exit(1)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    items = fixture.get("items")
    if not items:
        print("[smoke] FATAL: Fixture missing 'items' key or empty", flush=True)
        sys.exit(1)
    account_id = fixture.get("username", "fixture_account")

    # Step 1: Build seed posts
    seed_posts = [_build_seed_post(item, account_id=account_id) for item in items]
    print(f"[smoke] Built {len(seed_posts)} seed posts", flush=True)

    # Step 2: Analyze posts through single-post pipeline (vision + LLM)
    try:
        analyzed = asyncio.run(_analyze_posts(seed_posts, concurrency=1))
        print(f"[smoke] Analyzed {len(analyzed)} posts successfully", flush=True)
    except Exception:
        traceback.print_exc()
        print("[smoke] FATAL: Post analysis failed", flush=True)
        sys.exit(1)

    if not analyzed:
        print("[smoke] FATAL: No posts analyzed successfully", flush=True)
        sys.exit(1)

    # ── Save per-post data for verification ───────────────────────
    per_post_output = []
    for i, post in enumerate(analyzed):
        post_data = {
            "index": i,
            "media_id": post.media_id,
            "media_type": post.media_type,
            "caption_text_preview": (post.caption_text or "")[:80],
        }
        # Vision analysis
        if post.vision_analysis is not None:
            va = post.vision_analysis
            post_data["vision"] = va.model_dump(mode="python") if hasattr(va, "model_dump") else str(va)
        else:
            post_data["vision"] = None

        # S1 - Visual Quality
        if post.visual_quality_score is not None:
            vqs = post.visual_quality_score
            post_data["visual_quality_score"] = vqs.model_dump(mode="python") if hasattr(vqs, "model_dump") else str(vqs)
        else:
            post_data["visual_quality_score"] = None

        # S2 - Caption Effectiveness
        if post.caption_effectiveness_score is not None:
            ces = post.caption_effectiveness_score
            post_data["caption_effectiveness_score"] = (
                ces.model_dump(mode="python") if hasattr(ces, "model_dump") else str(ces)
            )
        else:
            post_data["caption_effectiveness_score"] = None

        # S3 - Content Clarity
        if post.content_clarity_score is not None:
            ccs = post.content_clarity_score
            post_data["content_clarity_score"] = (
                ccs.model_dump(mode="python") if hasattr(ccs, "model_dump") else str(ccs)
            )
        else:
            post_data["content_clarity_score"] = None

        # S5 - Engagement Potential
        if post.engagement_potential_score is not None:
            eps = post.engagement_potential_score
            post_data["engagement_potential_score"] = (
                eps.model_dump(mode="python") if hasattr(eps, "model_dump") else str(eps)
            )
        else:
            post_data["engagement_potential_score"] = None

        # Weighted Post Score
        if post.weighted_post_score is not None:
            wps = post.weighted_post_score
            post_data["weighted_post_score"] = (
                wps.model_dump(mode="python") if hasattr(wps, "model_dump") else str(wps)
            )
        else:
            post_data["weighted_post_score"] = None

        # Predicted engagement rate
        post_data["predicted_engagement_rate"] = post.predicted_engagement_rate
        post_data["predicted_engagement_rate_notes"] = list(post.predicted_engagement_rate_notes or [])

        per_post_output.append(post_data)

    Path("smoke_per_post.json").write_text(
        json.dumps(per_post_output, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"[smoke] Per-post data written to smoke_per_post.json", flush=True)

    # Step 3: Run account-level analysis job directly
    job_id = "smoke-test-v2"
    payload = {
        "job_id": job_id,
        "account_id": account_id,
        "post_limit": min(len(analyzed), 30),
        "posts": [p.model_dump(mode="python") for p in analyzed],
    }

    initialize_job_status(job_id)
    print(f"[smoke] Running account analysis job (job_id={job_id})...", flush=True)

    try:
        run_account_analysis_job(payload)
        print("[smoke] Job completed!", flush=True)
    except Exception:
        traceback.print_exc()
        print("[smoke] Job execution failed", flush=True)
        sys.exit(1)

    # ── Read and save final job status from Redis ─────────────────
    from backend.app.infra.redis_client import get_json
    status = get_json(f"account_analysis:job:{job_id}")
    if status:
        Path("smoke_final_status.json").write_text(
            json.dumps(status, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"[smoke] Final status: {status.get('status')}", flush=True)
        if status.get("result"):
            print(f"[smoke] AHS score: {status['result'].get('ahs_score')}", flush=True)
    else:
        print("[smoke] WARNING: No status found in Redis", flush=True)

    print("[smoke] ✅ Smoke test complete. Check smoke_final_status.json + smoke_per_post.json", flush=True)


if __name__ == "__main__":
    main()
