# Runtime Flows

## 1. Backend startup

Main entrypoint: `backend/main.py`

Key startup behavior:

- loads environment variables
- resolves session secret and CORS origins
- validates `BRAND_API_KEY`
- flags Gemini vision availability from `GEMINI_API_KEY`
- initializes SQLAlchemy engines via `backend/app/infra/database.py`
- calls `init_db()` and registers routers

When debugging startup issues, inspect:

- `backend/main.py`
- `backend/app/infra/database.py`
- `backend/app/infra/models.py`

## 2. Dashboard and analytics flow

Primary route: `backend/app/api/dashboard.py`

Main service path:

- `creator_analytics()` -> `build_creator_analytics()`
- `creator_dashboard()` -> `build_creator_dashboard()`

Core logic lives in `backend/app/services/dashboard_service.py`.

Important behaviors:

- uses Instagram OAuth data when a stored token exists
- otherwise falls back to synthetic demo data
- runs niche detection, growth scoring, post analysis, momentum, posting-time heuristics, and RAG-backed action-plan generation
- assembles chart-friendly payloads for the frontend

Likely companion files:

- `backend/app/ingestion/instagram_oauth.py`
- `backend/app/ingestion/instagram_mapper.py`
- `backend/app/ai/niche.py`
- `backend/app/ai/growth_score.py`
- `backend/app/ai/post_insights.py`
- `backend/app/ai/rag.py`
- `backend/core/momentum.py`
- `backend/core/best_time.py`

## 3. Account analysis and scoring flow

The deterministic account-health wrapper is in `backend/app/services/account_analysis_service.py`.

It:

- fingerprints post insight payloads
- caches account-health results in memory
- delegates actual score computation to `backend/app/analytics/account_health_engine.py`

Use this path when a task mentions:

- account health
- caching of analysis results
- account-level score regressions

## 4. Campaign and brand match flow

Start with:

- `backend/app/api/campaign_routes.py`

Then follow into:

- `backend/app/services/campaign_prompt_service.py`
- `backend/app/services/creator_pool_service.py`
- `backend/app/analytics/brand_match_engine.py`
- `backend/app/infra/models.py` for creator discovery storage concerns

Also load the creator discovery architecture doc when needed:

- `docs/Creator_discovery_architecture.md`

## 5. Post and reel analysis flow

Start with:

- `backend/app/api/post_analysis_routes.py`
- `backend/app/api/reel_analysis_routes.py`

Likely service and engine modules:

- `backend/app/services/post_insights_service.py`
- `backend/app/services/reel_analysis_jobs.py`
- `backend/app/analytics/reel_analysis_service.py`
- `backend/app/analytics/reel_audio_engine.py`
- `backend/app/analytics/reel_gemini_engine.py`
- `backend/app/analytics/vision_s1_engine.py`
- `backend/app/analytics/vision_s3_engine.py`
- `backend/app/analytics/caption_s2_engine.py`
- `backend/app/analytics/s4_audience_relevance_engine.py`
- `backend/app/analytics/s6_brand_safety_engine.py`

When a task mentions the stage scores `S1` to `S6`, begin in `backend/app/analytics/`.

## 6. Frontend flow

Frontend route entrypoint: `frontend/src/App.jsx`

Current routes:

- `/analytics`
- `/brand/campaign`
- `/post/:media_id`
- `/auth/callback`

When debugging UI behavior:

1. open the target page in `frontend/src/pages/`
2. identify the API it calls
3. trace that API to `backend/app/api/`
4. trace onward to the service layer

If the UI looks wrong but the payload is correct, stay in `frontend/`.
If the payload is wrong, fix the backend first.
