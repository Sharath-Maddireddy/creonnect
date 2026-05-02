# AI and Analytics Pipelines Documentation

This document explains the AI modules, analytics computations, and data transformation pipelines in `backend/app/ai/` and `backend/app/analytics/`.

## Overview

**AI Layer (`backend/app/ai/`):**
- Low-level AI utilities: LLM client, RAG, prompts, schema definitions.
- Deterministic and learned analytics: post insights, niche detection, growth scoring.
- Vision payload helpers: cringe/brand-safety analysis.

**Analytics Layer (`backend/app/analytics/`):**
- Deterministic metrics: derived metrics (engagement rate, like rate), benchmarking, content scoring.
- Account-level aggregations: account health, engagement signals, vision summary.

---

## AI Layer (backend/app/ai/)

### schemas.py — AI Input Models

Defines **pydantic input schemas** for AI functions:

#### `CreatorProfileAIInput`
Represents a creator's profile and aggregated metrics:
```python
{
  "creator_id": str,
  "username": str,
  "platform": str,  # "instagram"
  "bio_text": str,
  "followers_count": int,
  "following_count": int,
  "total_posts": int,
  "avg_likes": float,
  "avg_comments": float,
  "avg_views": float | None,
  "posts_per_week": float,
  "historical_engagement": {
    "avg_likes": float,
    "avg_comments": float,
    "avg_views": float | None,
    "avg_engagement_rate_by_views": float
  },
  "profile_last_updated": datetime
}
```

#### `CreatorPostAIInput`
Represents a single post with media and metrics:
```python
{
  "post_id": str,
  "creator_id": str,
  "platform": str,  # "instagram"
  "post_type": "IMAGE" | "REEL",
  "media_url": str,
  "thumbnail_url": str,
  "caption_text": str,
  "hashtags": list[str],
  "likes": int,
  "comments": int,
  "views": int | None,
  "audio_name": str | None,
  "posted_at": datetime | None
}
```

---

### post_insights.py — Deterministic Post Metrics

Computes **human-readable insights and basic metrics** for a post without LLM calls.

#### Key Functions

**`analyze_post(post: CreatorPostAIInput, creator_profile: CreatorProfileAIInput) -> dict`**

Computes:
- `total_interactions` = likes + comments
- `engagement_rate_by_views` = interactions / views (PRIMARY metric for Instagram 2025+)
- `like_rate` = (likes / views) * 100
- `comment_rate` = (comments / views) * 100
- `relative_performance` = post engagement rate / creator average
- `caption_context_present` — Boolean, caption has >= 3 words
- `cta_present` — Boolean, caption contains CTA keywords (comment, share, save, follow, etc.)
- `insights` — List of human-readable observations (e.g., "Excellent engagement rate...", "No CTA detected...")

**Returns:**
```python
{
  "post_id": "...",
  "total_interactions": 450,
  "engagement_rate_by_views": 0.08,
  "like_rate": 6.5,
  "comment_rate": 1.2,
  "relative_performance": 1.5,
  "caption_context_present": True,
  "cta_present": False,
  "insights": [
    "Excellent engagement rate by views (8.00%)...",
    "This post performed 1.5x your average..."
  ]
}
```

**`analyze_posts(creator_profile, posts: list) -> list[dict]`**

Batch version that also includes `comparison_to_previous` for each post (except the first).

---

### llm_client.py — LLM Abstraction Layer

Thin wrapper around OpenAI (easily swappable to local models):

#### `LLMClient`

**Initialization:**
```python
client = LLMClient(
  model_name="gpt-4o-mini",  # from LLM_MODEL_NAME env or default
  temperature=0.4,
  max_tokens=400,
  timeout=30,
  max_retries=1
)
```

**`generate(prompt: dict[str, str]) -> str`**

Calls the LLM with retries. Prompt format:
```python
{
  "system": "You are...",
  "user": "Analyze the following...",
  "response_format": { "type": "json_schema", ... }  # optional
}
```

