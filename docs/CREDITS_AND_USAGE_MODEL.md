# Creonnect Credits & Usage Model

This document defines how Creonnect should account for AI usage, convert provider costs into user-facing credits, and protect margins as new features are added.

It is intended for product, engineering, and finance. The goal is to make billing simple for users while keeping provider usage measurable and controllable internally.

## Goals

- Keep the user-facing system simple: users see credits, not raw tokens.
- Make backend accounting precise enough to handle text, image, video, and speech features.
- Prevent cost spikes from long prompts, large outputs, retries, or heavy reel usage.
- Give product and finance a single framework that can support future features like campaign builder, script generation, and strategy tools.

## Core Decision

Creonnect should use a single shared credit wallet with cost-based deduction.

Users should see:

- Current credit balance
- Credits spent per feature
- Monthly credit refresh date

Users should not see:

- Provider-specific token counts
- Gemini video tokenization details
- Sarvam audio billing details

Internally, credits should represent money-equivalent usage.

Recommended baseline:

- `1 credit = INR 1.00 of billable AI usage`
- Store balances internally in `millicredits`
- `1000 millicredits = 1 credit`

This keeps accounting precise while keeping the UX understandable.

## Why We Should Not Bill on Raw Tokens Alone

Raw text tokens work well for text models, but not for the full Creonnect feature set.

Text features:

- OpenAI text generation exposes input and output tokens directly.
- Campaign builder, caption generation, rewrites, and action plans fit naturally into token accounting.

Non-text features:

- Gemini image/video analysis is not naturally understood as plain text token usage by users.
- Reel cost depends on media duration and provider-specific media accounting, not just prompt length.
- Sarvam STT is billed by audio duration, not transcript token count.

Because of this, Creonnect needs one common accounting layer above all providers:

- Text models -> actual token-based cost
- Vision/video models -> cost estimated from provider pricing or usage metadata
- Speech-to-text -> cost estimated from audio duration
- All of the above -> converted into credits

## High-Level Model

Every request should follow this flow:

1. Identify feature type
2. Collect provider usage signals
3. Estimate raw cost in INR
4. Apply a safety multiplier
5. Round up to a minimum billable credit unit
6. Deduct credits from the user balance
7. Persist a usage ledger row for auditability

Formula:

```text
raw_cost_inr = sum(provider_costs_in_inr)
billable_cost_inr = raw_cost_inr * safety_multiplier
credits_spent = round_up(billable_cost_inr, credit_rounding_unit_inr)
```

Recommended defaults:

- Text-only features: `safety_multiplier = 1.15`
- Image/post analysis: `safety_multiplier = 1.20`
- Reel/video analysis: `safety_multiplier = 1.25`
- Rounding unit: `0.1 credits`

Recommended rounding rule:

```text
rounded_credits = ceil(credits_spent * 10) / 10
```

This prevents abuse through many tiny low-cost requests and gives a predictable UX.

## Provider Cost Formulas

### OpenAI Text

Current default model in code is `gpt-4o-mini` via `backend/app/ai/llm_client.py`.

Formula:

```text
openai_text_cost_usd =
  (input_tokens * input_rate_usd_per_million / 1_000_000) +
  (cached_input_tokens * cached_input_rate_usd_per_million / 1_000_000) +
  (output_tokens * output_rate_usd_per_million / 1_000_000)

openai_text_cost_inr = openai_text_cost_usd * usd_inr_rate
```

Engineering note:

- Persist actual provider usage whenever the API returns it.
- Cache the FX rate daily rather than fetching it per request.

### OpenAI Embeddings

Formula:

```text
embedding_cost_usd =
  (embedding_tokens * embedding_rate_usd_per_million / 1_000_000)

embedding_cost_inr = embedding_cost_usd * usd_inr_rate
```

Use this for creator-pool search, niche embeddings, and any future semantic search features.

### Gemini Image / Video

Preferred formula:

```text
gemini_cost_usd =
  (input_tokens * gemini_input_rate_usd_per_million / 1_000_000) +
  (output_tokens * gemini_output_rate_usd_per_million / 1_000_000)

gemini_cost_inr = gemini_cost_usd * usd_inr_rate
```

Fallback when exact usage metadata is unavailable:

```text
estimated_gemini_input_tokens =
  prompt_tokens + media_tokens
```

For reel/video analysis, use the documented estimate:

```text
media_tokens ~= video_seconds * 300
```

with a default structured output estimate of roughly `250 output tokens` unless actual response usage is available.

### Sarvam Speech-to-Text

Sarvam STT should be treated as duration-based cost.

Formula:

```text
sarvam_cost_inr = ceil(audio_seconds) * (sarvam_hourly_rate_inr / 3600)
```

This is more accurate than trying to infer cost from transcript length.

## Feature-Level Billing Rules

These rules are the starting point for product pricing and can be tuned once real usage data accumulates.

### Text Features

Use actual token-based deduction with a text safety multiplier.

Examples:

- Caption generation
- Text rewrites
- Script generation
- Campaign builder
- Strategy builder
- Action plan generation

Formula:

```text
credits_spent =
  round_up((openai_text_cost_inr) * 1.15, 0.1)
```

### Single Post Analysis

A post may involve:

- Gemini image analysis
- OpenAI text analysis
- Optional embeddings or LLM follow-ups

Formula:

```text
raw_cost_inr =
  gemini_image_cost_inr +
  openai_text_cost_inr +
  embedding_cost_inr_if_any

credits_spent =
  round_up(raw_cost_inr * 1.20, 0.1)
```

### Reel Analysis

A reel may involve:

- Gemini video analysis
- Sarvam STT
- Optional text scoring or post-processing

Formula:

