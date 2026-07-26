# Creator Trend Recommendation System — Architecture

> **Feature**: Given a creator's account, infer their niche and generate 3 hyper-personalized, trend-backed content recommendations they can act on immediately.

---

## Overview

The Creator Trend Recommendation system is a **3-stage LLM pipeline** that:
1. **Discovers** what niche the creator belongs to (from their posts, bio, username)
2. **Fetches** current global trends relevant to that niche
3. **Generates** 3 actionable content recommendations by cross-referencing the creator's strengths against those trends

Results are cached in Redis and persisted to Postgres so the next API call returns instantly.

---

## High-Level Flow

```
HTTP Request (GET/POST)
        │
        ▼
  trend_routes.py
  (FastAPI Router)
        │
        ├──► Redis Cache Check ──── HIT ──► Return TrendAnalysisResult
        │
        │ MISS
        ▼
  CreatorTrendService
  .get_trends_and_recommendations()
        │
        ├── Step 1: discover_creator_niche()       ◄── niche_discovery_engine.py
        │           (posts, bio, username → CreatorNiche)
        │
        ├── Step 2: fetch_global_trends()           ◄── global_trend_engine.py
        │           (CreatorNiche → List[GlobalTrend])
        │
        └── Step 3: generate_trend_recommendations() ◄── trend_recommendation_engine.py
                    (CreatorIntelligence + List[GlobalTrend] → List[TrendRecommendation])
                            │
                            ▼
                    TrendAnalysisResult
                            │
                    ┌───────┴────────┐
                    ▼               ▼
               Redis Cache       Postgres DB
               (24h TTL)         (creator_trend_results)
```

---

## Entry Points

### API Routes — `trend_routes.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/accounts/{account_id}/trends` | Return stored result from DB, or trigger refresh if none exists |
| `POST` | `/api/v1/accounts/{account_id}/trends/refresh` | Force recalculation — rate limited to 1 per 30 minutes |
| `GET` | `/api/v1/accounts/{account_id}/trends/job/{job_id}` | Poll status of a queued background job |

**Rate Limiting logic (`refresh_trends`):**
- Uses Redis incr with 1800s expiry: `rate_limit:trends_refresh:{account_id}`
- First call (`count == 1`): computed **synchronously** (fast path)
- Subsequent calls within 30 min (`count > 1`): enqueued as **RQ background job** and returns `{ status: "queued", job_id: "..." }`

---

## Stage 1 — Niche Discovery

**File:** `backend/app/analytics/niche_discovery_engine.py`

**Function:** `discover_creator_niche(posts, bio, username) → CreatorNiche`

### What it does
- Takes the creator's last **12 post captions**, bio text, and username
- Sends them to the LLM (acting as *Senior Creator Analyst*) with a strict TOON-only system prompt
- LLM outputs `primary_category`, `sub_niches`, `confidence_score`
- Parsed via the project's **TOON parser**, validated into a `CreatorNiche` Pydantic model

### Fallback
On any LLM or parse failure → returns `CreatorNiche(primary_category="General", sub_niches=[], confidence_score=0.1)`

### LLM Config
- `temperature=0.1` (deterministic — niche classification should be consistent)
- `max_tokens=300`

---

## Stage 2 — Global Trend Fetching

**File:** `backend/app/analytics/global_trend_engine.py`

**Function:** `fetch_global_trends(niche: CreatorNiche) → List[GlobalTrend]`

### What it does
- Takes the `CreatorNiche` (primary_category + sub_niches)
- Sends it to the LLM (acting as *Viral Trend Spotter*)
- LLM returns 3–5 hyper-current, rising trends tailored to that niche
- Each trend includes: `topic_name`, `trend_type`, `momentum`, `description`, `example_reference`
- Parsed and validated into `List[GlobalTrend]`

### Trend Types
| Type | Meaning |
|------|---------|
| `topic` | Subject matter trend |
| `format` | Video structure / editing style |
| `audio` | Sound or music trend |
| `hashtag` | Tag-driven trend |

### Momentum Values
| Value | Meaning |
|-------|---------|
| `rising` | Gaining attention — act now |
| `peaking` | At maximum visibility |
| `falling` | Losing traction |

### Fallback
On failure → returns `[GlobalTrend(topic_name="Evergreen Content", ...)]` so the pipeline always continues.

### LLM Config
- `temperature=0.4`
- `max_tokens=800`

---

## Stage 3 — Recommendation Generation

**File:** `backend/app/analytics/trend_recommendation_engine.py`

**Function:** `generate_trend_recommendations(creator_intelligence, trends) → List[TrendRecommendation]`

### What it does
- Takes the `CreatorIntelligence` (creator strengths, content style summary) + up to **8** global trends
- Sends them to the LLM (acting as *Creative Director*)
- LLM outputs exactly **3 `TrendRecommendation`** objects
- Each recommendation includes: `suggested_title`, `rationale`, `expected_impact`, `trend_reference`
- The `rationale` **must** explain WHY this trend fits the creator by referencing their strengths

### LLM Config
- `temperature=0.7` (higher — creative output benefits from some variability)
- `max_tokens=600`

### Fallback
On any error → returns `[]` (empty list, pipeline is resilient)

---

## Orchestration Service

**File:** `backend/app/services/creator_trend_service.py`

