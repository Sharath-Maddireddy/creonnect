# Prompt Assistant Implementation Plan

## Phase 1: Contract And Grounding

1. Extend `AssistantRequest` with optional `selected_idea_id` and `selected_trend_reference`; add length limits.
2. Replace the plain-string response with typed `status`, `reply`, `grounding`, and `actions` fields.
3. Load `CreatorTrendResult` by `account_id`; account-safely load an optional selected idea.
4. Return `analysis_required` if the trend result is absent or contains no usable trends/recommendations.
5. Build a bounded prompt payload from persisted fields only. Exclude raw unrelated account data and limit list sizes.
6. Add a strict system prompt that distinguishes observed context from creative suggestions and forbids invented facts.

## Phase 2: Reliable Service Layer

1. Move LLM invocation into `prompt_assistant_service.py` so routes only validate, load context, and serialize results.
2. Add timeout, structured logging, and telemetry for requested, completed, failed, and analysis-required outcomes.
3. Add account/session rate limiting and a short response cache keyed by normalized prompt plus analysis version.
4. Parse the LLM response into a constrained JSON schema; reject malformed or unsupported actions.
5. Add a safe error mapper for provider, timeout, validation, and database failures.

## Phase 3: Frontend Experience

1. Replace the current plain reply state with `idle`, `loading`, `success`, `analysis_required`, and `error` states.
2. Send the active account ID and selected context through the typed endpoint contract.
3. Render grounding references as small source chips, not as unverified prose.
4. Render up to three action buttons and route each to the existing modal/workflow.
5. Keep quick prompt chips, disable send while loading, and retain the draft after errors.
6. Add responsive styles that do not reduce text contrast or cause the right rail to overflow.

## Phase 4: Tests And Evaluation

1. Unit-test request/response validation and account-scoped context loading.
2. Add route tests for stored analysis, missing analysis, selected idea ownership, provider failure, and malformed LLM output.
3. Add frontend tests for loading, analysis-required, error retry, source chips, and action clicks.
4. Add prompt evaluation fixtures that detect unsupported statistics, trend names, and audio claims.
5. Run the focused backend suite and `npm run build`; manually test the three prompt chips against a real analyzed account.

## Delivery Order

1. Backend schema, context loader, and analysis-required response.
2. Service extraction, prompt schema, and tests.
3. Frontend state model, source chips, and action buttons.
4. Telemetry, rate limiting, evaluation fixtures, and final QA.

## Definition Of Done

- The assistant only answers from persisted account context plus clearly labeled creative suggestions.
- Missing or stale analysis produces an explicit refresh path.
- Every successful response exposes its grounding references.
- The UI has no placeholder badge, canned reply, fake metric, or silent failure.
- Focused tests and production frontend build pass.
