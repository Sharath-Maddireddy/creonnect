# Creonnect Codebase Learning Guide

This document is for learning the codebase gradually and confidently, especially if parts feel "vibe-coded" right now.

## 1) Big Picture

Creonnect backend is a FastAPI app with these main layers:

- API layer: request validation, auth/rate-limit, route wiring.
- Service layer: business workflows (campaign discovery, chat loop, analysis orchestration).
- Analytics layer: pure scoring/metric engines.
- Infra layer: database sessions/models, queue/redis utilities.
- Workers: async/background processing via SQS/RQ and scheduled jobs.
- AI layer: LLM client, prompts, circuit breaker, tool schemas.

Think of it as:

`API -> Services -> Analytics/Infra -> DB/Queues/LLM`

## 2) Start Here (Entry Points)

### App startup and wiring

Read first:

- `backend/main.py`

What to learn:

- How environment is loaded.
- Lifespan startup tasks (`init_db`, gRPC server start).
- Router registration order.
- Security startup checks (`BRAND_API_KEY`, `CREONNECT_INTERNAL_HMAC_SECRET`).

### API surface

Read these next:

- `backend/app/api/campaign_routes.py`
- `backend/app/api/account_analysis_routes.py`
- `backend/app/api/dashboard.py`
- `backend/app/api/auth.py`
- `backend/app/api/rate_limiter.py`

What to learn:

- Auth dependency pattern.
- Rate limiting behavior.
- Request/response Pydantic models.
- Where each route delegates (service function calls).

## 3) Core Domain Models

Read:

- `backend/app/domain/brand_models.py`
- `backend/app/domain/post_models.py`
- `backend/app/domain/account_models.py`
- `backend/app/domain/tool_response.py`

What to focus on:

- Validation rules in Pydantic models.
- How score outputs are structured (`CreatorMatchScore`).
- Standard tool envelope (`ToolResponse`, `ToolResponseMeta`).

## 4) New Tool-Calling System (Most Important Recent Work)

### Files

- `backend/app/ai/tool_schemas.py`
- `backend/app/services/tool_orchestrator.py`
- `backend/app/services/brand_chat_service.py`
- `backend/app/ai/llm_client.py`
- `backend/app/api/campaign_routes.py` (`POST /api/brand/campaign/chat`)

### Mental model

1. Brand sends prompt to `/api/brand/campaign/chat`.
2. `brand_chat_service.brand_chat_discover(...)` starts an LLM tool loop.
3. LLM chooses tools from `BRAND_DISCOVERY_TOOLS`.
4. `ToolOrchestrator.execute_tool(...)` is the only backend-service dispatch layer.
5. Each tool returns `ToolResponse` with `success/data/ui/meta`.
6. Loop repeats until final natural-language response or `MAX_TOOL_CALLS` limit.

### Why this matters

- Clean separation of "LLM decides" vs "backend executes".
- Safer observability: tool calls are logged with redaction.
- Bounded cost/latency via max tool calls.

## 5) Legacy Campaign Flow (Still Active)

Read:

- `backend/app/services/campaign_prompt_service.py`
- `backend/app/api/campaign_routes.py` (`/discover`, `/match`, `/lookalikes`)

This is the pre-tool-calling flow.

Compare legacy vs new:

- Legacy `/discover`: mostly single-shot extraction + scoring.
- New `/chat`: iterative multi-tool reasoning loop.

## 6) Creator Pool + Matching Engine

Read:

- `backend/app/services/creator_pool_service.py`
- `backend/app/analytics/brand_match_engine.py`
- `backend/app/analytics/audience_quality.py`
- `backend/app/analytics/s6_brand_safety_engine.py`

What to understand:

- How creators are queried and lookalikes are found.
- How match score is built from sub-scores.
- Safety/quality/engagement factors.

## 7) Infra and Data Access

Read:

- `backend/app/infra/database.py`
- `backend/app/infra/models.py`
- `backend/app/services/account_analysis_result_store.py`
- `backend/app/infra/redis_client.py`

