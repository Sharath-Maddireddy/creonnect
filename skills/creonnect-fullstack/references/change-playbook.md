# Change Playbook

## Default assumptions

- Product-facing work usually belongs under `backend/app/` or `frontend/src/`.
- `internal_tools/` is safe for diagnostics and fixture-based debugging, but it is not the product boundary.
- `experimental/` should not be used for product fixes unless explicitly requested.
- Root-level loose output files are not source-of-truth inputs.

## Fast path for common tasks

### Backend API change

1. Open the route in `backend/app/api/`.
2. Open the called service in `backend/app/services/`.
3. Open downstream analytics, AI, or infra modules the service depends on.
4. Update or add narrow tests in `backend/app/tests/`.

### Frontend page change

1. Open `frontend/src/App.jsx`.
2. Open the page component under `frontend/src/pages/`.
3. Confirm which API payload it consumes.
4. Update backend contract only if the user asked for behavior changes.
5. Validate with `npm run build` when possible.

### Analytics regression

1. Start in `backend/app/analytics/`.
2. Confirm domain model expectations in `backend/app/domain/`.
3. Check any wrapper service in `backend/app/services/`.
4. Run the narrow relevant test file first.

### Infra or queue issue

1. Read `backend/app/infra/database.py`, `rq_queue.py`, and `redis_client.py`.
2. Check `backend/app/workers/rq_worker.py` and any `*_jobs.py` service.
3. Keep startup, session, and env-var assumptions aligned with `backend/main.py`.

## Useful validation commands

Run from repo root unless the task clearly needs otherwise.

Backend tests:

```bash
pytest backend/app/tests/test_main.py
pytest backend/app/tests/test_dashboard_service.py
pytest backend/app/tests/test_brand_match_engine.py
pytest backend/ml/tests/test_run_dataset_pipeline.py
```

Whole configured test suite:

```bash
pytest
```

Frontend build:

```bash
cd frontend && npm run build
```

Backend dev server:

```bash
uvicorn backend.main:app --reload
```

RQ worker:

```bash
python -m backend.app.workers.rq_worker
```

## Dev and diagnostic helpers

Useful only when the request needs fixtures, smoke runs, or debugging:

- `internal_tools/run_smoke_test.py`
- `internal_tools/run_profile_analysis.py`
- `internal_tools/analyze_user_post.py`
- `internal_tools/verify_e2e.py`

These are support tools, not the primary runtime.

## Environment variables worth checking

- `OPENAI_API_KEY`
- `LLM_MODEL_NAME`
- `DATABASE_URL`
- `BRAND_API_KEY`
- `GEMINI_API_KEY`
- `CREONNECT_SESSION_SECRET`
- `CORS_ALLOWED_ORIGINS`
- Instagram OAuth variables from `README.md`

If a bug looks environment-specific, verify these before changing code.
