# Prompt Assistant PRD

## Summary

Prompt Assistant is an account-aware creative copilot in the Content Suggestions right rail. It helps a creator turn the latest persisted trend analysis into practical hooks, formats, content angles, and next steps without inventing data.

## Problem

Creators can see recommended content angles but still need help adapting them to a specific request, such as creating a no-face reel or a carousel hook. The current compact assistant UI needs a reliable backend contract, clear loading/error states, and answers grounded in the creator's current analysis.

## Goals

- Answer concise creator questions using the latest stored trend analysis for the active account.
- Ground responses in persisted trends, recommendations, content gaps, niche, and relevant saved/generated ideas.
- Never present invented trend names, performance metrics, Instagram audio titles, or account facts as real data.
- Provide useful next actions from the existing workflow, such as generating full ideas or opening a matched idea.
- Keep the right-rail interaction fast and readable on desktop and mobile.

## Non-Goals

- General-purpose chat or long-running conversation memory.
- Publishing, scheduling, or editing content directly from chat in the first release.
- Claiming access to live Instagram data that has not been fetched and persisted.
- Replacing the full script, caption, or idea-generation tools.

## Users And Jobs

- Creator: "Give me three no-face content angles based on what is trending for me."
- Creator: "Which existing recommendation should I turn into a carousel?"
- Creator: "Give me hooks that fit my highest-opportunity topic."
- Creator: "Explain why this content gap matters and what to post next."

## Source Of Truth

The assistant must use the latest `CreatorTrendResult` for the selected `account_id`:

- `niche_json`
- `global_trends_json`
- `recommendations_json`
- `content_gaps_json`
- `daily_insights_json`
- `opportunity_bullets_json`

Optional context may include a user-selected idea ID or trend topic. The server resolves IDs account-safely before adding their content to the model prompt.

If no persisted analysis exists, return an explicit `analysis_required` response. The UI should offer `Refresh Recommendations`, not a speculative answer.

## Functional Requirements

### Request

- `POST /api/v1/accounts/{account_id}/trends/ai-assistant`
- Request fields: `message`, optional `selected_idea_id`, optional `selected_trend_reference`.
- Validate a non-empty message with a sensible maximum length.
- Rate-limit requests per account and user session.

### Response

- Return `reply`, `grounding`, `actions`, and `status`.
- `grounding` lists the stored trend/recommendation identifiers used for the response.
- `actions` may suggest `generate_ideas`, `open_idea`, `generate_script`, or `generate_caption`; actions are suggestions only in v1.
- Return `analysis_required` when no persisted analysis exists.
- Return a user-safe transient error when the LLM provider is unavailable.

### Grounding Rules

- The system prompt must explicitly prohibit invented statistics, trend names, audio track names, links, and creator facts.
- The model may infer creative suggestions, but must label them as suggestions rather than observed facts.
- Numeric opportunity, reach, audience-match, and timing claims must come from supplied stored data.
- Responses should be concise: target 100-180 words plus up to three actions.

### UI

- Replace the `Preview` badge with `AI Assistant` when the backend feature flag is enabled.
- Preserve prompt chips, but use them only to prefill/send the message.
- Show a compact loading state while the request is in progress.
- Render responses in a readable panel with source chips and actionable buttons.
- Show an honest empty state when analysis has not been generated.
- Preserve the user's draft after a failed request.

## Success Metrics

- At least 95% of successful responses contain one or more grounding references.
- Fewer than 1% of responses contain unsupported numerical claims in sampled evaluation.
- Median assistant response time under 5 seconds.
- At least 20% of assistant sessions lead to a downstream generation action.

## Acceptance Criteria

- With stored analysis, a no-face request references relevant stored trends or recommendations and returns useful ideas.
- Without stored analysis, the assistant does not answer speculatively and prompts the user to refresh analysis.
- A provider failure shows a retryable error without replacing the user's input.
- The assistant cannot access another account's ideas or trend data.
- No response displays placeholder text or fabricated image/audio/trend facts.
