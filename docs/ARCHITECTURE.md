# Creonnect — High-Level Architecture

This document summarizes the main components, data flows, and where to find the implementation for the Creonnect project. It is intended as a single-stop reference for engineers onboarding to the codebase.

## Goals
- Explain how each major component works and interacts.
- Point to the canonical source files to inspect implementation details.
- Describe runtime dependencies, important environment variables, and deployment notes.

## Layout / Components

- Frontend: SPA (Vite) that consumes the backend API. See `frontend/`.
- Backend API: FastAPI application exposing creator dashboards, post analysis, OAuth, and other endpoints. See `backend/main.py` and `backend/app/api/`.
- AI / ML layer: Collection of deterministic analytics (post metrics, benchmarks) and LLM/vision components (LLM client, RAG, prompts, vision helpers) in `backend/app/ai/`.
- Ingestion: Instagram OAuth and Graph ingestion + mappers in `backend/app/ingestion/`.
- Services: Orchestrators and business logic (dashboard, post insights, account intelligence) in `backend/app/services/`.
- Infra helpers: DB, Redis, RQ, token store and SQLAlchemy models in `backend/app/infra/`.
- Internal tools and scripts: Various utilities and diagnostics in `internal_tools/`.
- Docs and knowledge: `docs/` and `backend/app/knowledge/` (used by RAG engine via `backend/app/ai/rag.py`).

## Backend (FastAPI)

Entrypoint:
- `backend/main.py` — constructs the FastAPI app, configures CORS & sessions, initializes DB/Redis features, checks BRAND_API_KEY and vision availability, and mounts routers.

Main routers (in `backend/app/api/`):
- Dashboard: `dashboard.py` — `/api/creator/dashboard`, `/api/creator/analytics`, snapshot and script endpoints.
- Instagram OAuth: `instagram_auth_routes.py` — `/api/auth/instagram/login`, `/api/auth/instagram/callback`, `/api/auth/me`, `/api/auth/logout`.
- Post analysis: `post_analysis_routes.py` — `/api/v1/post-analysis`, `/api/v1/posts/{id}/cringe-summary`, `/api/v1/posts/{id}/insights`.
- Additional routers: `account_analysis_routes.py`, `brand_match_routes.py`, `campaign_routes.py`, `brand_post_analysis_routes.py`, `reel_analysis_routes.py`, etc.

Lifespan and startup:
- `_app_lifespan` in `main.py` sets app state flags, initializes DB engines (`initialize_database_engines`) and runs `init_db()` to create tables and register Postgres vector extension when appropriate.
- Session secret management: `CREONNECT_SESSION_SECRET` is required in production; dev uses an ephemeral secret.

## Services and Business Logic

Key orchestrators:
- `backend/app/services/dashboard_service.py` — assembles the creator dashboard by combining ingestion (Instagram or synthetic demo), analytics, AI modules, RAG action plan, snapshots and time-series.
- `backend/app/services/post_insights_service.py` — deterministic pipeline for single-post derived metrics, benchmark metrics and optional AI analysis (calls into `ai_analysis_service`).
- `backend/app/services/ai_analysis_service.py` (and related) — wraps higher-level AI tasks (caption/vision scoring, predictions, S1–S6 scoring).

Important patterns:
- Deterministic analytics (metrics, benchmarks, content scores) are implemented separately from ML/LLM logic. This keeps core product signals reproducible without external AI calls.
- AI/LLM calls are optional and controlled by flags; fallback deterministic behavior is provided when model or vision APIs are unavailable.

## Ingestion & Mapping

- `backend/app/ingestion/instagram_oauth.py` — builds OAuth flow, exchanges codes for tokens, fetches profile and media using Graph API.
- `backend/app/ingestion/instagram_mapper.py` — maps Graph API payloads into canonical AI input pydantic models:
  - `CreatorProfileAIInput` and `CreatorPostAIInput` (schemas in `backend/app/ai/schemas.py`).
- OAuth tokens are stored via token store helpers in `backend/app/infra/token_store.py` (used by `instagram_auth_routes.py`).

## AI / ML Layer

Core AI components (folder `backend/app/ai/`):
- `schemas.py` — Pydantic models for AI inputs (`CreatorProfileAIInput`, `CreatorPostAIInput`).
- `post_insights.py` — deterministic post metrics and human-readable insights.
- `cringe_analysis.py` — helper heuristics for brand-safety/cringe scoring from vision payloads.
- `llm_client.py` — abstraction over an LLM provider (OpenAI by default) with retries and an `embed()` helper for embeddings.
- `rag.py` — local in-memory RAG engine that chunks markdown in `backend/app/knowledge/` and uses sentence-transformers for embeddings; also generates action plans via LLM with deterministic fallback.
- `prompts.py`, `prompt_builder.py`, `prompts_brand.py` — canonical prompt templates and builders (enforce structured TOON/JSON outputs where required).