**Retry logic:**
- Attempts request up to `max_retries + 1` times.
- If `response_format` fails, retries without it.
- Logs timing and warnings.
- Raises `LLMClientError` if all attempts exhaust.

**`embed(text: str) -> list[float] | None`**

Generates embedding vector using OpenAI's embedding model (for creator pool).
- Returns `EMBEDDING_DIMENSION` (1536 for OpenAI ada-002).
- Returns `None` if embedding API is unavailable.

---

### rag.py — RAG Engine & Action Planner

Simple in-memory **Retrieval Augmented Generation** system using sentence-transformers.

#### `RAGEngine`

**Initialization:**
```python
engine = RAGEngine()
engine.load_knowledge()  # Loads markdown from backend/app/knowledge/
```

**`load_knowledge()`**

1. Scans `backend/app/knowledge/` for `.md` files.
2. Chunks text via `_chunk_text()` (400-char default chunks with 50-char overlap).
3. Embeds chunks using sentence-transformers (`all-MiniLM-L6-v2`).
4. Caches embeddings to disk (`.rag_cache/`).

**`retrieve(query: str, k: int = 3) -> list[str]`**

Retrieves top-k relevant chunks:
1. Embeds query with sentence-transformers.
2. Computes cosine similarity with cached chunk embeddings.
3. Returns top-k chunks by similarity.

#### `generate_action_plan(creator_metrics, niche_data, momentum, best_time, recent_posts, knowledge_chunks=None) -> dict`

Generates a **growth action plan** via LLM with deterministic fallback:

**Process:**
1. Build context dict from deterministic signals (followers, growth score, niche, momentum, etc.).
2. Retrieve knowledge chunks via `retrieve()` if not provided.
3. Call LLM with action plan prompt (niche-aware, creator-specific).
4. [If LLM succeeds] Parse JSON/TOON response → return structured action plan.
5. [If LLM fails] Fall back to `_deterministic_fallback()` → rule-based recommendations.

**Returns:**
```python
{
  "diagnosis": "Your account is growing at X followers/day...",
  "weekly_plan": [
    "Increase posting to 3-4 times/week",
    "Add CTAs to boost engagement",
    "Focus on fitness niche content"
  ],
  "content_suggestions": [
    "Workout transformation reel",
    "Quick exercise tutorial"
  ],
  "posting_schedule": [
    "Post between 6-8 PM for best reach",
    "Tuesday and Thursday have highest engagement",
    "Space posts 6+ hours apart"
  ],
  "cta_tips": [
    "End captions with a question",
    "Use 'Save this for later' to boost saves"
  ]
}
```

**Deterministic fallback rules:**
- Momentum-based diagnosis (accelerating / declining / flat).
- Growth score-based recommendations.
- Niche-specific content ideas and posting times.
- Engagement-based CTA tips.

---

### cringe_analysis.py — Brand Safety & Cringe Helpers

Utilities for analyzing vision payloads and detecting problematic content.

#### Key Functions

**`build_cringe_section_for_brand_safety(vision_analysis: dict) -> dict`**

Extracts cringe data from vision payload:
```python
{
  "cringe_score": int | None,  # 0–100
  "cringe_label": "not_cringe" | "uncertain" | "cringe",
  "is_cringe": bool,  # safety-oriented threshold (45+)
  "cringe_signals": list[str],
  "production_level": "low" | "medium" | "high" | None,
  "adult_content_detected": bool
}
```

**`enforce_cringe_floor(cringe_score, cringe_signals) -> int`**

Implements "cringe floor" rule from Cringe-detector legacy:
- 3+ signals with strong keywords (awkward, forced, chaotic, etc.) → score >= 70
- 2+ signals with strong keywords → score >= 60

**`is_cringe_detected(cringe_score) -> bool`**

Returns `cringe_score >= 45` (safety-oriented threshold, distinct from "cringe" label).

---

### prompts.py — Prompt Templates

Canonical **TOON/JSON prompt templates** for deterministic AI scoring:

#### Vision/Caption Scoring Prompts

