# Creonnect Codebase Guide

This document explains the current state of the repository at a codebase level: what each major folder does, which parts appear product-facing, how the backend and frontend connect, and which areas look experimental, transitional, or legacy.

## 1. Repository Summary

Creonnect is primarily a Python backend for creator analytics, creator discovery, brand matching, and post/reel analysis, with a separate React + Vite frontend for dashboard-style UIs.

At a high level, the repository is split into:

- `backend/`: the main application code and the most important production-facing area
- `frontend/`: the React application for analytics and brand campaign flows
- `docs/`: architecture and audit documentation
- `internal_tools/`: operational scripts, diagnostics, fixture helpers, and local artifacts
- `experimental/`: side projects and non-launch experiments
- root-level `services/` and utility scripts: older or standalone logic that is adjacent to, but not fully merged into, the main `backend/app` structure

The clearest application entrypoint is [backend/main.py](../backend/main.py), which boots the FastAPI server and registers the API routers.

## 2. Top-Level Folder Map

### `backend/`

This is the core product backend.

- [backend/main.py](../backend/main.py): FastAPI app setup, CORS, session middleware, router registration, startup lifecycle
- `backend/app/`: main domain/application code
- `backend/core/`: cross-cutting analytics helpers such as momentum, snapshot shaping, posting-time calculations
- `backend/ml/`: dataset cleaning, scaling, validation, upload, and fine-tuning helpers
- `backend/data/`: training datasets and generated ML artifacts
- [backend/requirements.txt](../backend/requirements.txt): backend dependency list

### `frontend/`

This is a Vite + React application.

- [frontend/src/App.jsx](../frontend/src/App.jsx): frontend routing
- `frontend/src/pages/`: dashboard, brand campaign, auth callback, single-post insight pages
- [frontend/package.json](../frontend/package.json): frontend scripts and dependencies

### `docs/`

Contains product, architecture, guardrail, metrics, and audit documents. These are useful, but they are specialized rather than being a single codebase onboarding guide, which is why this document exists.

### `internal_tools/`

Development-only tooling, diagnostics, and fixture management.

- fixture-based analysis scripts
- smoke tests
- developer diagnostics for reels, Gemini, cringe analysis, user post analysis
- artifacts folder for generated outputs

This folder is explicitly described as non-launch-facing in [internal_tools/README.md](../internal_tools/README.md).

### `experimental/`

Contains side explorations and non-core work. It currently includes:

- `experimental/Cringe-detector-main/`
- `experimental/cringe_classifier/`

These should be treated as research or prototype areas, not primary runtime dependencies.

### Root-level standalone files and folders

There are several root-level items outside the main `backend/` and `frontend/` shape:

- `services/`: standalone post-insight orchestration and AI-analysis helpers
- `populate_redis.py`: development seeding script for mock post insight payloads
- assorted local result files like `*_result.json`, `*_output.txt`, `pytest_err.txt`
- test scripts such as `run_test_reel.py`, `test_discovery_on_pool.py`

These make the repo feel like a working product plus a POC lab. They are useful, but they are not as cleanly integrated into the primary application boundary.

## 3. Active Application Architecture

## Backend runtime

The primary backend starts in [backend/main.py](../backend/main.py).

On startup it does the following:

1. Loads environment variables with `dotenv`
2. Resolves session secret and CORS origins
3. Validates `BRAND_API_KEY` presence
4. Flags whether Gemini-backed vision is enabled
5. Initializes database engines
6. Attempts database setup via `init_db()`
7. Registers all FastAPI routers

The app exposes:

- `/health`
- dashboard routes
- account analysis routes
- brand match and campaign routes
- post analysis routes
- reel analysis routes
- Instagram OAuth routes

## Frontend runtime

The frontend is a standard Vite React SPA.

Routes defined in [frontend/src/App.jsx](../frontend/src/App.jsx):

- `/analytics`: creator dashboard
- `/brand/campaign`: brand campaign workflow
- `/post/:media_id`: single-post insight page
- `/auth/callback`: Instagram OAuth callback landing page

