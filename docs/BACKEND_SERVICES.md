# Backend Services Documentation

This document explains the key orchestrator services in `backend/app/services/` that coordinate business logic, data pipelines, and AI flows.

## Overview

Services are the **business logic layer** that sits between API routes and lower-level utilities (analytics, AI, DB). They orchestrate data ingestion, analytics computation, and integration with external APIs and ML models.

### Core Services

1. **dashboard_service.py** — Assembles complete creator dashboard with profile, posts, metrics, and growth recommendations.
2. **post_insights_service.py** — Single-post analysis pipeline: derived metrics, benchmarking, content scoring, optional AI analysis.
3. **ai_analysis_service.py** — Calls LLM and vision models for post scoring (S1–S6), caption analysis, cringe detection.
4. **snapshot_service.py** — Snapshot management (daily creator state summary).
5. **account_ai_intelligence.py** — Generates rich creator intelligence and insights from account data.
6. **account_analysis_service.py** — Orchestrates long-running account-level analysis jobs.

---

## dashboard_service.py

**Location:** `backend/app/services/dashboard_service.py`

### Purpose
Assembles a **complete creator dashboard** by orchestrating:
- Profile and post ingestion (Instagram API or synthetic demo data)
- Post-level analytics and insights
- Account health scoring
- Niche detection and growth scoring
- Time-series data for charts
- Authenticity analysis (real data only)
- Action plan generation via RAG + LLM

### Key Functions

#### `build_creator_dashboard(creator_id: str, access_token: str | None = None) -> dict`

**Inputs:**
- `creator_id` — username or user identifier for demo mode; ignored when access_token is provided.
- `access_token` — optional Instagram long-lived access token; when provided, fetches real Instagram data; otherwise uses synthetic demo.

**Process:**
1. Fetch or load synthetic profile + posts (Instagram API or demo).
2. Detect niche via `detect_creator_niche()`.
3. Compute growth score via `compute_growth_score()`.
4. Analyze all posts via `analyze_posts()` (deterministic metrics + insights).
5. Fetch follower snapshots from DB and compute momentum.
6. Calculate best posting hours via `get_best_posting_hours()`.
7. Retrieve knowledge chunks from RAG.
8. Generate action plan via `generate_action_plan()` (LLM + fallback).
9. Calculate authenticity score (real data only).
10. Assemble and return response dict.

**Returns:**
```json
{
  "summary": {
    "username": "...",
    "followers": 12500,
    "growth_score": 72,
    "niche": { "primary_niche": "fitness", ... },
    "momentum": { "momentum_label": "accelerating", ... },
    ...
  },
  "posts": [
    {
      "post_id": "...",
      "media_url": "...",
      "engagement_rate_by_views": 0.08,
      "insights": ["..."],
      ...
    }
  ],
  "charts": {
    "engagement_over_time": [...],
    "views_over_time": [...]
  },
  "authenticity_analysis": { "score": 82, "band": "high", ... },
  "action_plan": { "diagnosis": "...", "weekly_plan": [...], ... }
}
```

**Error handling:**
- Raises `ValueError` if creator is not found (demo mode name mismatch).
- Returns fallback authenticity_analysis when demo data is used.

---

#### `build_creator_analytics(creator_id: str, access_token: str | None = None) -> dict`

**Inputs:** Same as `build_creator_dashboard`.

**Process:**
1. Calls `build_creator_dashboard()` to get base payload.
2. Converts post data into `SinglePostInsights` models.
3. Computes account health scoring (S1–S4 pillars) via `compute_account_health_score()`.
4. Computes engagement signals via `compute_account_engagement_signals()`.
5. Computes vision summary via `compute_account_vision_summary()`.
6. Generates creator intelligence via `generate_creator_intelligence()` (async).
7. Builds content-type breakdown (REEL vs IMAGE stats).
8. Returns enriched payload with account health, signals, and creator intelligence.

**Returns:** Extended version of `build_creator_dashboard` response with:
```json
{
  "...dashboard fields...",
  "account_health": {
    "ahs_score": 68,
    "ahs_band": "good",
    "pillars": { ... },
    "drivers": [...],
    "recommendations": [...]
  },
  "engagement_signals": { ... },
  "vision_summary": { ... },
  "creator_intelligence": { ... },
  "content_type_breakdown": { "REEL": { "count": 10, ... }, ... }
}
```

### Data Flow

