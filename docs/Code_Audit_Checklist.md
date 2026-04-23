# Creonnect Code Audit Checklist

Because the codebase is too large for automated tools like Code Rabbit to ingest all at once, the best strategy is to audit the architecture **layer by layer** or **domain by domain**. 

You can use this document to track your progress as you sit with your backend developer.

## 1. Domain Models Layer (Data Structures)
*The foundation of the app. Reviewing this first ensures you agree on how data is shaped.*
- [ ] `backend/app/domain/post_models.py` (Core metrics, derived metrics, API schemas)
- [ ] `backend/app/domain/database_models.py` (If applicable, any other domain entities)

## 2. Infrastructure Layer (Database & Caching)
*How data persists and moves around.*
- [ ] `backend/app/infra/models.py` (PostgreSQL schemas, `pgvector` implementation)
- [ ] `backend/app/infra/database.py` (SQLAlchemy setup, connection pooling)
- [ ] `backend/app/infra/redis_client.py` (Redis caching and rate-limiting scripts)
- [ ] `backend/app/infra/rq_queue.py` (Queue configurations)

## 3. AI & Prompts Layer (The Brain)
*The logic that drives the product's value.*
- [ ] `backend/app/ai/prompts.py` (The exact instructions sent to `creonnect-v2`)
- [ ] `backend/app/ai/schemas.py` (Pydantic models enforcing JSON output from AI)
- [ ] `backend/app/analytics/reel_gemini_engine.py` (Vision and video analysis)
- [ ] `backend/app/analytics/reel_audio_engine.py` (Audio grading)

## 4. Background Workers (Async Jobs)
*The heavy lifters. This is where the core business logic executes.*
- [ ] `backend/app/services/account_analysis_jobs.py` (Orchestrates the scrape -> AI pipeline)
- [ ] `backend/app/services/reel_analysis_jobs.py` (Video processing)
- [ ] `backend/app/workers/rq_worker.py` (The entry point for the worker process)

## 5. API Routing Layer (Endpoints)
*The front door for the frontend.*
- [ ] `backend/app/api/account_analysis_routes.py` (Triggering analysis)
- [ ] `backend/app/api/campaign_routes.py` (Brand matchmaking endpoints)
- [ ] `backend/app/api/dashboard_routes.py` (Data fetching for the UI)

---

### Pro-Tip for Reviewing with AI
Instead of reading every line manually, you can ask me to perform targeted audits on specific files. For example:
* *"Review `account_analysis_jobs.py` and look for any race conditions or memory leaks."*
* *"Audit `infra/models.py` to ensure our pgvector indexes are optimized for cosine similarity."*