The dashboard page in [frontend/src/pages/Dashboard.jsx](../frontend/src/pages/Dashboard.jsx) fetches `/api/creator/analytics` and falls back to demo mode when auth is unavailable.

## 4. `backend/app/` Breakdown

`backend/app/` is the most important directory in the repository. It is organized in a fairly healthy layered way.

### `backend/app/api/`

FastAPI route modules.

- [backend/app/api/dashboard.py](../backend/app/api/dashboard.py): creator dashboard and analytics routes
- [backend/app/api/account_analysis_routes.py](../backend/app/api/account_analysis_routes.py): enqueue and poll account analysis jobs
- [backend/app/api/campaign_routes.py](../backend/app/api/campaign_routes.py): AI-assisted brand discovery, manual campaign match, lookalikes
- [backend/app/api/post_analysis_routes.py](../backend/app/api/post_analysis_routes.py): post-analysis and post-insight endpoints
- [backend/app/api/reel_analysis_routes.py](../backend/app/api/reel_analysis_routes.py): background reel analysis job endpoints
- [backend/app/api/instagram_auth_routes.py](../backend/app/api/instagram_auth_routes.py): Instagram OAuth login/callback/session routes

### `backend/app/services/`

Application orchestration layer.

Representative modules:

- [backend/app/services/dashboard_service.py](../backend/app/services/dashboard_service.py): assembles dashboard payloads from demo or Instagram OAuth data
- [backend/app/services/account_analysis_service.py](../backend/app/services/account_analysis_service.py): deterministic account health analysis with in-memory caching
- `creator_pool_service.py`: creator pool retrieval and lookalike queries
- `campaign_prompt_service.py`: prompt-to-structured-brand-profile flow
- `post_insights_service.py`: single-post insight assembly
- `account_analysis_jobs.py` and `reel_analysis_jobs.py`: background queue orchestration

This layer is where most use-case orchestration lives.

### `backend/app/analytics/`

Pure or mostly deterministic analytics/scoring engines.

This area contains scoring logic for:

- account health
- benchmark comparisons
- audience quality
- visual analysis stages
- brand safety
- caption effectiveness
- audience relevance
- brand match
- predicted engagement
- reel audio / reel Gemini analysis
- weighted post scoring

This folder looks like the scoring core of the product.

### `backend/app/ai/`

LLM and AI-adjacent code.

Capabilities here include:

- prompt construction
- niche detection
- growth scoring support
- RAG-based retrieval and action-plan generation
- explanation generation
- cringe analysis
- LLM client wrapper
- schemas for AI-facing inputs and outputs

This is the main AI integration surface for OpenAI and Gemini-backed flows.

### `backend/app/domain/`

Pydantic/domain models for structured data exchange across the app.

Examples:

- account models
- brand models
- post models

### `backend/app/infra/`

Infrastructure concerns such as database, Redis, models, tokens.

Key files:

- [backend/app/infra/database.py](../backend/app/infra/database.py): engine/session setup for async and sync SQLAlchemy usage
- [backend/app/infra/models.py](../backend/app/infra/models.py): `creator_vectors` and `creator_discovery_meta` tables, pgvector integration, metadata indexes
- `redis_client.py`: Redis helpers
- `rq_queue.py`: queue helpers
- `token_store.py`: auth/session-related storage

### `backend/app/ingestion/`

Input-side integrations and mapping.

- Instagram OAuth fetches
- Instagram data-to-domain mapping
- legacy/dev login-related code

### `backend/app/demo/`

Synthetic data generation and loading. This is important because several routes fall back to demo behavior when live auth or data is absent.

### `backend/app/knowledge/`

Markdown knowledge files that appear to support retrieval-augmented guidance and action-plan generation.

### `backend/app/workers/`

Background worker entrypoints and scheduled jobs.

- [backend/app/workers/rq_worker.py](../backend/app/workers/rq_worker.py): RQ worker bootstrapping
- `embedding_worker.py`
- `nightly_jobs.py`

### `backend/app/tests/`

The backend contains a relatively substantial automated test suite.