```text
raw_cost_inr =
  gemini_video_cost_inr +
  sarvam_cost_inr +
  openai_text_cost_inr_if_any

credits_spent =
  round_up(raw_cost_inr * 1.25, 0.1)
```

### Account Analysis

Account analysis is a composite feature and should aggregate all child requests.

Formula:

```text
raw_cost_inr =
  sum(child_post_costs) +
  niche_detection_cost +
  creator_intelligence_cost +
  action_plan_cost

credits_spent =
  round_up(raw_cost_inr * 1.20, 0.1)
```

### Creator Search / Semantic Search

These are usually embedding-dominant and cheap.

Formula:

```text
credits_spent =
  round_up((embedding_cost_inr) * 1.10, 0.1)
```

## Product Rules

### What Users See

Users should see:

- `Credits remaining`
- `Credits used this month`
- `Credits spent per action`

Users should not see:

- OpenAI token counters
- Gemini token counters
- Sarvam duration math

### What Product Should Communicate

Recommended UI copy:

- `Credits are deducted based on the compute used by each feature.`
- `Longer or richer analyses may use more credits than shorter requests.`
- `Credits refresh monthly and do not roll over.`

This is honest without overwhelming users with provider-specific pricing details.

## Guardrails

Credits alone are not enough. We should also enforce request-level and account-level controls.

### Request-Level Limits

- Maximum input prompt length
- Maximum uploaded context size
- Maximum output tokens
- Maximum reel duration
- Maximum image/video count per request
- Maximum regeneration count per request

### Monthly / Daily Limits

- Monthly credit cap by plan
- Daily request cap on expensive features
- Maximum full account analyses per month
- Maximum reel analyses per day on free plans

### Safety Controls

- Hard stop when user balance is exhausted
- Optional preflight estimate before dispatching expensive jobs
- Internal kill switch if model spend crosses a daily platform budget

## Implementation Plan

### 1. Add a Usage Ledger

Create a durable usage table with at least:

- `user_id`
- `feature_name`
- `provider`
- `model`
- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `audio_seconds`
- `video_seconds`
- `raw_cost_inr`
- `safety_multiplier`
- `credits_spent`
- `request_id`
- `created_at`

### 2. Add a Credit Balance Store

Each user or workspace should have:

- `balance_millicredits`
- `plan_name`
- `billing_period_start`
- `billing_period_end`

### 3. Add Per-Feature Metering Hooks

Each major service should emit usage events:

- text generation services
- post analysis service
- reel analysis job
- account analysis job
- creator-pool search

### 4. Add a Pricing Config Layer

Keep rates configurable in one place:

- provider rates
- FX rate cache source
- safety multipliers
- rounding unit
- plan limits

This should not be hard-coded in scattered service files.

## Worked Examples

### Example 1: Small Campaign Builder Request

Assume:

- `3000` input tokens
- `800` output tokens
- `gpt-4o-mini`
- `usd_inr_rate = 83`

Then:

```text
cost_usd =
  3000 * 0.15 / 1_000_000 +
  800 * 0.60 / 1_000_000
= 0.00045 + 0.00048
= 0.00093

cost_inr = 0.00093 * 83 = 0.07719
with 15% buffer = 0.08877
rounded = 0.1 credits
```

### Example 2: Heavier Campaign Builder Request

Assume:

- `20000` input tokens
- `4000` output tokens
- `gpt-4o-mini`
- `usd_inr_rate = 83`

Then:

```text
cost_usd =
  20000 * 0.15 / 1_000_000 +
  4000 * 0.60 / 1_000_000
= 0.003 + 0.0024
= 0.0054

cost_inr = 0.0054 * 83 = 0.4482
with 15% buffer = 0.51543
rounded = 0.6 credits
```

### Example 3: Reel Analysis

Assume:

- `45` second reel
- Gemini prompt + media estimate
- Sarvam charged by audio duration

Then:

```text
raw_cost_inr =
  gemini_video_cost_inr +
  sarvam_cost_inr

credits_spent =
  round_up(raw_cost_inr * 1.25, 0.1)
```

The exact value depends on actual model rates and duration, but the accounting shape stays consistent.

## Recommendations for Launch

### Product

- Use one shared monthly credit wallet
- Explain credits as compute-based usage, not token-based billing
- Refresh credits monthly with no rollover at launch

### Engineering

- Meter actual provider usage wherever possible
- Estimate only when provider usage is unavailable
- Log every credit deduction with enough detail to audit and reprice later

### Finance

- Review real average credits per feature after launch
- Reprice only after at least one month of usage data
- Keep a 15% to 25% safety buffer until provider behavior is well understood

## Open Questions

- Should credit balances live at the user level or workspace/team level?
- Do we want to allow negative balances briefly for asynchronous jobs already in flight?
- Should account analysis pre-authorize a maximum credit amount before execution?
- Do we want fixed minimum charges per feature, or only pure metered charging with rounding?

## Canonical Source Files

- `backend/app/ai/llm_client.py`
- `backend/app/services/ai_analysis_service.py`
- `backend/app/services/post_insights_service.py`
- `backend/app/services/reel_analysis_jobs.py`
- `backend/app/analytics/reel_gemini_engine.py`
- `backend/app/analytics/reel_sarvam_engine.py`
- `docs/FINANCIAL_MODEL.md`

## Sources

- OpenAI pricing: https://platform.openai.com/docs/pricing/
- OpenAI model docs: https://platform.openai.com/docs/models/gpt-4o-mini
- Gemini pricing: https://ai.google.dev/gemini-api/docs/pricing
- Gemini video understanding: https://ai.google.dev/gemini-api/docs/video-understanding
- Sarvam pricing: https://www.sarvam.ai/api-pricing
