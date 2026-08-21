# Pending Fixes

Verified snapshot: 2026-08-13

This is the working engineering backlog for confirmed defects and unresolved
production risks. Keep proposed features separate from confirmed bugs, and
re-verify each item against the live code before editing it.

## P0 - Release hygiene

### 1. Separate and review the current worktree

- Current snapshot contains 34 tracked files with content changes and 55
  untracked entries.
- Several untracked entries are local scripts, generated data, test artifacts,
  and image assets. Some may be useful and must not be deleted blindly.
- Split work into feature-specific commits and check local artifacts for secrets
  before pushing.

Done when:

- Every changed or untracked file is intentionally kept, ignored, archived, or
  removed.
- Each deliverable has a bounded diff and its relevant tests pass.
- No credentials, private datasets, generated media, or local database files are
  staged.

## P1 - Security and correctness

### 2. Block redirect-based SSRF for inline image vision

Status: fixed locally on 2026-08-13; not committed or deployed.

Evidence:

- `backend/app/services/ai_analysis_service.py` validates the initial hostname,
  but `_download_vision_media` uses `follow_redirects=True`.
- Redirect destinations are not validated before HTTPX connects.
- DNS validation and the actual connection perform separate DNS resolutions.

Implemented:

- Disable automatic redirects.
- Validate every allowed redirect destination with a strict hop limit.
- Preserve content-type and 15 MB limits.
- Reject non-global addresses, including mixed public/private DNS results and
  carrier-grade NAT space.

Verification:

- Focused downloader coverage: 10 passed.
- Covers private and mixed DNS answers, private redirect targets, relative
  redirects, missing `Location`, redirect limits, size limits, content types,
  and normal public images.
- Connect-time DNS pinning is now covered by the shared policy in item 3.

### 3. Close residual DNS-rebinding gaps in remote fetchers

Status: fixed locally on 2026-08-13; not committed or deployed.

Evidence:

- `backend/app/analytics/reel_gemini_engine.py` explicitly documents that its
  pre-resolution cannot prevent HTTPX from resolving a different address when
  connecting.
- `backend/app/services/creator_image_source_service.py` uses the same
  pre-resolution pattern.

Required fix:

- Adopt one shared, audited outbound-media policy.
- Prefer verified host allowlists where the production CDN contract permits it;
  otherwise enforce the validated IP at connection time.

Local implementation:

- Added one shared outbound-media resolver for Reel, inline-vision, and Creator
  image downloads.
- Rejects credentials and any non-global or mixed DNS answer, then replaces the
  connection hostname with the validated numeric IP.
- Preserves the original hostname in the HTTP `Host` header and HTTPX/httpcore
  `sni_hostname` extension so HTTPS certificate validation remains intact.
- Revalidates each Reel/vision redirect and disables keep-alive for those
  multi-hop clients, preventing TLS connection reuse between different
  hostnames that resolve to the same IP.
- Creator image fetching now also ignores proxy environment variables.

Local validation:

- Focused outbound-media, Reel, inline-vision, and Creator tests: `42 passed`.
- Ordinary backend regression suite after this fix: `581 passed`, with the same
  3 existing deprecation warnings.

### 4. Make background-job idempotency atomic

Status: fixed locally on 2026-08-13; not committed, deployed, or applied to the
production database.

Evidence:

- `BackgroundJob` has indexes but no database-level atomic idempotency guard.
- Callers perform a lookup followed by a separate insert, allowing concurrent
  requests to create duplicate paid work.

Required fix:

- Define idempotency semantics per queue before adding a constraint; some queues
  must allow legitimate reruns.
- Implement an atomic insert/upsert or a dedicated idempotency record.
- Handle the losing concurrent request by returning the existing job.

Done when a real concurrency test proves that two matching requests produce one
billable job without blocking valid retries or reruns.

Local implementation:

- Added a nullable database-enforced idempotency claim separate from
  `payload_hash`, so queue-specific rerun rules remain possible.
- Creator-image keys permanently resolve to their original job, including
  terminal jobs. Deterministic-filter claims are released after failure so a
  real retry can create new work.
- Losing concurrent requests return the winning job and do not schedule a
  second background task.
- Added an idempotent Alembic migration that backfills one canonical claim per
  existing key and concurrency/regression coverage.

Local validation:

- `python -m pytest backend/app/tests/test_image_editor.py backend/app/tests/test_creator_image_editor.py backend/app/tests/test_background_job_idempotency.py backend/app/tests/test_background_job_idempotency_migration.py -o addopts='' -q`
- Result: `24 passed`.

### 5. Define and enforce Reel job ownership

Evidence:

- `backend/app/api/reel_analysis_routes.py` authenticates with a shared service
  API key.
- `backend/app/services/reel_analysis_jobs.py` stores no tenant or account
  identity with a Reel job.

Required decision:

- Creonnect-BD must provide the authoritative actor/account identity.
- Bind enqueue and status reads to that identity without trusting a
  client-supplied account ID by itself.

Done when cross-tenant reads return 404/403 and ownership tests cover enqueue,
polling, failure results, and leaked job IDs.

### 6. Add service-to-service authentication for trend routes

Evidence:

- `/api/v1/accounts/{account_id}/trends*` currently requires an Instagram
  session cookie through `require_current_account`.
- The routes do not accept the existing internal HMAC contract or
  `BRAND_API_KEY`, so environment variables alone cannot let Creonnect-BD call
  them safely.

Required fix:

- Add a bounded internal trend API authenticated with the shared internal HMAC.
- Carry an authoritative actor/account identity and preserve ownership checks.
- Keep browser session authentication on the public route.

