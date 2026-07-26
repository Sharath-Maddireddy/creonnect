# Creonnect — AI Analysis Pipeline: Architecture Reference

> **Last updated:** 2026-06-28  
> **Status:** ✅ All issues resolved — Phase 1 + Phase 2 complete

---

## Table of Contents

1. [What This Pipeline Does](#1-what-this-pipeline-does)
2. [Current Architecture](#2-current-architecture)
3. [Why ECS + Async Fan-out](#3-why-ecs--async-fan-out)
4. [Cost](#4-cost)
5. [All Changes Shipped](#5-all-changes-shipped)
6. [Issues Status](#6-issues-status)

---

## 1. What This Pipeline Does

```
Account submitted
       │
       ▼
  SQS Queue (account-analysis)
  maxReceiveCount=3 → DLQ on failure ✅
       │
       ▼
  run_account_analysis_job()
       │
       │  asyncio.gather() — all posts parallel ✅
       ├──► build_single_post_insights() [×30, Semaphore(8)]
       │         ├── S1: Vision        (Gemini — image or Gemini File API for reels)
       │         ├── S2: Caption       (deterministic ✅)
       │         ├── S3: Clarity       (LLM call)
       │         ├── S4: Audience      (deterministic ✅)
       │         ├── S5: Engagement    (deterministic)
       │         └── S6: Brand Safety  (deterministic)
       │
       ├──► analyze_account_health()
       ├──► calculate_creator_score()
       ├──► generate_creator_intelligence()  ← 1 LLM call per account
       ├──► upsert_creator()                 ← embedding
       └──► persist → Redis
```

### Key numbers

| | Before | After |
|---|---|---|
| LLM calls / account | ~151 | **~61** |
| Job time (30 posts) | 8–12 min | **~2–3 min** |
| Gemini cost / account | ~$0.030 | **~$0.018** |
| Workers needed at 500/day | 3–4 | **1 (auto-scales to 8)** |

---

## 2. Current Architecture

```
  FastAPI API (EC2 / ECS)
       │ SQS send_message
       ▼
  AWS SQS — account-analysis
  VisibilityTimeout: 420s  ✅
  maxReceiveCount: 3  ✅
  DLQ: account-analysis-dlq  ✅
       │ long-poll
       ▼
  SQS Worker (EC2 Spot)
  desiredCount: 2  |  min: 1  |  max: 8  ✅
  Scales on: ApproximateNumberOfMessagesVisible
    asyncio.gather([post_1 … post_30], Semaphore(8))  ✅
    GEMINI_USE_BATCH=true → text calls → Batch API  ✅
       │
       ▼
  Redis — job state, AI cache (24h TTL), dedup, rate limits
  PostgreSQL + pgvector — creator data, embeddings, job results
```

---

## 3. Why ECS + Async Fan-out

| Option | Reason rejected |
|---|---|
| **Lambda** | 15-min hard ceiling; reel jobs can exceed it; in-process cache breaks |
| **Celery** | Lateral move from RQ — same bottlenecks, more ops overhead |
| **Fargate on-demand** | 30–60s cold start; more expensive than Spot EC2 at 500+/day |
| **ECS + Async ✅** | Same infra, ~60 lines changed, 5× faster, no ceiling |

---

## 4. Cost

> Gemini API is 80–95% of the bill. Compute is secondary.

### 500 accounts/day — full journey

| Scenario | Gemini | Compute | DB | Redis | **Total** |
|---|---|---|---|---|---|
| Original (serial, LLM S2+S4) | $450 | $63 | $61 | $24 | **$601** |
| Phase 1 (parallel, deterministic S2+S4) | $270 | $16 | $61 | $24 | **$371** |
| Phase 2 + Batch API ✅ | **$135** | **$16** | **$61** | **$24** | **$236** |

### All scales — current baseline

| Scale | Gemini | Compute | DB | Redis | **Total** | Per analysis |
|---|---|---|---|---|---|---|
| 50 acc/day | $13.50 | $16 | $15 | $12 | **~$57** | ~$0.038 |
| 200 acc/day | $54 | $16 | $31 | $24 | **~$125** | ~$0.021 |
| **500 acc/day** | **$135** | **$16** | **$61** | **$24** | **~$236** | **~$0.016** |
| 2,000 acc/day | $540 | $47 | $123 | $49 | **~$759** | ~$0.013 |

### Remaining cost levers (if needed)

| Lever | Effort | Saving at 500/day |
|---|---|---|
| Reduce `post_limit` to 10 for first-time accounts | Low | -$45/mo |
| Skip S1 vision for text-only posts | Low | -$14/mo |
| EC2 Reserved Instances (1-year) for API | Zero code | ~-$5/mo |

### Infra reference pricing (ap-south-1, Spot)

| Component | Recommended | Monthly |
|---|---|---|
| EC2 worker | t3.large Spot (needs 4 GB+ for reel downloads) | $15.84 |
| Redis | ElastiCache cache.t3.small | $24.48 |
| PostgreSQL | RDS db.t3.small or Supabase Pro | $25–31 |
| SQS | — | < $0.05 |

> ⚠️ Use On-demand or Reserved for the API instance. Workers are safe on Spot — SQS redelivers on reclaim.

---

## 5. All Changes Shipped

### Phase 1 — Performance & Cost

| Change | File | Effect |
|---|---|---|
| Serial loop → `asyncio.gather()` + `Semaphore(8)` | `account_analysis_jobs.py` | 5× faster jobs |
| Removed `_GENAI_LOCK` | `ai_analysis_service.py` | Unblocked true concurrency |
| S2 → `compute_s2_caption_effectiveness()` | `post_insights_service.py` | -30 LLM calls/account |
| S4 → `compute_s4_audience_relevance()` | `post_insights_service.py` | -30 LLM calls/account |
| `GEMINI_USE_BATCH` flag + `_call_gemini_text_batch()` | `ai_analysis_service.py` | 50% off text calls |
| `VisibilityTimeout` 300s → 420s | `sqs_worker.py` | Reel jobs no longer time out |

### Phase 2 — Reliability & Scaling

| Change | File / Infra | Effect |
|---|---|---|
| Message deletion → `finally` block | `sqs_worker.py` | Poison pills can't retry forever |
| DLQ created for all 4 queues | `infra/scripts/setup_sqs_dlq.py` → AWS | Failed jobs captured, not lost |
| ECS auto-scaling wired to queue depth | `infra/scripts/setup_ecs_autoscaling.py` → AWS | 1–8 workers, scales automatically |
| `GEMINI_USE_BATCH=true` on worker | `.env` / ECS task definition | Batch API active for all background jobs |

> `GEMINI_USE_BATCH` applies to text-only (non-vision) Gemini calls. S1 vision always uses the synchronous SDK.

---

## 6. Issues Status

| # | Issue | Status |
|---|---|---|
| 1 | Serial post loop (8–12 min jobs) | ✅ Fixed — asyncio.gather |
| 2 | `_GENAI_LOCK` blocked concurrency | ✅ Fixed — lock removed |
| 3 | S2+S4 LLM calls — expensive | ✅ Fixed — deterministic |
| 4 | No Batch API for background jobs | ✅ Fixed — `GEMINI_USE_BATCH` |
| 5 | `VisibilityTimeout` too short | ✅ Fixed — 420s |
| 6 | Message deleted only on success | ✅ Fixed — `finally` block |
| 7 | No SQS Dead-Letter Queue | ✅ Fixed — DLQ on all 4 queues |
| 8 | Worker count not auto-scaled | ✅ Fixed — ECS scales 1→8 on queue depth |

---

*Maintained by the Creonnect backend team.*
