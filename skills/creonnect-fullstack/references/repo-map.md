# Repo Map

## Core application

`backend/` is the main product backend.

- `backend/main.py`: FastAPI app startup, middleware, and router registration
- `backend/app/api/`: HTTP layer
- `backend/app/services/`: orchestration and use-case assembly
- `backend/app/analytics/`: deterministic scoring engines
- `backend/app/ai/`: prompts, schemas, RAG, LLM client, and AI helpers
- `backend/app/domain/`: typed models shared across the backend
- `backend/app/infra/`: SQLAlchemy, pgvector models, Redis, RQ, tokens
- `backend/app/ingestion/`: Instagram OAuth fetch and mapping logic
- `backend/app/workers/`: queue workers and background jobs
- `backend/app/tests/`: main regression suite

`frontend/` is a separate Vite React SPA.

- `frontend/src/App.jsx`: route table
- `frontend/src/pages/Dashboard.jsx`: analytics dashboard
- `frontend/src/pages/BrandCampaign.jsx`: brand campaign workflow
- `frontend/src/pages/SinglePostInsights.jsx`: per-post insights page
- `frontend/src/pages/Callback.jsx`: OAuth callback handling

## Supporting product areas

- `backend/core/`: helper logic such as momentum, snapshots, best-time calculations
- `backend/ml/`: training dataset cleanup, validation, scaling, and upload helpers
- `backend/data/`: datasets and generated training artifacts
- `backend/app/knowledge/`: markdown knowledge files used by retrieval and generation flows

## Non-primary areas

- `internal_tools/`: developer diagnostics, smoke scripts, fixture helpers, generated artifacts
- `experimental/`: prototype or side research
- root `services/`: older or parallel scripts that are not the cleanest application layer
- root loose files like `*_result.json`, `*_output.txt`, `tmp_jobs.json`: local outputs, not canonical sources

## Dependency and runtime signals

Backend dependencies in `backend/requirements.txt` indicate the main stack:

- FastAPI + Uvicorn
- SQLAlchemy 2
- asyncpg + psycopg2
- pgvector
- Redis + RQ
- OpenAI
- Torch + torchvision

Frontend stack from `frontend/package.json`:

- React 18
- React Router 6
- Recharts
- Vite 5

## Test layout

`pytest.ini` points to:

- `backend/app/tests`
- `backend/ml/tests`

Default rule: if you change backend logic, there is a good chance the authoritative regression lives in one of those two test directories rather than in a root-level ad hoc script.
