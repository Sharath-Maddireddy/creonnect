# Creonnect Architecture Guide

> **Creator Intelligence Backend** - AI-powered analytics and insights for social media creators.

This document provides a comprehensive technical architecture guide for the Creonnect platform. It covers the end-to-end data flow, folder structure, analytics layer, RAG pipeline, ML training system, and development workflows.

---

## Table of Contents

1. [High-Level System Overview](#1-high-level-system-overview)
2. [Folder Structure Breakdown](#2-folder-structure-breakdown)
3. [Backend Request Lifecycle](#3-backend-request-lifecycle)
4. [Analytics Layer](#4-analytics-layer)
5. [RAG + Action Engine](#5-rag--action-engine)
6. [Creator Script Generator](#6-creator-script-generator)
7. [ML Pipeline](#7-ml-pipeline)
8. [Evaluation System](#8-evaluation-system)
9. [Configuration](#9-configuration)
10. [Development Workflow](#10-development-workflow)
11. [Roadmap](#11-roadmap)

---

## 1. High-Level System Overview

Creonnect is a **creator intelligence platform** that analyzes Instagram creator data and generates actionable growth recommendations. The system combines traditional analytics with AI-powered insights using a RAG (Retrieval Augmented Generation) pipeline.

### What Creonnect Does

1. **Ingests creator data** (currently synthetic/demo data, future: Instagram API)
2. **Computes analytics** (growth score, engagement rates, momentum, best posting times)
3. **Retrieves knowledge** using semantic search over domain expertise
4. **Generates action plans** with personalized recommendations
5. **Creates content scripts** tailored to the creator's niche
6. **Serves data via REST API** for frontend visualization

### End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            CREONNECT ARCHITECTURE                                │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   DATA SOURCE    │     │   ANALYTICS      │     │   AI LAYER       │
│                  │     │                  │     │                  │
│  ┌────────────┐  │     │  ┌────────────┐  │     │  ┌────────────┐  │
│  │ Synthetic  │──┼────►│  │ Growth     │  │     │  │ Niche      │  │
│  │ Creator    │  │     │  │ Score      │  │     │  │ Detection  │  │
│  │ Data       │  │     │  └────────────┘  │     │  └────────────┘  │
│  └────────────┘  │     │  ┌────────────┐  │     │  ┌────────────┐  │
│  ┌────────────┐  │     │  │ Momentum   │  │     │  │ RAG        │  │
│  │ Instagram  │  │     │  │ Tracker    │  │     │  │ Retrieval  │  │
│  │ API        │  │     │  └────────────┘  │     │  └────────────┘  │
│  │ (Future)   │  │     │  ┌────────────┐  │     │  ┌────────────┐  │
│  └────────────┘  │     │  │ Best Time  │  │     │  │ Action     │  │
│                  │     │  │ Analysis   │  │     │  │ Plan Gen   │  │
└──────────────────┘     │  └────────────┘  │     │  └────────────┘  │
                         │  ┌────────────┐  │     │  ┌────────────┐  │
                         │  │ Post       │  │     │  │ Script     │  │
                         │  │ Insights   │  │     │  │ Generator  │  │
                         │  └────────────┘  │     │  └────────────┘  │
                         └────────┬─────────┘     └────────┬─────────┘
                                  │                        │
                                  ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SERVICE LAYER                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                      dashboard_service.py                                │    │
│  │   Orchestrates: load data → compute analytics → RAG → action plan       │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   API LAYER      │     │   FRONTEND       │     │   ML PIPELINE    │
│                  │     │                  │     │                  │
│  ┌────────────┐  │     │  ┌────────────┐  │     │  ┌────────────┐  │
│  │ /api/      │◄─┼─────┼──│ Dashboard  │  │     │  │ Enrich     │  │
│  │ creator/   │  │     │  │ Component  │  │     │  │ Dataset    │  │
│  │ dashboard  │  │     │  └────────────┘  │     │  └────────────┘  │
│  └────────────┘  │     │  ┌────────────┐  │     │  ┌────────────┐  │
│  ┌────────────┐  │     │  │ Charts     │  │     │  │ Convert    │  │
│  │ /api/      │  │     │  │ (Recharts) │  │     │  │ to Chat    │  │
│  │ generate-  │  │     │  └────────────┘  │     │  └────────────┘  │
│  │ script     │  │     │                  │     │  ┌────────────┐  │
│  └────────────┘  │     │                  │     │  │ Fine-tune  │  │
│                  │     │                  │     │  │ GPT-4o     │  │
└──────────────────┘     └──────────────────┘     │  └────────────┘  │
                                                  │  ┌────────────┐  │
                                                  │  │ Evaluate   │  │
                                                  │  │ Model      │  │
                                                  │  └────────────┘  │
                                                  └──────────────────┘
```

### Request Flow Summary

```
Frontend Request
      │
      ▼
  GET /api/creator/dashboard
      │
      ▼
  dashboard.py (API Router)
      │
      ▼
  dashboard_service.py (Orchestration)
      │
      ├──► load_synthetic() ──► profile, posts
      │
      ├──► detect_creator_niche() ──► niche classification
      │
      ├──► compute_growth_score() ──► growth_score + metrics
      │
      ├──► analyze_posts() ──► post insights + comparisons
      │
      ├──► calculate_momentum() ──► momentum_value, momentum_label
      │
      ├──► get_best_posting_hours() ──► best_posting_hours
      │
      ├──► retrieve() ──► knowledge chunks from RAG
      │
      └──► generate_action_plan() ──► actionable recommendations
      │
      ▼
  JSON Response to Frontend
```

---

## 2. Folder Structure Breakdown

### Root Structure

```
creonnect/
├── backend/                 # Python FastAPI backend
│   ├── app/                 # Application modules
│   ├── core/                # Core analytics logic
│   ├── data/                # Training data (JSONL files)
│   ├── ml/                  # ML pipeline scripts
│   ├── main.py              # FastAPI application entry point
│   └── requirements.txt     # Python dependencies
├── frontend/                # React/Vite frontend
│   ├── src/                 # Source code
│   └── package.json         # Node dependencies
├── .env.example             # Environment variable template
├── requirements.txt         # Top-level dependencies
└── README.md                # Project documentation
```

### `backend/app/` — Application Modules

| Folder | Purpose |
|--------|---------|
| `api/` | **FastAPI routers** — HTTP endpoints that expose functionality. Contains `dashboard.py` with routes like `/api/creator/dashboard`. |
| `services/` | **Orchestration layer** — Coordinates between data loading, analytics, and AI. The `dashboard_service.py` is the main orchestrator. |
| `ai/` | **AI/ML modules** — Niche detection, growth scoring, RAG retrieval, action plan generation, LLM client. |
| `demo/` | **Demo data** — Synthetic creator generator and loader for development without real Instagram data. |
| `knowledge/` | **RAG knowledge base** — Markdown files with domain expertise (Instagram best practices, growth playbook, campaign rules). |
| `ingestion/` | **Data ingestion** — Mapping and normalization layer (reserved for future Instagram API ingestion). |
| `utils/` | **Utilities** — Logging configuration and helper functions. |
| `tests/` | **Unit tests** — Test files for various modules. |

### `backend/core/` — Core Analytics

This folder contains **pure analytics logic** with no external dependencies on AI/LLM:

| File | Purpose |
|------|---------|
| `momentum.py` | Calculates follower growth momentum from daily snapshots |
| `best_time.py` | Analyzes optimal posting hours based on engagement |
| `post_comparison.py` | Compares consecutive posts to show performance trends |
| `snapshots.py` | Builds creator metric snapshots for tracking |
| `script_generator.py` | Generates niche-aware reel scripts using templates |

### `backend/app/ai/` — AI Layer

| File | Purpose |
|------|---------|
| `rag.py` | RAG engine: chunking, embedding, retrieval, action plan generation |
| `growth_score.py` | Computes 0-100 growth score with weighted components |
| `post_insights.py` | Analyzes individual posts with engagement metrics |
| `niche.py` | Detects creator niche using sentence embeddings |
| `llm_client.py` | OpenAI API wrapper for LLM calls |
| `prompt_builder.py` | Constructs prompts for LLM-based features |
| `schemas.py` | Pydantic models for AI input/output |

### `backend/ml/` — ML Pipeline

| File | Purpose |
|------|---------|
| `enrich_dataset_with_action_plan.py` | Adds action_plan to training data |
| `convert_to_chat_dataset.py` | Converts to OpenAI chat format |
| `finetune_gpt4o_mini.py` | Uploads and triggers fine-tuning job |
| `evaluate_action_model.py` | Evaluates model output quality |
| `chat_train.jsonl` | Training dataset in chat format |
| `chat_val.jsonl` | Validation dataset in chat format |

### `frontend/` — React Frontend

| Path | Purpose |
|------|---------|
| `src/App.jsx` | Main app component |
| `src/pages/Dashboard.jsx` | Dashboard page with charts and metrics |
| `src/index.css` | Global styles |
| `vite.config.js` | Vite configuration with API proxy |

---

## 3. Backend Request Lifecycle

Let's trace a complete request to **`GET /api/creator/dashboard`**:

### Step 1: API Router (`backend/app/api/dashboard.py`)

```python
@router.get("/creator/dashboard")
def creator_dashboard():
    return build_creator_dashboard("demo")
```

The router is minimal — it delegates all logic to the service layer.

### Step 2: Service Orchestration (`backend/app/services/dashboard_service.py`)

The `build_creator_dashboard()` function orchestrates the entire pipeline:

```python
def build_creator_dashboard(creator_id: str) -> dict:
    # 1. Load demo data
    profile, posts = load_synthetic()
    
    # 2. AI: Detect niche
    niche = detect_creator_niche(profile, posts)
    
    # 3. AI: Compute growth score
    growth = compute_growth_score(profile, posts)
    
    # 4. AI: Analyze posts
    post_insights = analyze_posts(profile, posts)
    
    # 5. Core: Calculate momentum
    momentum = calculate_momentum(simulated_snapshots)
    
    # 6. Core: Get best posting times
    best_time = get_best_posting_hours(posts_for_time_analysis)
    
    # 7. RAG: Retrieve knowledge
    knowledge_chunks = retrieve(query, k=3)
    
    # 8. RAG: Generate action plan
    action_plan = generate_action_plan(
        creator_metrics, niche, momentum, best_time,
        recent_posts, knowledge_chunks
    )
    
    # 9. Return assembled response
    return {
        "summary": { ... },
        "posts": post_insights,
        "charts": { ... },
        "action_plan": action_plan
    }
```

### Step 3: Data Loading (`backend/app/demo/synthetic_loader.py`)

```python
profile, posts = load_synthetic()
```

Loads `synthetic_creator.json` and converts to typed schemas:
- `CreatorProfileAIInput` — username, followers, engagement metrics
- `CreatorPostAIInput` — post_id, likes, comments, views, caption

### Step 4: Analytics Computation

Each analytics module processes the data independently:

| Module | Input | Output |
|--------|-------|--------|
| `detect_creator_niche()` | profile, posts | `{primary_niche, secondary_niches, confidence}` |
| `compute_growth_score()` | profile, posts | `{growth_score, breakdown, metrics}` |
| `analyze_posts()` | profile, posts | List of post insights with engagement rates |
| `calculate_momentum()` | snapshots | `{momentum_value, momentum_label}` |
| `get_best_posting_hours()` | posts | `{best_posting_hours, hourly_engagement}` |

### Step 5: RAG Retrieval

```python
query = f"{niche} growth strategies engagement tips"
knowledge_chunks = retrieve(query, k=3)
```

The RAG engine:
1. Embeds the query using `sentence-transformers`
2. Computes cosine similarity against knowledge base embeddings
3. Returns top-k most relevant chunks

### Step 6: Action Plan Generation

```python
action_plan = generate_action_plan(
    creator_metrics, niche_data, momentum,
    best_time, recent_posts, knowledge_chunks
)
```

Produces structured recommendations:
```json
{
    "diagnosis": "Your account is growing at 80 followers/day...",
    "weekly_plan": ["Increase posting frequency...", ...],
    "content_suggestions": ["Workout transformation reel", ...],
    "posting_schedule": ["Post between 6 PM...", ...],
    "cta_tips": ["End captions with a question...", ...]
}
```

### Step 7: Response Assembly

The final response combines all computed data:

```json
{
    "summary": {
        "username": "demo",
        "followers": 75000,
        "growth_score": 72,
        "avg_engagement_rate_by_views": 0.0765,
        "niche": {"primary_niche": "fitness", ...},
        "momentum": {"momentum_value": 80, "momentum_label": "accelerating"},
        "best_time_to_post": {"best_posting_hours": [18, 19], ...}
    },
    "posts": [...],
    "charts": {...},
    "action_plan": {...}
}
```

---

## 4. Analytics Layer

### Growth Score (`backend/app/ai/growth_score.py`)

The growth score is a **0-100 composite metric** with weighted components:

| Component | Max Points | What It Measures |
|-----------|------------|------------------|
| `engagement` | 30 | Engagement rate by views (likes+comments)/views |
| `content` | 20 | Views/followers ratio (viral potential) |
| `consistency` | 20 | Posts per week frequency |
| `audience` | 20 | Total follower count |
| `growth_trend` | 10 | Historical growth (placeholder) |

#### Engagement by Views Formula

```python
engagement_rate_by_views = (likes + comments) / views
```

This is the **primary metric** because Instagram's algorithm prioritizes view-based engagement over follower-based.

#### Scoring Thresholds

```python
# Engagement by views scoring (max 30 points)
if avg_engagement_rate >= 0.10: return 30  # 10%+ = excellent
if avg_engagement_rate >= 0.07: return 26  # 7%+ = very good
if avg_engagement_rate >= 0.05: return 22  # 5%+ = good
if avg_engagement_rate >= 0.03: return 18  # 3%+ = average
if avg_engagement_rate >= 0.01: return 12  # 1%+ = needs work
return 6  # <1% = poor
```

### Momentum (`backend/core/momentum.py`)

Tracks **follower growth velocity** over time:

```python
def calculate_momentum(snapshots: List[Dict]) -> Dict:
    # Use last 7 days of snapshots
    window = snapshots[-7:]
    
    # Calculate daily change
    momentum_value = (latest_followers - previous_followers) / number_of_days
    
    # Classify
    if momentum_value > 0:
        momentum_label = "accelerating"
    elif momentum_value < 0:
        momentum_label = "declining"
    else:
        momentum_label = "flat"
```

**Output:**
```json
{
    "momentum_value": 80.0,
    "momentum_label": "accelerating"
}
```

### Best Posting Time (`backend/core/best_time.py`)

Analyzes **which hours get the best engagement**:

```python
def get_best_posting_hours(posts: List[Dict]) -> Dict:
    # Group engagement by hour
    for post in posts:
        hour = post.created_at.hour
        engagement_rate = (likes + comments) / views
        hour_engagement[hour].append(engagement_rate)
    
    # Average per hour, sort descending
    sorted_hours = sorted(hourly_avg.keys(), key=lambda h: hourly_avg[h], reverse=True)
    
    return {
        "best_posting_hours": sorted_hours[:2],
        "hourly_engagement": hourly_avg
    }
```

### Post Comparison (`backend/core/post_comparison.py`)

Compares **consecutive posts** to show trends:

```python
def compare_posts(current_post, previous_post) -> dict:
    # Engagement deltas
    delta_views = current_views - previous_views
    delta_likes = current_likes - previous_likes
    
    # Engagement rate change
    engagement_change_pct = ((current_rate - previous_rate) / previous_rate) * 100
    
    return {
        "delta_views": delta_views,
        "engagement_change_pct": engagement_change_pct,
        "relative_performance_label": "better" | "worse" | "same",
        "explanation": "This post performed better with 15% higher engagement."
    }
```

---

## 5. RAG + Action Engine

### Knowledge Base (`backend/app/knowledge/`)

The RAG system uses **domain expertise documents**:

| File | Content |
|------|---------|
| `instagram_best_practices.md` | Algorithm fundamentals, view-based metrics, posting strategy |
| `creator_growth_playbook.md` | Growth tactics, content strategies |
| `brand_campaign_rules.md` | Brand collaboration guidelines |

### RAG Engine (`backend/app/ai/rag.py`)

#### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       RAGEngine                              │
├─────────────────────────────────────────────────────────────┤
│  Knowledge Loading:                                          │
│  1. Read .md files from knowledge/                           │
│  2. Chunk text (400 chars, 50 overlap)                       │
│  3. Embed chunks using all-MiniLM-L6-v2                      │
│  4. Cache embeddings to .rag_cache/                          │
├─────────────────────────────────────────────────────────────┤
│  Retrieval:                                                  │
│  1. Embed query                                              │
│  2. Compute cosine similarity                                │
│  3. Return top-k chunks                                      │
└─────────────────────────────────────────────────────────────┘
```

#### Chunking Strategy

```python
CHUNK_SIZE = 400    # Target characters per chunk
CHUNK_OVERLAP = 50  # Overlap for context continuity

def _chunk_text(text, chunk_size, overlap):
    # Split on paragraph boundaries
    paragraphs = text.split("\n\n")
    
    # Accumulate until chunk_size exceeded
    # Keep overlap from previous chunk
```

#### Embedding Model

Uses `sentence-transformers/all-MiniLM-L6-v2`:
- Fast, lightweight (22M parameters)
- 384-dimensional embeddings
- Good for semantic similarity

#### Caching

Embeddings are cached to avoid recomputation:
```
.rag_cache/
├── .rag_embeddings.npy    # NumPy array of vectors
└── .rag_chunks.json       # Chunk text + metadata
```

### Action Plan Generator

The `generate_action_plan()` function creates structured recommendations:

#### Prompt Structure (Conceptual)

```
Given:
- Creator metrics: followers=75000, growth_score=72, avg_views=85000
- Niche: fitness
- Momentum: accelerating (+80/day)
- Best posting hours: [18, 19]
- Recent posts: [...]
- Knowledge: [RAG chunks]

Generate:
- diagnosis: Current state assessment
- weekly_plan: 3 actionable items
- content_suggestions: 2 content ideas
- posting_schedule: 3 timing recommendations
- cta_tips: 2 engagement boosters
```

#### Output JSON Schema

```json
{
    "_model": "gpt-4o-mini",
    "_model_version": "base",
    "diagnosis": "Your account is growing at 80 followers/day...",
    "weekly_plan": [
        "Keep up your 4.5 posts/week cadence",
        "Focus content on your fitness niche",
        "Engage with 10+ accounts daily"
    ],
    "content_suggestions": [
        "Workout transformation reel",
        "Double down on your top-performing content format"
    ],
    "posting_schedule": [
        "Post between 6 PM - your audience is most active",
        "Tuesday and Thursday typically have highest engagement"
    ],
    "cta_tips": [
        "End captions with a question to encourage comments",
        "Use 'Save this for later' to boost save rate"
    ]
}
```

#### Model Switching

Control the model via environment variables:

```bash
ACTION_MODEL=gpt-4o-mini           # Base model
ACTION_MODEL=ft:gpt-4o-mini:xxx    # Fine-tuned model
ACTION_MODEL_VERSION=base          # Metadata tag
```

#### Versioning Metadata

Every action plan includes metadata for traceability:
```json
{
    "_model": "gpt-4o-mini",
    "_model_version": "base",
    ...
}
```

---

## 6. Creator Script Generator

The script generator produces **niche-aware reel scripts** (`backend/core/script_generator.py`).

### How It Works

#### Step 1: Select Top Post

```python
# Find best-performing post by engagement
top_post = max(posts, key=lambda p: (p.likes + p.comments) / max(p.views, 1))
```

#### Step 2: Detect Niche

Uses the niche classification from `detect_creator_niche()`:
- fitness, food, travel, tech, fashion, lifestyle, general

#### Step 3: Select Templates

Each niche has tailored templates:

```python
HOOK_TEMPLATES = {
    "fitness": [
        "Stop scrolling if you want to {goal}",
        "This one exercise changed everything for me",
        "The {duration} workout that actually works"
    ],
    ...
}
```

#### Step 4: Fill Placeholders

```python
def _fill_template(template: str, context: dict):
    # Replace {goal}, {duration}, {reps}, etc.
    template = template.replace("{goal}", random.choice(goals))
    ...
```

### Output Format

```json
{
    "hook": "Stop scrolling if you want to build muscle",
    "body": "Focus on form over speed. Start with 10 reps and build up gradually.",
    "cta": "Save this for your next workout!",
    "niche": "fitness",
    "inspired_by": {
        "post_id": "post_003",
        "engagement_rate": 0.089
    }
}
```

---

## 7. ML Pipeline

The ML pipeline enables **fine-tuning GPT-4o-mini** on creator action plans.

### Pipeline Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           ML TRAINING PIPELINE                              │
└────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ training_    │     │ training_    │     │ chat_train   │     │ Fine-tuned   │
│ data.jsonl   │────►│ data_with_   │────►│ .jsonl       │────►│ GPT-4o-mini  │
│              │     │ actions.jsonl│     │ chat_val     │     │              │
│ Raw data     │     │ + action_plan│     │ .jsonl       │     │ Custom model │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │                    │
       │                    │                    │                    │
       ▼                    ▼                    ▼                    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ enrich_      │     │ convert_to_  │     │ finetune_    │     │ evaluate_    │
│ dataset_     │     │ chat_        │     │ gpt4o_       │     │ action_      │
│ with_action_ │     │ dataset.py   │     │ mini.py      │     │ model.py     │
│ plan.py      │     │              │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Step 1: Raw Training Data

**File:** `backend/data/training_data.jsonl`

Each line contains creator profile + posts:
```json
{
    "example_id": "creator_001",
    "input": {
        "profile": {"username": "...", "followers": 50000, ...},
        "posts": [...]
    },
    "output": {
        "niche": {...},
        "growth": {...}
    }
}
```

### Step 2: Enrich with Action Plans

**Script:** `backend/ml/enrich_dataset_with_action_plan.py`

```bash
python -m backend.ml.enrich_dataset_with_action_plan
```

For each example:
1. Build momentum from simulated snapshots
2. Calculate best posting times
3. Retrieve RAG knowledge
4. Generate action plan
5. Append to output

**Output:** `backend/data/training_data_with_actions.jsonl`

### Step 3: Convert to Chat Format

**Script:** `backend/ml/convert_to_chat_dataset.py`

```bash
python -m backend.ml.convert_to_chat_dataset
```

Transforms to OpenAI chat format:

```json
{
    "messages": [
        {"role": "system", "content": "You are a creator growth expert..."},
        {"role": "user", "content": "<creator_profile>...</creator_profile>..."},
        {"role": "assistant", "content": "{\"diagnosis\": \"...\", ...}"}
    ]
}
```

**Outputs:**
- `backend/ml/chat_train.jsonl` — Training examples
- `backend/ml/chat_val.jsonl` — Validation examples

### Step 4: Fine-tune GPT-4o-mini

**Script:** `backend/ml/finetune_gpt4o_mini.py`

```bash
python -m backend.ml.finetune_gpt4o_mini
```

1. Uploads training and validation files to OpenAI
2. Creates fine-tuning job
3. Polls for completion
4. Returns fine-tuned model ID

```
training_file_id: file-abc123
validation_file_id: file-def456
fine_tune_job_id: ftjob-xyz789
status: running → succeeded
fine_tuned_model_id: ft:gpt-4o-mini:org::abc123
```

### ML Lifecycle Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ML LIFECYCLE                                       │
└─────────────────────────────────────────────────────────────────────────────┘

     DATA GENERATION          TRAINING              DEPLOYMENT
     ─────────────────────────────────────────────────────────────────────

     ┌─────────────┐
     │ Synthetic   │
     │ Demo Data   │
     └──────┬──────┘
            │
            ▼
     ┌─────────────┐         ┌─────────────┐
     │ RAG         │         │ training_   │
     │ Pipeline    │────────►│ data.jsonl  │
     └─────────────┘         └──────┬──────┘
                                    │
                                    ▼
                             ┌─────────────┐
                             │ Enrich with │
                             │ action_plan │
                             └──────┬──────┘
                                    │
                                    ▼
                             ┌─────────────┐
                             │ Convert to  │
                             │ Chat Format │
                             └──────┬──────┘
                                    │
                     ┌──────────────┴──────────────┐
                     │                             │
                     ▼                             ▼
              ┌─────────────┐              ┌─────────────┐
              │ chat_train  │              │ chat_val    │
              │ .jsonl      │              │ .jsonl      │
              └──────┬──────┘              └──────┬──────┘
                     │                             │
                     └──────────────┬──────────────┘
                                    │
                                    ▼
                             ┌─────────────┐
                             │ Fine-tune   │
                             │ GPT-4o-mini │
                             │ (OpenAI)    │
                             └──────┬──────┘
                                    │
                                    ▼
                             ┌─────────────┐         ┌─────────────┐
                             │ ft:gpt-4o-  │────────►│ ACTION_MODEL│
                             │ mini:xxx    │         │ env var     │
                             └─────────────┘         └─────────────┘
                                                            │
                                                            ▼
                                                     ┌─────────────┐
                                                     │ Production  │
                                                     │ API         │
                                                     └─────────────┘

     FUTURE: QLoRA Path
     ────────────────────────────────────────────────────────────────────

     ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
     │ Larger base │────────►│ QLoRA       │────────►│ Local       │
     │ model       │         │ Fine-tune   │         │ Deployment  │
     │ (Llama, etc)│         │ (4-bit)     │         │             │
     └─────────────┘         └─────────────┘         └─────────────┘
```

---

## 8. Evaluation System

The evaluation system measures **action plan quality** (`backend/ml/evaluate_action_model.py`).

### Metrics

| Metric | Description | Measurement |
|--------|-------------|-------------|
| `json_valid` | Is the output valid JSON? | Parse success rate |
| `has_all_keys` | Does it have required keys? | `diagnosis`, `weekly_plan`, etc. |
| `weekly_plan_overlap` | Token similarity with ground truth | Jaccard similarity |
| `output_length` | Average response length | Character count |

### Evaluation Modes

| Mode | Description |
|------|-------------|
| `baseline` | Compare ground truth to itself (perfect score baseline) |
| `base_gpt` | Call vanilla GPT-4o-mini |
| `ft_gpt` | Call fine-tuned model (requires `ACTION_MODEL` env var) |

### Running Evaluation

```bash
# Baseline (perfect scores)
python -m backend.ml.evaluate_action_model --mode baseline --limit 10

# Base GPT-4o-mini
python -m backend.ml.evaluate_action_model --mode base_gpt --limit 10

# Fine-tuned model
ACTION_MODEL=ft:gpt-4o-mini:xxx python -m backend.ml.evaluate_action_model --mode ft_gpt --limit 10
```

### Sample Output

```
Action Plan Evaluation (ft_gpt)
Total examples: 10
% json_valid: 100.00
% has_all_keys: 100.00
avg_weekly_plan_overlap: 0.4523
avg_output_length: 412.30
```

### Interpreting Results

- `json_valid`: Should be 100% — the model must output valid JSON
- `has_all_keys`: Should be 100% — schema compliance
- `weekly_plan_overlap`: Higher is better — measures recommendation quality
- `output_length`: Monitor for reasonable length (not too verbose/terse)

---

## 9. Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key for LLM calls |
| `ACTION_MODEL` | No | `gpt-4o-mini` | Model for action plan generation |
| `ACTION_MODEL_VERSION` | No | `base` | Version tag for metadata |
| `RAG_CACHE_DIR` | No | `.rag_cache` | Directory for embedding cache |
| `ENV` | No | `dev` | Environment (dev/staging/production) |

### Setting Up Environment

```bash
# Copy template
cp .env.example .env

# Edit .env
OPENAI_API_KEY=sk-your-key-here
ACTION_MODEL=gpt-4o-mini
ACTION_MODEL_VERSION=base
RAG_CACHE_DIR=.rag_cache
ENV=dev
```

### Using a Fine-tuned Model

After fine-tuning completes:

```bash
# Set the fine-tuned model ID
ACTION_MODEL=ft:gpt-4o-mini:your-org::abc123xyz
ACTION_MODEL_VERSION=v1_finetune
```

---

## 10. Development Workflow

### Initial Setup

```bash
# 1. Clone repository
git clone <repo-url>
cd creonnect

# 2. Create virtual environment
python -m venv .venv

# 3. Activate (Windows)
.venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Set environment variables
cp .env.example .env
# Edit .env with your OPENAI_API_KEY
```

### Running the Backend

```bash
# Start FastAPI server with hot reload
uvicorn backend.main:app --reload

# API is available at http://127.0.0.1:8000
# Docs at http://127.0.0.1:8000/docs
```

### Running the Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev

# Frontend is available at http://localhost:3000
```

### Generating Synthetic Data

```bash
# Generate new demo creator
python -m backend.app.demo.generate_fake_instagram

# Options: niche, followers, num_posts
python -c "
from backend.app.demo.generate_fake_instagram import save_synthetic_creator
save_synthetic_creator(niche='food', followers=100000, num_posts=15)
"
```

### Running the ML Pipeline

```bash
# Step 1: Enrich training data with action plans
python -m backend.ml.enrich_dataset_with_action_plan

# Step 2: Convert to chat format
python -m backend.ml.convert_to_chat_dataset

# Step 3: Fine-tune (requires OPENAI_API_KEY)
python -m backend.ml.finetune_gpt4o_mini

# Step 4: Evaluate
python -m backend.ml.evaluate_action_model --mode ft_gpt --limit 10
```

### Sanity Checks

```bash
# Health check
curl http://127.0.0.1:8000/health

# Dashboard endpoint
curl http://127.0.0.1:8000/api/creator/dashboard | python -m json.tool

# Generate script
curl -X POST http://127.0.0.1:8000/api/creators/demo/generate-script | python -m json.tool
```

### Running Tests

```bash
# Run all tests
pytest backend/app/tests/

# Run specific test file
pytest backend/app/tests/test_growth_score.py -v
```

---

## 11. Roadmap

### Current Phase: Demo + Core Analytics

- ✅ Synthetic data generation
- ✅ Growth score computation
- ✅ Momentum tracking
- ✅ Best posting time analysis
- ✅ RAG knowledge retrieval
- ✅ Action plan generation
- ✅ Script generator
- ✅ Frontend dashboard
- ✅ ML fine-tuning pipeline

### Phase 2: Instagram Integration

- [ ] Instagram Graph API ingestion
- [ ] OAuth authentication flow
- [ ] Real creator data pipeline
- [ ] Webhook for new posts

### Phase 3: Database Persistence

- [ ] PostgreSQL for user data
- [ ] Historical snapshot storage
- [ ] Analytics trend tracking
- [ ] Caching layer (Redis)

### Phase 4: Frontend Polish

- [ ] User authentication
- [ ] Multi-creator support
- [ ] Interactive action plan UI
- [ ] Script generator interface
- [ ] Mobile-responsive design

### Phase 5: ML Expansion

- [ ] QLoRA fine-tuning for local deployment
- [ ] A/B testing framework for models
- [ ] User feedback loop for training
- [ ] Multi-language support

---

## Quick Reference

### Key Files

| Purpose | File Path |
|---------|-----------|
| API Entry | `backend/main.py` |
| Dashboard Route | `backend/app/api/dashboard.py` |
| Dashboard Logic | `backend/app/services/dashboard_service.py` |
| Growth Score | `backend/app/ai/growth_score.py` |
| RAG Engine | `backend/app/ai/rag.py` |
| Momentum | `backend/core/momentum.py` |
| Best Time | `backend/core/best_time.py` |
| Script Gen | `backend/core/script_generator.py` |
| Fine-tune | `backend/ml/finetune_gpt4o_mini.py` |
| Evaluate | `backend/ml/evaluate_action_model.py` |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/creator/dashboard` | Full dashboard data |
| GET | `/api/creators/{id}/snapshot` | Creator snapshot |
| POST | `/api/creators/{id}/generate-script` | Generate reel script |

### Environment Setup Checklist

- [ ] Python 3.9+ installed
- [ ] Virtual environment created and activated
- [ ] `requirements.txt` installed
- [ ] `.env` file created with `OPENAI_API_KEY`
- [ ] Backend running with `uvicorn`
- [ ] Frontend running with `npm run dev`

---

*Last updated: February 2026*