```
API Request (/api/creator/dashboard or /api/creator/analytics)
  ↓
build_creator_dashboard or build_creator_analytics
  ↓
[If access_token provided]
  → fetch_instagram_profile() + fetch_instagram_media() [async]
  → map_instagram_to_ai_inputs() → CreatorProfileAIInput, List[CreatorPostAIInput]
[Else]
  → load_synthetic() → demo profile/posts
  ↓
Detect niche, compute growth score, analyze posts
  ↓
Query FollowerSnapshot table from DB
  ↓
RAG retrieve() + generate_action_plan() [with LLM fallback]
  ↓
Assemble response JSON
  ↓
Return to client
```

### Key Dependencies
- `backend.app.ingestion.instagram_oauth` — OAuth and media fetching.
- `backend.app.demo.synthetic_loader` — Demo data when offline.
- `backend.app.analytics.*` — Health, engagement, vision summaries.
- `backend.app.ai.*` — Niche, growth, post insights, action plan.
- `backend.app.infra.database` — Access follower snapshots.
- `backend.app.services.account_ai_intelligence` — Creator intelligence generation.

---

## post_insights_service.py

**Location:** `backend/app/services/post_insights_service.py`

### Purpose
Deterministic **single-post analysis pipeline** that:
- Converts AI input schemas to domain models.
- Computes derived metrics (engagement rate, like rate, comment rate).
- Computes benchmark metrics (vs historical posts).
- Computes content score (weighted combination of derived + benchmark).
- Optionally runs AI analysis (LLM calls, vision scoring).

### Key Functions

#### `build_single_post_insights(target_post, historical_posts, run_ai=False, run_advanced_caption_ai=False, run_advanced_audience_ai=False) -> SinglePostInsightsResponse`

**Inputs:**
- `target_post` — `SinglePostInsights | CreatorPostAIInput` — the post to analyze.
- `historical_posts` — list of previous posts for benchmarking.
- `run_ai` — if True, calls `analyze_single_post_ai()` for LLM/vision scoring.
- `run_advanced_caption_ai`, `run_advanced_audience_ai` — additional AI flags.

**Process:**
1. Coerce inputs into `SinglePostInsights` model via `_coerce_single_post_insights()`.
2. Filter out the target from historical (avoid self-comparison).
3. Compute derived metrics via `compute_derived_metrics()`:
   - Engagement rate = (likes + comments) / views
   - Like rate, comment rate, total interactions
4. Compute benchmark metrics via `compute_benchmark_metrics()`:
   - Compare against historical posts and niche/follower band.
5. Compute content score via `compute_content_score()`:
   - Weighted blend of derived + benchmark metrics.
6. [Optional] Run AI analysis via `analyze_single_post_ai()`:
   - Calls LLM for caption, audience relevance, growth prediction.
   - Calls vision models if enabled (Gemini).
   - Returns structured S1–S6 scores, summary, drivers, recommendations.

**Returns:**
```python
{
  "post": SinglePostInsights,        # fully populated post model
  "content_score": dict,             # aggregated score breakdown
  "ai_analysis": dict | None         # LLM/vision results (if run_ai=True)
}
```

### Example Derived Metrics Computation

```python
engagement_rate = (likes + comments) / views if views > 0 else None
like_rate = (likes / views) * 100 if views > 0 else None
comment_rate = (comments / views) * 100 if views > 0 else None
relative_performance = engagement_rate / creator_avg_engagement_rate
```

### Key Dependencies
- `backend.app.analytics.derived_metrics` — Metric computation.
- `backend.app.analytics.benchmark_engine` — Benchmarking.
- `backend.app.analytics.content_score` — Content scoring.
- `backend.app.services.ai_analysis_service` — Optional AI analysis.

### Usage (from API)

```python
# From post_analysis_routes.py
pipeline_result = await build_single_post_insights(
    target_post=creator_post,
    historical_posts=[],
    run_ai=True,
    run_advanced_caption_ai=True,
)
post = pipeline_result["post"]
ai_analysis = pipeline_result.get("ai_analysis")
```

---

## ai_analysis_service.py

**Location:** `backend/app/services/ai_analysis_service.py` (implied; may be separate files)

### Purpose
Calls **LLM and vision models** to score posts and provide AI-driven insights.

### Process Overview

**S1–S6 Scoring Pipeline:**
- **S1** (Visual Quality) — Composition, lighting, subject clarity, aesthetic (image/frame analysis).
- **S2** (Caption Effectiveness) — Hook score, length, hashtag quality, CTA strength.
- **S3** (Content Clarity) — Message singularity, context clarity, caption–visual alignment.
- **S4** (Audience Relevance) — Topic affinity with creator niche.
- **S5** (Engagement Potential) — Predicted engagement rate based on historical performance.
- **S6** (Brand Safety) — Cringe score, adult content, production quality (from vision).

