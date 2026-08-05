# Release Checklist: Tool-Calling + Reliability Hardening

Branch:

- `feat/creator-trend-results`

Scope in this release:

- Tool-calling orchestration flow.
- Tool response envelope standardization.
- New campaign chat endpoint.
- LLM tool-call support in client.
- Reliability/security hardening follow-ups.

## 1) Pre-merge checks

- [ ] `python -m compileall backend/app`
- [ ] `python -m pytest -q backend/app/tests/test_tool_calling_integration.py`
- [ ] `python -m pytest -q backend/app/tests/test_campaign_routes.py`
- [ ] `python -m pytest -q backend/app/tests/test_main.py`

## 2) Security checks

- [ ] API key auth enforced on protected campaign routes.
- [ ] gRPC internal HMAC secret configured and non-placeholder.
- [ ] Redis auth configured for production deployment.
- [ ] No `.env` secrets included in committed files.

## 3) Tool-calling checks

- [ ] `ToolResponse` envelope used by all orchestrator tools.
- [ ] Unknown tool name returns `ToolResponse.error`.
- [ ] Bad argument types return `ToolResponse.error`.
- [ ] Chat loop enforces `MAX_TOOL_CALLS` and forced final response.
- [ ] Tool call audit trail includes `name`, `args`, `latency_ms`.

## 4) CI/CD checks

- [ ] GitHub workflow runs backend tests before Docker build.
- [ ] Test step explicitly disables Redis-backed limiter mode (`RATE_LIMIT_USE_REDIS=false`) unless Redis service is started.
- [ ] Docker image build and push produce expected tags.

## 5) Deployment checks

- [ ] Required env vars present on EC2 (`BRAND_API_KEY`, DB URL, Redis password, session secret, HMAC secret).
- [ ] `/health` endpoint returns `{"status": "ok"}` after deployment.
- [ ] API and worker containers both healthy after rollout.

## 6) Post-deploy spot checks

- [ ] `POST /api/brand/campaign/discover` works (legacy path).
- [ ] `POST /api/brand/campaign/chat` works (tool-calling path).
- [ ] Tool-calling result ranking and dedupe behavior is sane.
- [ ] No spike in tool execution errors in logs.

## 7) Known limitations accepted for this release

- Cost estimation is heuristic-only (`estimate_campaign_cost`) and should be treated as planning guidance.
- CI currently does not provision a Redis service for tests by default; rate limiter uses in-memory mode in CI.
