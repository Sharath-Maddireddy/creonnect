---
name: creonnect-fullstack
description: Use this skill when working on the Creonnect repository for backend APIs, analytics engines, AI flows, RQ jobs, database-backed creator discovery, frontend dashboard pages, internal diagnostics, or cross-layer changes that need repo-specific guidance. This skill helps navigate the production code paths, avoid experimental and legacy traps, choose the right tests, and map user requests to the correct backend, frontend, and infrastructure modules.
---

# Creonnect Fullstack

This skill is the repo-specific onboarding guide for the Creonnect codebase.

Use it when the task involves any of the following:

- changing FastAPI routes, service orchestration, analytics, or AI behavior
- debugging creator dashboard, campaign, post insight, or reel-analysis flows
- updating the React frontend under `frontend/`
- working on database, Redis, RQ worker, or OAuth-related code
- deciding whether a file belongs to the main product, internal tooling, or experiments

Do not assume the whole repo is equally production-facing. Start with the primary application boundary, then branch outward only if the task clearly requires it.

## First-pass workflow

1. Read [references/repo-map.md](references/repo-map.md) to orient yourself.
2. Read [references/runtime-flows.md](references/runtime-flows.md) for the relevant feature path.
3. Read [references/change-playbook.md](references/change-playbook.md) before editing or validating.
4. Open the exact entrypoint files named in those references before making assumptions.

## Primary product boundary

Treat these areas as the main application unless the request explicitly points elsewhere:

- `backend/main.py`: backend entrypoint and router registration
- `backend/app/api/`: FastAPI route modules
- `backend/app/services/`: application orchestration and job flows
- `backend/app/analytics/`: scoring engines and deterministic analytics
- `backend/app/ai/`: prompts, LLM integration, RAG, and AI helpers
- `backend/app/domain/`: shared typed models
- `backend/app/infra/`: database, Redis, queue, token storage
- `backend/app/ingestion/`: Instagram OAuth and mapping
- `backend/app/workers/`: RQ workers and scheduled jobs
- `frontend/src/`: React app and pages

## Secondary and caution areas

- `internal_tools/`: dev-only scripts, diagnostics, fixtures, and artifacts
- `backend/ml/` and `backend/data/`: dataset preparation and fine-tuning utilities
- root `services/`: older or parallel logic that is not the clearest mainline path
- `experimental/`: research or prototype work, not the default place for product changes

Do not move work into `experimental/` or root-level ad hoc scripts unless the user explicitly asks for experimental work.

## Reading strategy by request type

For API and backend feature work:

- Start at `backend/main.py`
- Open the matching route module in `backend/app/api/`
- Follow the call chain into `backend/app/services/`
- Open any analytics or AI modules referenced by that service
- Check nearby tests in `backend/app/tests/`

For analytics and scoring changes:

- Start in `backend/app/analytics/`
- Confirm the domain model outputs in `backend/app/domain/`
- Check service callers to understand how the scores are surfaced
- Run the narrowest relevant tests first

For AI and prompt changes:

- Start in `backend/app/ai/`
- Inspect prompt builders, schemas, and the calling service
- Check guardrail-oriented tests before changing prompt structure

For frontend changes:

- Start in `frontend/src/App.jsx` to confirm the route
- Open the target page under `frontend/src/pages/`
- Trace the API calls back to the corresponding backend route and service
- Preserve existing visual language unless the user asks for redesign

For background job or infra work:

- Read `backend/app/services/account_analysis_jobs.py` or `reel_analysis_jobs.py`
- Read `backend/app/workers/rq_worker.py`
- Read `backend/app/infra/rq_queue.py`, `redis_client.py`, and `database.py`

## Validation rules

- Prefer targeted `pytest` runs over broad reruns.
- For frontend-only edits, use the lightest validation available, typically `npm run build` when feasible.
- If a change touches API payload shape, inspect both backend tests and the consuming frontend page.
- If a change touches DB or queue behavior, verify startup and worker assumptions in the infra layer before editing.

See [references/change-playbook.md](references/change-playbook.md) for concrete commands and file-level guidance.

## Useful repo docs

- `README.md`: setup, OAuth, queue usage, and top-level orientation
- `docs/CODEBASE_GUIDE.md`: repository overview and architecture summary
- `docs/Creator_discovery_architecture.md`: creator discovery-specific architecture
- `docs/CREONNECT_AI_GUARDRAILS.md`: AI safety and policy context
- `docs/METRICS_EXPLAINED.md`: score and metric definitions

Load those docs only when the task actually needs them.
