---
alwaysApply: true
---

# Creonnect project rules

## Scope and workflow

- Treat the Python backend, APIs, database migrations, worker and queue logic, and backend tests as production scope.
- The local React frontend is reference-only unless a task explicitly provides its production contract. Do not claim a UI feature is complete merely because local frontend code changed.
- Before implementing a PRD feature, compare the PRD against the existing code. Identify reusable foundations, gaps, and replacement work.
- Preserve backwards compatibility. Prefer additive endpoints, schemas, and migrations over changing or removing existing behaviour.
- Make the smallest coherent change that solves the request. Do not refactor unrelated files.

## Security

- Never read, print, commit, or expose values from `.env` files, API keys, tokens, cookies, session IDs, database URLs, or cloud credentials.
- Do not put secrets in source code, tests, fixtures, logs, git commits, or documentation.
- Treat Instagram session IDs and OAuth tokens as highly sensitive.
- Do not call production APIs, deploy, alter cloud resources, or access real user data unless explicitly requested.

## Implementation standards

- Keep provider configuration server-side only; never send provider credentials to the frontend.
- Validate API inputs and return structured errors. Do not silently fall back to unsafe or misleading behaviour.
- Preserve immutable original media; generated or transformed media must be stored as derived assets.
- For asynchronous jobs, make state transitions explicit. FastAPI `BackgroundTasks` are not durable after a restart: report recovery and failure states accurately, and use a durable queue for production work.
- Do not invent integrations or endpoints for the separate Creonnect-BD service. Clearly mark that boundary as unimplemented unless its actual contract is available.
- For Reel analysis, use the existing Gemini File API path unless an equivalent video contract is verified. Compression failures must return a structured error; never upload the uncompressed original silently.

## Quality checks

- Inspect `git status` before editing and preserve unrelated existing changes.
- Add or update focused tests for changed backend behaviour.
- Run the smallest relevant test suite using the project `.venv` where available.
- Do not claim tests, provider calls, UI flows, deployments, or production behaviour were verified unless actually run and observed.
- In the final summary, list changed files, tests run and their outcome, and any remaining risks or unverified work.

## Communication

- State assumptions before making a material product or architecture decision.
- When blocked by missing information, report exactly what is needed rather than guessing.
- Keep explanations concise and evidence-based.