**Class:** `CreatorTrendService`

Chains the 3 stages in sequence:
```python
niche  = await discover_creator_niche(posts, bio, username)
trends = await fetch_global_trends(niche)
recs   = await generate_trend_recommendations(creator_intelligence, trends)
return TrendAnalysisResult(niche=niche, global_trends=trends, recommendations=recs)
```

Raises `RuntimeError("Creator trend orchestration failed")` on unexpected errors.

---

## Background Job (RQ)

**File:** `backend/app/services/trend_analysis_jobs.py`

**Function:** `run_trend_analysis(account_id: str) → dict`

Used when a refresh is rate-limited. Runs the same 3-stage pipeline synchronously inside an RQ worker:

```
RQ Worker
    │
    ├── load_draft_history_context(account_id)
    ├── discover_creator_niche(posts, bio, username)
    ├── fetch_global_trends(niche)
    ├── generate_trend_recommendations(creator_intelligence, trends)
    ├── TrendAnalysisCache.set(...)       ← Redis
    └── _upsert_trend_result(...)         ← Postgres
```

---

## Caching Layer

**File:** `backend/app/services/trend_cache.py`

**Class:** `TrendAnalysisCache`

| Property | Value |
|----------|-------|
| Backend | Redis |
| TTL | **24 hours** (`86400s`) |
| Key format | `trend_cache:{account_id}:{md5(sorted_post_ids)}` |
| Invalidation | Time-based (TTL) + Content-based (post set change = new cache key) |

**Sync + Async variants** both available (`get`/`set` and `aget`/`aset`).

Cache is checked **before** calling the LLM pipeline and **written** immediately after.

---

## Persistence Layer

**Table:** `creator_trend_results` (Postgres)

**ORM Model:** `CreatorTrendResult` in `backend/app/infra/models.py`

| Column | Type | Description |
|--------|------|-------------|
| `account_id` | PK `str` | Creator's account ID |
| `niche_json` | `JSONB` | Serialized `CreatorNiche` |
| `global_trends_json` | `JSONB` | Serialized `List[GlobalTrend]` |
| `recommendations_json` | `JSONB` | Serialized `List[TrendRecommendation]` |

Upsert logic: `session.get(CreatorTrendResult, account_id)` → update or insert.

---

## Domain Models

**File:** `backend/app/domain/trend_models.py`

```
CreatorNiche
├── primary_category: str          e.g. "Fitness"
├── sub_niches: list[str]          e.g. ["HIIT", "Home Workouts"]
└── confidence_score: float        0.0 – 1.0

GlobalTrend
├── topic_name: str                e.g. "90s Dance Revival"
├── trend_type: topic|format|audio|hashtag
├── momentum: rising|peaking|falling
├── description: str
└── example_reference: str | None

TrendRecommendation
├── suggested_title: str           e.g. "Morning Aesthetic Routine"
├── rationale: str                 WHY this fits the creator
├── expected_impact: str           e.g. "High engagement, discovery boost"
└── trend_reference: str | None    Links back to a GlobalTrend.topic_name

TrendAnalysisResult               ← Final aggregated output
├── niche: CreatorNiche
├── global_trends: list[GlobalTrend]
└── recommendations: list[TrendRecommendation]
```

---

## TOON Format (Internal LLM Protocol)

All three LLM engines use **TOON** (Token-Oriented Object Notation) — a YAML-like format without braces or quotes. This is the project's internal structured output format for LLM responses.

Example output the LLM is expected to return:
```
recommendations
  -
    suggested_title: The aesthetic morning routine
    rationale: Visuals match your style
    expected_impact: High engagement
    trend_reference: Morning Vlog
```

Parsing is handled by `backend.app.ai.toon.loads()` which converts TOON → Python dict → Pydantic model.

---

## End-to-End Request Lifecycle

```
Client
  │
  ├─ GET /api/v1/accounts/{id}/trends
  │       │
  │       ├── DB has result?  YES → return TrendAnalysisResult immediately
  │       │
  │       └── NO → falls through to refresh_trends()
  │
  └─ POST /api/v1/accounts/{id}/trends/refresh
          │
          ├── Redis rate check (1 per 30 min)
          │
          ├── load_draft_history_context(account_id)
          │
          ├── TrendAnalysisCache.get()  → HIT? return cached
          │
          ├── count == 1 (first call)?
          │       YES → Run synchronously via CreatorTrendService
          │               → Cache result (Redis)
          │               → Upsert result (Postgres)
          │               → Return TrendAnalysisResult
          │
          └── count > 1 (rate limited)?
                  YES → enqueue_trend_analysis_job(account_id) via RQ
                      → Return { status: "queued", job_id: "..." }
                      → Client polls GET /trends/job/{job_id}
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| 3-stage LLM pipeline (sequential) | Each stage needs the output of the previous one; no parallelism possible |
| TOON format for LLM output | Avoids JSON escaping issues, project-wide consistency |
| `temperature=0.1` for niche | Deterministic classification |
| `temperature=0.7` for recommendations | Creative output benefits from variety |
| Redis cache keyed on post content hash | Changing posts = stale analysis = force recompute |
| Fallback at every stage | Pipeline never fully breaks — always returns something usable |
| Sync execution first, RQ queue on rate-limit | Avoids blocking on first use, protects LLM API budget |