### 7. Align production Redis authentication

Evidence:

- `docker-compose.prod.yml` starts Redis without `--requirepass`.
- The API uses a passwordless Redis URL while the worker URL includes
  `REDIS_PASSWORD`.

Required fix:

- Choose one production authentication model and configure Redis, API, and all
  workers consistently.
- Add a startup connectivity check that does not log credentials.

## P2 - Reliability and deployment

### 8. Migrate trend and content-suggestion jobs to SQS

Status: deferred by product decision on 2026-08-13. Production will use SQS
only; do not add an RQ worker as the final deployment solution.

Evidence:

- Trend refreshes and content suggestions enqueue directly to RQ.
- The production Compose worker launches `backend.app.workers.sqs_worker`.
- Its configured queue list does not include `trend-analysis` or
  `content-suggestions`.

Required future fix:

- Move both job families onto the existing SQS abstraction.
- Add queue URLs, registered SQS handlers, worker dispatch coverage, retries,
  timeouts, and status persistence.
- Monitor SQS queue depth, failures, dead-letter messages, and job latency.

### 9. Move Creator Image Editor generation to a durable queue

Evidence:

- `backend/app/api/creator_image_editor_routes.py` schedules generation using
  FastAPI `BackgroundTasks`.
- API restarts convert interrupted work into `worker_restarted` failures rather
  than resuming it.

Required fix:

- Enqueue generation to a durable worker.
- Preserve account ownership, cancellation, retry payload privacy, progress,
  timeout handling, and idempotency behavior.

### 10. Add the missing formal trend-result migration

Status: fixed locally on 2026-08-13; not committed, deployed, or applied to the
configured project database.

Evidence:

- `weekly_opportunity_json` exists in the SQLAlchemy model and runtime
  compatibility logic.
- No Alembic revision adds that column.

Implemented:

- Added revision `20260813_weekly_trend` after the previous single head.
- Upgrade and downgrade tolerate the startup compatibility code having already
  added the column.
- Temporary-database coverage proves repeated upgrade and downgrade behavior.

Verification:

- Alembic reports exactly one head: `20260813_weekly_trend`.
- Migration test: 1 passed.
- Migration and nearby trend regression set: 70 passed.
- A real staging upgrade from the production schema remains part of item 12.

### 11. Validate the Creonnect-BD integration against the real service

Evidence:

- The Python client assumes connection, posts, creator-profile, account-insight,
  and AI-analysis endpoint contracts.
- Unit tests cannot verify the separate service, stored Instagram token,
  production authentication, or Meta eligibility behavior.

Done when staging verifies request signing/authentication, account ownership,
pagination, normalized fields, unavailable insights, timeouts, and persistence
back to Creonnect-BD.

### 12. Complete release-level verification

Local status on 2026-08-13:

- Ordinary backend regression suite: 581 passed with 3 deprecation warnings.
- Stale campaign rate-limit, post-ownership, ML fixture, brand-match fixture,
  and S4 provider-isolation tests were corrected before the green run.
- No external S4 provider call is made by the S4/S6 integration test now.
- Excluded from this baseline: seven intentional stress/antigravity suites, the
  RQ orchestration file deferred by the SQS-only decision, and
  `test_snapshot_flow.py`, which is a helper module containing no tests.

- Run the full backend suite from the project virtual environment.
- Apply migrations to a clean database and a production-like existing schema.
- Smoke-test API, Redis, RQ workers, SQS workers, and external integrations.
- Replace the RQ-specific smoke requirement with SQS coverage when item 8 is
  implemented.
- Verify the real production frontend contract separately; the local React
  frontend is reference-only.

### 13. Resolve single-post test and implementation drift

Status: fixed locally on 2026-08-13; not committed or deployed.

Evidence found while validating item 2:

- Three tests monkeypatch `_repair_gemini_vision_json` or
  `_repair_openai_vision_json`, but those functions no longer exist.
- One REST fallback test calls a dependency-injected route directly without a
  concrete `current_user`, leaving FastAPI's `Depends` marker in its place.

Resolution:

- Tests now match the implemented one-retry contract: malformed or empty output
  triggers one fresh provider request with the simplified JSON prompt.
- Removed stale references to deleted provider-specific repair helpers.
- The REST queue-failure test now supplies an authenticated user and verifies a
  `503`; it also proves expensive inline analysis does not run in the API
  process.
- The internal gRPC path retains and tests its intentional inline fallback.

Verification:

- Complete single-post and gRPC files: 21 passed.
- Nearby single-post and vision regression set: 24 passed.

## P3 - Planned improvements, not current defects

- Compress Reel analysis copies before Gemini upload while preserving originals.
- Add durable Reel cache/deduplication using stable media hashes.
- Record bytes, duration, provider tokens, latency, retries, worker time, error
  reasons, and estimated cost.
- Complete remaining Creator Image Editor production-frontend acceptance work.

## Confirmed completed work

Do not reopen these without new evidence:

- Public background-job responses no longer expose private `payload` data.
- Creator Image Editor retry reads an ownership-checked deep copy of persisted
  payload data.
- Reel downloads reject private/mixed DNS answers and validate manual redirects
  with a three-hop limit; the residual DNS-rebinding limitation remains item 3.
- Requirements encoding was normalized to UTF-8.
- Verified-unused frontend CSS was removed and the frontend build passed at the
  time of cleanup.
- Single-post malformed-output and REST queue-failure tests match the current
  simplified-retry and `503` contracts.