Focus:

- Sync session usage patterns.
- ORM model structure.
- Where analysis JSON is stored/retrieved.
- Redis fallback strategy in rate limiting.

## 8) Background Jobs and Workers

Read:

- `backend/app/workers/sqs_worker.py`
- `backend/app/workers/rq_worker.py`
- `backend/app/services/account_analysis_jobs.py`
- `backend/app/services/reel_analysis_jobs.py`
- `backend/app/services/trend_analysis_jobs.py`

What to learn:

- Queue polling, retry, and failure behavior.
- Job orchestration boundaries.
- Worker entrypoints and operational assumptions.

## 9) AI Reliability and Safety

Read:

- `backend/app/ai/llm_client.py`
- `backend/app/ai/circuit_breaker.py`
- `backend/app/ai/prompts.py`
- `backend/app/ai/prompts_brand.py`

Key topics:

- Retry strategy.
- Circuit-breaker behavior.
- Structured/tool outputs.
- Prompt composition and guardrails.

## 10) Security and Production Checks

Read:

- `backend/main.py`
- `backend/app/api/auth.py`
- `backend/app/api/grpc_analysis_server.py`
- `.github/workflows/deploy.yml`
- `docker-compose.prod.yml`

Checklist to internalize:

- API key enforcement on protected routes.
- gRPC HMAC auth requirements.
- Redis auth and env safety.
- CI test behavior before build/deploy.

## 11) Testing Strategy (How to Learn Faster)

Read tests like documentation:

- `backend/app/tests/test_campaign_routes.py`
- `backend/app/tests/test_integration_campaign_ai.py`
- `backend/app/tests/test_tool_calling_integration.py`
- `backend/app/tests/test_brand_match_engine.py`
- `backend/app/tests/test_main.py`

How to use them:

- Pick one feature.
- Read route/service code.
- Read the matching test.
- Run the single test file and inspect assertions.

## 12) Practical Learning Plan (2 Weeks, Part-Time)

### Week 1: Foundations

Day 1-2:

- Read `backend/main.py` and all API route files.
- Draw your own flow map of each endpoint to service.

Day 3-4:

- Read domain models and `brand_match_engine.py`.
- Write down what each score component means.

Day 5-6:

- Read infra (`database.py`, `models.py`, result store).
- Trace one real query path end-to-end.

Day 7:

- Run and study `test_campaign_routes.py` and `test_main.py`.

### Week 2: Tool-calling + workers

Day 8-9:

- Deep-read tool-calling files (`tool_schemas`, `tool_orchestrator`, `brand_chat_service`, `llm_client`).
- Trace one `/chat` request from route to final response.

Day 10-11:

- Read worker/job files.
- Understand retry, visibility timeout, and failure handling.

Day 12:

- Read deploy workflow + docker prod config.
- Identify all env vars required for production.

Day 13-14:

- Revisit tests: `test_tool_calling_integration.py` and one worker-related test.
- Write your own small test for one tool in orchestrator.

## 13) Personal "I Understand It" Checklist

You understand this codebase when you can explain:

- How `/api/brand/campaign/chat` works step-by-step.
- Difference between legacy `/discover` and new `/chat`.
- How tool execution is validated, dispatched, and logged.
- How brand fit scoring is computed and where data comes from.
- What happens if Redis, LLM, or queue components fail.
- Which startup checks protect production from weak config.

## 14) Suggested Next Practice Tasks

When you have free time, do these in order:

1. Add one new read-only tool schema and orchestrator method.
2. Add one integration test for that tool in `test_tool_calling_integration.py`.
3. Add one observability improvement (more precise `meta` or safe logs).
4. Document one endpoint flow using your own words in this file.

---

If this guide helps, we can create "Part 2" with sequence diagrams and a glossary of every important model/field.
## 15) Supporting Docs Added

Use these when you want practical release context:

- `docs/TOOL_CALLING_KNOWN_LIMITATIONS.md`
- `docs/RELEASE_CHECKLIST_TOOL_CALLING.md`