**Fallback Logic:**
- If vision API fails or is disabled, uses heuristics.
- If LLM call fails, returns deterministic defaults.
- Logs warnings for degraded behavior.

### Key Dependencies
- `backend.app.ai.llm_client` — LLMClient for calling OpenAI.
- `backend.app.ai.prompts` — TOON/JSON prompt templates.
- Vision APIs (Gemini/OpenAI vision) — optional, gated by environment variable.

---

## account_ai_intelligence.py

**Location:** `backend/app/services/account_ai_intelligence.py`

### Purpose
Generates **rich creator intelligence** from account data (posts, niche, follower count):
- Content gaps and opportunities
- Audience composition insights
- Growth recommendations
- Trend alignment

### Key Functions

#### `generate_creator_intelligence(posts, account_id, username, bio, niche_tags, creator_dominant_category, follower_count) -> CreatorIntelligence`

**Inputs:**
- `posts` — list of `SinglePostInsights` objects.
- `account_id`, `username`, `bio` — profile metadata.
- `niche_tags` — tags from niche detection.
- `creator_dominant_category` — primary niche (e.g. "fitness").
- `follower_count` — account follower count.

**Returns:** `CreatorIntelligence` object with insights on content strategy, audience, and opportunities.

---

## snapshot_service.py

**Location:** `backend/app/services/snapshot_service.py`

### Purpose
Manages **daily snapshots** — point-in-time summaries of creator account state.

### Key Functions

#### `build_creator_snapshot_service(creator_id: str) -> dict`

Retrieves or builds the latest snapshot for a creator including:
- Follower count at snapshot time
- Engagement metrics
- Growth score
- Top posts of the day

**Returns:**
```json
{
  "creator_id": "...",
  "snapshot_date": "2026-04-30",
  "followers": 12500,
  "growth_score": 72,
  "top_posts": [...]
}
```

---

## account_analysis_service.py

**Location:** `backend/app/services/account_analysis_service.py`

### Purpose
Orchestrates **long-running account analysis** — typically as background jobs via RQ.

### Typical Workflow
1. User requests account analysis via API endpoint.
2. Job is queued to RQ (backed by Redis).
3. Worker picks up job and calls account analysis service.
4. Service computes all scores, insights, and stores in DB or Redis.
5. Frontend polls for job status and displays results.

### Key Dependencies
- `backend.app.infra.rq_queue` — RQ job queueing.
- All services above (dashboard, post insights, AI analysis).

---

## Common Patterns

### Error Handling
- Services catch exceptions and either log+fallback or raise `HTTPException` (via FastAPI routes).
- AI calls have graceful degradation (fallback to deterministic rules).
- DB queries handle connection errors and return empty/null when appropriate.

### Async/Await
- Many services use `asyncio.run()` internally to bridge async calls (e.g., `fetch_instagram_media()`) from sync FastAPI routes.
- This is acceptable for lightweight orchestration; compute-heavy tasks should be pushed to RQ workers.

### Caching
- Snapshots and post insights are cached in Redis (see `post_snapshot_store.py` and `post_analysis_routes.py`).
- RAG chunks are cached to disk (`.rag_cache/`).
- Database queries use SQLAlchemy session pooling.

---

## Testing Services

Services are tested by mocking:
- Instagram API responses
- LLM/vision API responses
- DB session
- Redis

Existing tests are in `backend/app/tests/` — see `conftest.py` for fixtures.

---

## Adding a New Service

1. Create a new file in `backend/app/services/` named `my_service.py`.
2. Import dependencies (DB, Redis, AI, infra).
3. Define orchestration functions (avoid side effects if possible).
4. Log progress and errors via `backend.app.utils.logger.logger`.
5. Raise `HTTPException` or application-level exceptions for error cases.
6. Write unit tests in `backend/app/tests/` using fixtures from `conftest.py`.
7. Document the service in this file.

---

## Summary

| Service | Purpose | Entrypoint | Key Output |
|---------|---------|-----------|-----------|
| dashboard_service | Creator dashboard + analytics | `build_creator_dashboard`, `build_creator_analytics` | Complete dashboard JSON |
| post_insights_service | Single-post deterministic analysis | `build_single_post_insights` | `SinglePostInsights` + scores |
| ai_analysis_service | LLM/vision scoring | `analyze_single_post_ai` | S1–S6 structured scores |
| account_ai_intelligence | Creator intelligence generation | `generate_creator_intelligence` | `CreatorIntelligence` object |
| snapshot_service | Daily snapshots | `build_creator_snapshot_service` | Snapshot dict |
| account_analysis_service | Long-running account analysis | Various job handlers | Job results in DB/Redis |