Current quick count from the folder: `49` `test_*.py` files.

The naming suggests coverage across:

- API behavior
- analytics engines
- anti-regression suites
- prompt hardening
- queue orchestration
- ingestion
- brand matching
- reel analysis
- dashboard/service flows

## 5. Important Runtime Flows

### Creator dashboard flow

The dashboard flow is centered in [backend/app/services/dashboard_service.py](../backend/app/services/dashboard_service.py).

Current behavior:

1. Load creator data from Instagram OAuth if an access token is present
2. Otherwise load synthetic demo data
3. Run niche detection
4. Run growth scoring
5. Run per-post analysis
6. Build chart series
7. Simulate snapshot history for momentum
8. Compute best posting times
9. Retrieve knowledge chunks for recommendations
10. Generate the action plan payload

This is useful to know because the dashboard endpoint is not just a database read. It is an orchestration pipeline.

### Account analysis background jobs

Account analysis is queue-based:

1. `/api/account-analysis` accepts a structured request
2. the request is enqueued via service code
3. an RQ worker consumes jobs from Redis
4. `/api/account-analysis/{job_id}` is used to poll status

This means Redis and the worker process are required for the asynchronous analysis path.

### Brand campaign and creator matching

There are two related matching surfaces:

- direct scoring via `/api/brand/campaign/match`
- richer campaign/discovery flows via `/api/brand/campaign/*`

The campaign flow can:

- parse natural language prompts into structured brand profiles
- query the creator pool
- score candidates
- return top matches
- find semantic lookalikes

The database model in [backend/app/infra/models.py](../backend/app/infra/models.py) shows that creator discovery metadata and embeddings are meant to support this area.

### Post and reel analysis

Post and reel analysis are distinct concerns:

- post analysis lives under `post_analysis_routes.py` plus related services and analytics modules
- reel analysis is background-job driven under `reel_analysis_routes.py`

There is also root-level `services/` code that still contains post insight orchestration and AI output shaping, which suggests some post-analysis work may have evolved in more than one place over time.

## 6. Supporting Folders Outside the Main App

### `backend/ml/`

This folder contains model-training and dataset-preparation utilities, including:

- cleaning chat training data
- scaling or converting training datasets
- preflight validation
- fine-tune upload assembly
- tests around dataset processing

This looks like an internal ML operations workspace rather than a runtime-serving layer.

### `backend/core/`

Contains reusable, non-HTTP business logic such as:

- momentum calculation
- best time to post
- snapshot shaping
- post comparison
- script generation

These modules are consumed by services and help keep business logic out of route handlers.

### Root `services/`

The root-level `services/` folder contains:

- `ai_post_analysis.py`
- `post_ai_cache_repository.py`
- `post_insights.py`
- `signal_engine.py`

These modules are internally coherent and fairly clean, but their location is notable because the main app already has `backend/app/services/`. That makes this folder feel like either:

- a legacy pre-refactor service layer
- a standalone POC subsystem
- or a parallel implementation that has not yet been fully folded into `backend/app/`

This is worth calling out explicitly during onboarding because a new contributor could easily assume all service code lives in one place.

## 7. Infrastructure and Deployment

### Database

The backend supports async and sync SQLAlchemy access through [backend/app/infra/database.py](../backend/app/infra/database.py).

Default database URL:

- `postgresql+asyncpg://postgres:postgres@localhost:5432/creonnect`

Notable behavior:

- async and sync URLs are derived from the same `DATABASE_URL`
- pgvector is initialized automatically on PostgreSQL when available
- startup database initialization is non-fatal by default

That last point is important: the app can start in a degraded mode even when DB setup fails.

### Redis and RQ

Redis is used for background job execution and related state. The worker entrypoint is [backend/app/workers/rq_worker.py](../backend/app/workers/rq_worker.py).

Configured queues in the worker:

- `account-analysis`
- `embedding-ingestion`

### Docker