- **`S1_VISION_EVALUATION_PROMPT`** — Composition, lighting, subject clarity, aesthetic (0–10 scale).
- **`S2_CAPTION_EVALUATION_PROMPT`** — Hook score, length, hashtag quality, CTA strength (0–100 scale).
- **`S3_CLARITY_EVALUATION_PROMPT`** — Message singularity, context, caption–visual alignment (0–10 scale).
- **`S4_AUDIENCE_RELEVANCE_PROMPT`** — Niche/audience affinity for the post (0–100 scale).
- **`REEL_VISION_EVALUATION_PROMPT`** — Short-form video hook, pacing, audio–visual sync.

#### Response Format

All prompts enforce **TOON (Token-Oriented Object Notation)** or JSON:
```
hook_strength_score 0.78
cringe_score 25
cringe_signals
  - Slightly generic pose
  - Could be more authentic
cringe_fixes
  - Use more natural framing
production_level medium
adult_content_detected false
```

---

### niche.py — Creator Niche Detection

**`detect_creator_niche(profile: CreatorProfileAIInput, posts: list[CreatorPostAIInput]) -> dict`**

Detects primary and secondary niche categories using hashtag analysis, caption keywords, or heuristics.

**Returns:**
```python
{
  "primary_niche": "fitness",
  "secondary_niche": "lifestyle",
  "confidence": 0.85,
  "hashtags": ["#fitnesstraining", "#workoutoftheday", ...]
}
```

---

### growth_score.py — Growth Scoring

**`compute_growth_score(profile: CreatorProfileAIInput, posts: list[CreatorPostAIInput]) -> dict`**

Scores account growth on multiple dimensions:
- Engagement strength
- Posting consistency
- Audience size
- Content performance
- Growth momentum

**Returns:**
```python
{
  "growth_score": 72,  # 0–100
  "breakdown": {
    "engagement": 24,  # /30
    "consistency": 16,  # /20
    "audience": 18,    # /20
    "content": 18,     # /20
    "growth_trend": 8   # /10
  },
  "metrics": {
    "avg_views": 5200,
    "avg_engagement_rate_by_views": 0.075,
    "posts_per_week": 3.2,
    "views_to_followers_ratio": 0.41
  }
}
```

---

## Analytics Layer (backend/app/analytics/)

### derived_metrics.py — Post-Level Derived Metrics

**`compute_derived_metrics(core_metrics: CoreMetrics) -> DerivedMetrics`**

Computes secondary metrics from primary engagement data:
- `engagement_rate` = (likes + comments) / views (or from core_metrics)
- `like_rate`, `comment_rate`, `total_interactions`
- Additional metrics for advanced analysis

**Returns:** `DerivedMetrics` dataclass with computed fields.

---

### benchmark_engine.py — Comparative Analysis

**`compute_benchmark_metrics(post: SinglePostInsights, historical_posts: list[SinglePostInsights]) -> BenchmarkMetrics`**

Compares post against:
- Creator's historical posts
- Niche-specific benchmarks (if available)
- Follower band benchmarks (e.g., 100k–1M creators)

**Returns:** `BenchmarkMetrics` with percentile ranks, z-scores, performance bands.

---

### content_score.py — Aggregated Content Scoring

**`compute_content_score(derived: DerivedMetrics, benchmark: BenchmarkMetrics) -> dict`**

Combines derived + benchmark metrics into an aggregated **content score** (0–100).

**Returns:**
```python
{
  "overall_score": 75,
  "engagement_component": 0.80,
  "performance_component": 0.70,
  "consistency_component": 0.75
}
```

---

### audience_quality.py — Authenticity Analysis

**`calculate_authenticity_score(follower_count, avg_views, avg_likes, avg_comments) -> float`**

Estimates account **authenticity** (likelihood followers are real):
- High engagement relative to follower count → authentic.
- Low engagement relative to followers → potential bot followers.

**Returns:** Score 0–100 with bands: low, moderate, high.

---

### account_health_engine.py — Account-Level Scoring

**`compute_account_health_score(posts, account_avg_engagement_rate, niche_avg_engagement_rate, follower_band) -> AccountHealthScore`**