AI orchestration:
- Services call into AI modules (for example `dashboard_service` calls `analyze_posts`, `generate_action_plan`, `detect_creator_niche`, `compute_growth_score`).
- Vision (Gemini/OpenAI vision) is optionally enabled by `GEMINI_API_KEY` in environment and gated at startup.

Parsing and fallbacks:
- The system expects structured responses (TOON or JSON) and provides fallback parsers and deterministic rules if parsing or LLM fails.

## Data Stores & Caching

- Primary relational DB: PostgreSQL via SQLAlchemy async engine. Configured by `DATABASE_URL`. See `backend/app/infra/database.py` and `backend/app/infra/models.py`.
  - `init_db()` creates DB tables and ensures the `vector` extension for Postgres when applicable.
- Redis: caching and short-lived payloads, with both sync and async helpers in `backend/app/infra/redis_client.py`.
  - Cringe summaries and post snapshots are saved in Redis (see `post_analysis_routes.py` and `post_snapshot_store.py`).
- RQ / background queue: `backend/app/infra/rq_queue.py` integrates with Redis for background jobs when used.
- Creator pool vectors: project contains a persistent creator embedding store (pgvector) referenced in `backend/app/infra/models.py` and `backend/app/ai/` embedding helpers.

## Frontend

- Located in `frontend/` — a Vite-powered SPA. It consumes the backend API endpoints under `/api/*`.
- CORS allowed origins are configured in environment (`CORS_ALLOWED_ORIGINS`) with sensible defaults for local development.

## Internal Tools & Scripts

- `internal_tools/` contains scripts for diagnostics, data preparation, test utilities, e.g. `populate_redis.py`, `fetch_thumbnail.py`, and various diagnostics used by engineers.

## Configuration & Environment Variables (high-impact)

- `DATABASE_URL` — Async SQLAlchemy URL (e.g. `postgresql+asyncpg://...`). A sync-compat URL is derived automatically for some uses.
- `REDIS_URL` — Redis connection string.
- `OPENAI_API_KEY` — used by `LLMClient` to call OpenAI.
- `GEMINI_API_KEY` — enable vision features when present.
- `CREONNECT_SESSION_SECRET` — session cookie secret (required in production).
- `BRAND_API_KEY` — gates brand-protected endpoints.
- `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_REDIRECT_URI` — for Instagram OAuth.
- Other tuning vars: `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_COMMAND_TIMEOUT`, etc.

## Running Locally (quick)

- Backend (recommended inside a virtualenv):

```powershell
# from repository root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# set env vars (use .env or .env.example as reference)
uvicorn backend.main:app --reload --factory
```

- Frontend:

```bash
cd frontend
npm install
npm run dev
```

(For Windows PowerShell use the platform-appropriate commands.)

## Testing & Development Notes

- The repository contains `conftest.py` and many tests under `backend/app/tests/` and other test utilities.
- `database.reset_database_engines()` and the related async/sync helpers are intended to support tests and test isolation.

## Observability & Logging

- Logging is implemented by `backend/app/utils/logger.py`. Service modules log warnings and errors that are surfaced through FastAPI HTTPExceptions for endpoints.

## Where to Look for Specific Functionality

- OAuth flow: `backend/app/ingestion/instagram_oauth.py` and `backend/app/api/instagram_auth_routes.py`.
- Creator dashboard orchestration: `backend/app/services/dashboard_service.py`.
- Single-post deterministic pipeline: `backend/app/services/post_insights_service.py` and `backend/app/ai/post_insights.py`.
- Vision & cringe analysis: `backend/app/ai/cringe_analysis.py` and S1–S4 prompts in `backend/app/ai/prompts.py`.
- LLM calls and embedding usage: `backend/app/ai/llm_client.py` and embedding consumers across `ai/`.
- RAG and action planner: `backend/app/ai/rag.py` and knowledge markdown in `backend/app/knowledge/` (if present).

## Next Steps (recommended)

1. Document each `backend/app/services/*.py` file with function-level explanations and examples.
2. Create endpoint reference pages (inputs, outputs, example requests) for each router under `backend/app/api/`.
3. Add a `docs/TOC.md` that links all generated documentation pages.
4. Add a contributor guide and runbook for deploying (CI/CD, Docker, infra terraform in `infra/terraform`).

---

This is a first detailed pass of the architecture overview. I will now proceed to document backend services file-by-file (dashboard, post analysis, account analysis).