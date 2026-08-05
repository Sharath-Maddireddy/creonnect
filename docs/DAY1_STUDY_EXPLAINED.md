# Day 1 Study Guide (Explained)

This is a practical walkthrough for Day 1 files so you can learn the codebase with confidence.

Primary goal for Day 1:

- Understand how the app starts.
- Understand how auth/rate-limiting is enforced.
- Understand how one request reaches business logic.

Files covered:

- `backend/main.py`
- `backend/app/api/campaign_routes.py`
- `backend/app/api/auth.py`
- `backend/app/api/rate_limiter.py`

---

## 1) `backend/main.py` (App bootstrap + runtime guardrails)

### Why this file exists

`main.py` is the backend entrypoint. It wires app startup, middleware, routers, and health checks.

### What to read in order

1. Environment loading

- `load_app_env(override=False)`
- Purpose: load env vars before router/service initialization.

2. Security helper functions

- `_is_production_environment()`
- `_resolve_session_secret()`
- `_validate_internal_hmac_secret_configuration()`
- `_validate_brand_api_key_configuration()`

What to understand:

- In production, weak/missing secrets can fail startup.
- In dev/test, app can continue with warnings for easier local iteration.

3. Lifespan hook

- `_app_lifespan(...)`

What happens at startup:

- app state flags set (`brand_api_key_configured`, `internal_hmac_secret_configured`, `vision_enabled`)
- DB engines initialized
- DB init called
- gRPC analysis server started

What happens at shutdown:

- gRPC analysis server stopped

4. FastAPI instance + middleware

- CORS middleware
- Session middleware

Why it matters:

- CORS controls browser origins.
- Session middleware needs a safe secret in production.

5. Router registration

- `app.include_router(...)` calls

This is where routes become live endpoints.

### Day 1 output you should write yourself

- A 6-step startup sequence in your own words.
- One paragraph: "What must be correctly configured in prod before app boot?"

---

## 2) `backend/app/api/campaign_routes.py` (Campaign API surface)

### Why this file exists

Defines HTTP endpoints for brand campaign operations (legacy and new tool-calling path).

### Key concepts in this file

1. Request/response models

Look at classes like:

- `CampaignDiscoverRequest`
- `BrandChatRequest`
- `BrandChatResponse`

Purpose:

- Validate inputs (`Field(...)`, min/max length)
- Keep API contracts explicit and stable

2. Dependency-based protection

- `_rate_limit_by_api_key(...)`
- `Depends(_rate_limit_by_api_key)` on routes

This chains:

- API key verification
- Rate limit enforcement

3. Route responsibilities

- `/discover`: legacy single-shot discovery path
- `/chat`: new tool-calling conversational path
- `/match`: structured manual match
- `/lookalikes/{account_id}`: lookalike retrieval

Important architectural note:

- Routes should remain thin.
- Real logic should live in services.

4. Error handling pattern

- Route catches unexpected errors
- Logs with `logger.exception(...)`
- Returns HTTP 500 with controlled message

### Day 1 output you should write yourself

For `/api/brand/campaign/chat`, draw:

- Request JSON -> request model validation -> dependencies -> service call -> response model

---

## 3) `backend/app/api/auth.py` (Access control boundary)

### Why this file exists

Centralizes API key verification behavior used by protected endpoints.

### What to focus on

- How API key is extracted from headers.
- How configured key is compared.
- Which errors are raised on missing/invalid key.

Why it matters:

- This file is a security boundary. Bugs here can expose private endpoints.

### Questions to answer after reading

1. What header name is expected from clients?
2. What status code is returned when key is invalid?
3. Is behavior different in dev/test vs production?

---

## 4) `backend/app/api/rate_limiter.py` (Abuse protection + graceful fallback)

### Why this file exists

Protects endpoints from burst abuse/spam.

### What to focus on

- In-memory limiter behavior and bucket semantics.
- Redis-backed path (if enabled) and fallback behavior when Redis is unavailable.
- Reset behavior used by tests.

Why it matters:

- Reliability: requests should still be handled safely even if Redis is down.
- Predictability: limits must be consistent for same API key/client.

### Questions to answer after reading

1. What is the limit window unit (seconds/minutes)?
2. What happens when Redis errors occur?
3. How do tests isolate rate limiter state?

---

## 5) One complete request trace (Day 1 exercise)

Trace this endpoint end-to-end:

- `POST /api/brand/campaign/chat`

Expected sequence:

1. FastAPI receives request.
2. Pydantic validates `BrandChatRequest`.
3. `Depends(_rate_limit_by_api_key)` runs.
4. API key verification happens.
5. Rate limit check happens.
6. Route calls `brand_chat_discover_service(...)`.
7. Service result is mapped into `BrandChatResponse`.
8. Response JSON returned.

If any error happens in service:

- route logs exception
- route returns HTTP 500 with standard message

---

## 6) Day 1 mini checklist

Mark each only when you can explain without opening code:

- [ ] I can explain app startup sequence in `main.py`.
- [ ] I can explain how a route is protected (auth + rate limit).
- [ ] I can explain why request/response models exist.
- [ ] I can trace `/chat` from HTTP to service call.
- [ ] I can explain where unexpected route errors are handled.

---

## 7) Suggested 90-minute Day 1 schedule

- 20 min: `main.py`
- 25 min: `campaign_routes.py`
- 15 min: `auth.py`
- 15 min: `rate_limiter.py`
- 15 min: write your own notes + draw one flow

If you want next, I will make a Day 2 explained document with the same structure.