Scores account on **Account Health Score (AHS)** pillars:
1. **Engagement Health** — consistent, positive engagement signals.
2. **Content Quality** — mix of content types, production quality.
3. **Growth Consistency** — stable posting cadence, momentum.
4. **Audience Alignment** — niche relevance, audience composition.

**Returns:**
```python
{
  "ahs_score": 68,  # 0–100
  "ahs_band": "good",  # poor, fair, good, excellent
  "pillars": {
    "engagement": { "score": 70, "band": "good", "notes": [...] },
    "content_quality": { "score": 65, "band": "fair", "notes": [...] },
    ...
  },
  "drivers": [
    { "name": "Posting frequency too low", "impact": "negative" },
    ...
  ],
  "recommendations": [...]
}
```

---

## Data Flow Summary

### Single Post Analysis Pipeline
```
API Request (POST /api/v1/post-analysis)
  ↓
PostAnalysisRequest validation
  ↓
build_single_post_insights()
  ├─ coerce to SinglePostInsights
  ├─ compute_derived_metrics()
  ├─ compute_benchmark_metrics()
  ├─ compute_content_score()
  └─ [optional] analyze_single_post_ai()
      ├─ call LLM for S2–S4 scores
      ├─ call vision API for S1, S6
      └─ parse TOON responses
  ↓
Build response payload with vision, scores, AI analysis
  ↓
Cache cringe_summary in Redis
  ↓
Return JSON to client
```

### Creator Dashboard Pipeline
```
API Request (GET /api/creator/dashboard)
  ↓
build_creator_dashboard()
  ├─ Fetch Instagram data (API or demo)
  ├─ map_instagram_to_ai_inputs()
  ├─ detect_creator_niche()
  ├─ compute_growth_score()
  ├─ analyze_posts() [deterministic insights]
  ├─ Query FollowerSnapshot from DB
  ├─ RAG retrieve() + generate_action_plan()
  ├─ [optional] calculate_authenticity_score()
  └─ Assemble response
  ↓
Return to frontend
```

---

## Environment Variables (AI-related)

- `OPENAI_API_KEY` — Used by `LLMClient` for LLM and embedding calls.
- `GEMINI_API_KEY` — Enables vision features (optional).
- `LLM_MODEL_NAME` — Override default LLM model (default: `gpt-4o-mini`).
- `RAG_CACHE_DIR` — Directory for RAG embeddings cache (default: `.rag_cache`).

---

## Testing AI Modules

Key test utilities:
- Mock `LLMClient` to return fixture responses.
- Mock vision payloads (JSON fixtures in `backend/app/tests/fixtures/`).
- Use `CreatorProfileAIInput` and `CreatorPostAIInput` factories for deterministic test data.

---

## Summary of AI & Analytics

| Module | Purpose | Key Function | Output |
|--------|---------|---|--------|
| schemas.py | Input models | `CreatorProfileAIInput`, `CreatorPostAIInput` | Pydantic models |
| post_insights.py | Deterministic metrics | `analyze_post()`, `analyze_posts()` | Dict with insights |
| llm_client.py | LLM abstraction | `LLMClient.generate()` | Text response |
| rag.py | Knowledge retrieval + planning | `retrieve()`, `generate_action_plan()` | Action plan dict |
| cringe_analysis.py | Brand safety helpers | `build_cringe_section_for_brand_safety()` | Cringe dict |
| prompts.py | Prompt templates | S1–S4 prompt strings | TOON/JSON prompts |
| niche.py | Niche detection | `detect_creator_niche()` | Niche dict |
| growth_score.py | Growth scoring | `compute_growth_score()` | Growth dict |
| derived_metrics.py | Post metrics | `compute_derived_metrics()` | `DerivedMetrics` |
| benchmark_engine.py | Comparative scoring | `compute_benchmark_metrics()` | `BenchmarkMetrics` |
| content_score.py | Aggregated score | `compute_content_score()` | Content score dict |
| account_health_engine.py | Account scoring | `compute_account_health_score()` | `AccountHealthScore` |