The root [Dockerfile](../Dockerfile) builds a Python 3.11 image, installs both root and backend dependency files, exposes port `8000`, and runs:

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 2 --log-level info
```

### GitHub Actions

The repo includes CI/CD workflows under `.github/workflows/` for:

- anti-gravity regression tests
- CodeRabbit-to-Codex automation
- staging deployment to AWS ECS/ECR

This shows the repository is not only a prototype; it has at least some operational deployment shape.

## 8. Dependencies and Setup Notes

There are two Python dependency manifests:

- [backend/requirements.txt](../backend/requirements.txt)
- [requirements.txt](../requirements.txt)

Important note:

- the root `requirements.txt` is encoded as UTF-16 little-endian
- `backend/requirements.txt` is standard ASCII text

This is not necessarily wrong, but it is unusual and worth documenting because tooling sometimes assumes UTF-8 or ASCII for requirements files.

Frontend dependencies are lightweight and centered around:

- React 18
- React Router
- Recharts
- Vite

Backend dependencies include:

- FastAPI
- SQLAlchemy
- Redis / RQ
- OpenAI
- Torch / torchvision
- sentence-transformers
- pgvector

## 9. Current Strengths

The folder shows several healthy signs:

- the main backend is reasonably well layered
- analytics, AI, API, infra, domain, and worker concerns are separated
- there is meaningful automated test coverage
- background jobs and deployment workflows exist
- synthetic/demo paths make local development easier
- creator discovery and brand matching already have a documented domain model

## 10. Current Codebase Caveats

These are the main caveats a new engineer should know up front.

### Mixed maturity levels

The repository contains production-oriented code, POC scripts, experiments, local artifacts, and older standalone modules in the same top-level tree.

### Two service layers

There is a clear `backend/app/services/` layer, but there is also a root `services/` folder with overlapping naming. This is the largest structural ambiguity in the repo.

### Demo and production logic are intertwined

Some flows, especially dashboard assembly, deliberately fall back to synthetic data. That is practical for development, but it means endpoint behavior can vary materially based on auth/data availability.

### Generated and scratch files live in the repo root

Files like local results, diagnostics output, and temp JSON artifacts are present at the top level. That increases noise when trying to identify the real application boundary.

### Documentation is present but fragmented

The repo already has useful docs, but they are specialized by feature rather than being a single onboarding document.

## 11. Recommended Mental Model for Contributors

If you are new to this repository, the safest way to navigate it is:

1. Start with [backend/main.py](../backend/main.py)
2. Follow the routers in `backend/app/api/`
3. Trace orchestration in `backend/app/services/`
4. Look at scoring logic in `backend/app/analytics/`
5. Use `backend/app/infra/` to understand persistence and queueing
6. Treat `internal_tools/`, `experimental/`, and root `services/` as secondary until the main app path is clear

## 12. Practical Start Points

For common goals, these are the best entry files:

- Backend boot: [backend/main.py](../backend/main.py)
- Dashboard flow: [backend/app/services/dashboard_service.py](../backend/app/services/dashboard_service.py)
- Brand campaign flow: [backend/app/api/campaign_routes.py](../backend/app/api/campaign_routes.py)
- Brand scoring core: [backend/app/analytics/brand_match_engine.py](../backend/app/analytics/brand_match_engine.py)
- Background jobs: [backend/app/workers/rq_worker.py](../backend/app/workers/rq_worker.py)
- Database and pgvector: [backend/app/infra/database.py](../backend/app/infra/database.py) and [backend/app/infra/models.py](../backend/app/infra/models.py)
- Frontend routes: [frontend/src/App.jsx](../frontend/src/App.jsx)
- Frontend dashboard page: [frontend/src/pages/Dashboard.jsx](../frontend/src/pages/Dashboard.jsx)

## 13. Bottom Line

This repository is best understood as a creator-intelligence platform codebase with four concurrent personalities:

- a production-leaning FastAPI backend
- a lightweight React frontend
- an internal analytics and ML experimentation workspace
- a POC/operations sandbox with scripts, fixtures, and legacy service modules

The center of gravity is clearly `backend/app/`. Everything else becomes easier to understand once that is treated as the main application boundary.
