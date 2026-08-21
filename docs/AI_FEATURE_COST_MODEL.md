# AI Feature Cost Model

**Prepared:** 2026-08-09  
**Pricing last verified:** 2026-08-09  
**Next mandatory review:** before Q4 2026 budgeting, and immediately before changing a production model or provider plan.  
**Purpose:** production budgeting for the AI Analysis, Single-Post AI Analysis, and Trend Recommendations features. Prices are USD list prices and exclude infrastructure, Instagram/Meta access, storage, worker compute, and taxes.

## Scope and pricing baseline

This is a code-path inventory, not an invoice. Actual billing must be calculated from each provider response's usage fields and the pricing of the deployed provider/region.

| Model | Used for | Input / 1M tokens | Cached input / 1M | Output / 1M tokens |
|---|---|---:|---:|---:|
| `gpt-4o-mini` | Text scoring, summaries, creator intelligence, peer rankings, trends | $0.15 | $0.075 | $0.60 |
| `gemini-3.1-flash-lite` | Planned replacement for image and reel vision | $0.25 for text, image, or video; $0.50 audio | $0.025 for text, image, or video; $0.05 audio | $1.50 |
| `text-embedding-3-small` | Creator-search embeddings; not used in the three flows below | $0.02 | — | — |

`text-embedding-3-small` has been independently verified at $0.02 per 1M input tokens. It is not invoked by the three feature paths in this document, but it remains a billable production dependency for creator-search indexing and queries.

The current code defaults to `gpt-4o-mini` and **still names** `gemini-2.5-flash-lite`; this document deliberately prices the planned replacement, `gemini-3.1-flash-lite`. Update the runtime model configuration and constants before the planned October 2026 2.5 retirement. `LLM_MODEL_NAME`, `GEMINI_MODEL`, and Azure deployment variables can override these names at runtime.

### Cost formulas

Use these formulas with provider-reported token counts:

```text
GPT-4o mini request cost = (input_tokens × 0.15 + cached_input_tokens × 0.075
                           + output_tokens × 0.60) / 1,000,000

Gemini 3.1 Flash-Lite request cost = (text/image/video input_tokens × 0.25
                                      + output_tokens × 1.50) / 1,000,000
```

Gemini bills image and video inputs by tokens. The token count depends on the media supplied, so a fixed dollar amount per uploaded image or reel would be misleading. Capture API usage for real costs. Gemini 3.1 Flash-Lite standard rates are 2.5× the previous 2.5 Flash-Lite input rate and 3.75× its output rate, so this migration needs a fresh production measurement.

## Batch API option (50% reduction)

Both providers offer a Batch mode that reduces listed input and output prices by 50%, in exchange for asynchronous processing:

| Model | Standard input/output per 1M | Batch input/output per 1M | Suitability |
|---|---:|---:|---|
| GPT-4o mini | $0.15 / $0.60 | $0.075 / $0.30 | OpenAI Batch completes within 24 hours; suitable only for non-interactive recomputation/backfills |
| Gemini 3.1 Flash-Lite | $0.25 / $1.50 | $0.125 / $0.75 | Suitable for deferred work where the Google Batch completion window is acceptable |

Do not use Batch for a creator waiting for a dashboard or single-post result. Consider it for nightly account-analysis backfills, precomputing analyses after ingestion, re-indexing, or scheduled trend refreshes. The current service code uses synchronous provider calls, so Batch requires a separate deferred-job implementation rather than an environment-variable change.

## Prompt-cache guidance

GPT-4o mini automatically discounts recently reused input prefixes to the cached-input rate shown above. The current S2, S3, S4, and final-analysis prompts are separate and do not intentionally share a sufficiently large common prefix, so the model should not be assumed to receive the discount today.

To make caching measurable and useful:

1. Put stable, shared policy/schema instructions first and keep their wording, order, and formatting byte-for-byte identical.
2. Put task-specific instructions after that stable prefix, and append post caption, metrics, vision output, and other per-post data last.
3. Reuse the same client/model and observe `cached_tokens` in provider usage; do not claim savings until telemetry confirms cache hits.
4. Avoid bloating prompts just to create cacheable text: repeated instructions should be retained only when they improve output quality.

## 1. Single-Post AI Analysis

Entry point: `POST /api/v1/single-post-analysis` → `build_single_post_insights(..., run_ai=True)` → `analyze_single_post_ai`.

For a standard image post with AI enabled, the pipeline makes these calls:

| Step | Provider/model | Calls per post | Output cap in code | What drives input tokens |
|---|---|---:|---:|---|
| Visual analysis (S1) | Gemini 3.1 Flash-Lite (planned) | 1 | Provider default | The image plus the vision prompt |
| Caption effectiveness (S2) | GPT-4o mini | 1 | 1,200 | Caption and scoring prompt |
| Content clarity (S3) | GPT-4o mini | 1 | 1,200 | Caption, vision result, scoring prompt |
| Audience relevance (S4) | GPT-4o mini | 1 | 1,200 | Post and creator category prompt |
| Creator-facing analysis | GPT-4o mini | 1 | 1,200 | Scores, caption, metrics, and vision payload |

**Normal request count: 5** (four GPT text calls and one Gemini vision call).

### Planning estimate per image post

The following is a conservative planning range, not measured telemetry:

| Component | Planning input tokens | Planning output tokens | Estimated cost |
|---|---:|---:|---:|
| Four GPT-4o mini calls combined | 3,000–6,000 | 800–2,000 | $0.00093–$0.00210 |
| One Gemini image-vision call | Media-dependent | 200–600 | Track from API usage |
| **Total text-model portion** | — | — | **about $0.001–$0.002 per post** |

Gemini image-token cost is intentionally left out of the fixed estimate because image dimensions and provider tokenization determine it. With Gemini 3.1 Flash-Lite's higher token rates, measure representative production media before setting a per-post allowance.

### Retry and fallback exposure

- If vision output does not parse, Gemini is called once more with a simplified prompt: **up to two Gemini vision calls**.
- If Gemini fails, the OpenAI vision fallback can make **up to two more calls**. Its source default is `gpt-4o` when `LLM_MODEL_NAME` is unset, rather than `gpt-4o-mini`; this is a cost-risk path that should be explicitly configured before production.
- If the final GPT response is unusable, the current implementation uses deterministic fallback output; it does not make an extra repair call.
- A memory cache and persisted post snapshots can avoid repeat analysis for an unchanged post. Cache hits should be treated as approximately $0 model cost.

### Reels

Account analysis attaches a separate Gemini File API reel analysis for a reel. That is a Gemini 3.1 Flash-Lite video-input request after migration, and its cost varies with video duration and output tokens. The single-post path currently does not attach this File API reel analysis; that is a product-behavior gap to resolve separately, not an assumed cost.

## 2. Account AI Analysis

Entry point: `POST /api/account-analysis`. The request defaults to **30 posts** and is capped at 30.

When the payload does not include precomputed scores, the account job runs the Single-Post AI Analysis pipeline for every post, then makes two additional GPT calls:

| Component | Requests | Model | Notes |
|---|---:|---|---|
| Per-image post pipeline | 4 GPT + 1 Gemini each | GPT-4o mini + Gemini 3.1 Flash-Lite (planned) | Same path as above |
| Per-reel analysis | 4 GPT + 1 Gemini File API each | GPT-4o mini + Gemini 3.1 Flash-Lite (planned) | In addition to the normal post path's failed/disabled image-vision attempt |
| Creator intelligence | 1 | GPT-4o mini | `max_tokens=700` |
| Peer rankings | 1 | GPT-4o mini | `max_tokens=600`; can be disabled with `AI_PEER_RANKINGS_ENABLED=0` |
| Account-health score and report | 0 | Deterministic | No model tokens |

### Account-level planning scenarios

| Scenario | GPT text calls | Gemini calls | GPT text-model estimate | Plus Gemini media cost |
|---|---:|---:|---:|---|
| 10 image posts | 42 | 10 | $0.011–$0.023 | 10 image-vision requests |
| 30 image posts (default/max) | 122 | 30 | $0.032–$0.065 | 30 image-vision requests |
| 30 reels | 122 | 30 File API requests | $0.032–$0.065 | Video-duration-dependent |

Estimates use the single-post GPT planning range above plus approximately 1,000 input and 800 output tokens for the two account-level calls combined. Long captions, verbose vision payloads, retries, and output close to the configured 1,200-token maximum increase spend.

### Existing controls that reduce spend

- The account endpoint deduplicates identical requests for **2 hours**.
- An account is limited to **three analysis requests per hour**.
- Post snapshots are reused when available, avoiding the full per-post pipeline.
- Supplying precomputed post scores skips the per-post AI pipeline; the deterministic account aggregation then has no per-post model cost.

The rate limit protects against bursts but is not a monetary budget. At the 30-post maximum, three uncached runs per account per hour can still make 366 GPT calls and 90 Gemini vision calls.

## 3. Trend Recommendations

Entry point: `CreatorTrendService.get_trends_and_recommendations`.

| Step | Provider/model | Calls per refresh | Output cap in code | Other usage |
|---|---|---:|---:|---|
| Creator niche discovery | GPT-4o mini | 1 | 300 | Up to ten recent captions |
| Live-signal retrieval | Tavily + Google Trends | 1 Tavily search + 1 Google Trends fetch | — | Tavily is a separate paid vendor; Google Trends is an unauthenticated external dependency |
| Global-trend synthesis | GPT-4o mini | 1 | 800 | Grounded with up to ten live signals |
| Tailored recommendations | GPT-4o mini | 1 | 800 minimum | Default returns five recommendations |

**Normal request count: three GPT calls, one Tavily advanced search, and one Google Trends fetch.**

### Planning estimate per refresh

| Component | Planning input tokens | Planning output tokens | Estimated GPT-4o mini cost |
|---|---:|---:|---:|
| Niche discovery | 1,000–3,000 | 100–300 | $0.00021–$0.00063 |
| Global-trend synthesis | 800–2,000 | 300–800 | $0.00030–$0.00078 |
| Recommendation generation | 1,000–2,500 | 500–1,000 | $0.00045–$0.00098 |
| **Total GPT cost per refresh** | **2,800–7,500** | **900–2,100** | **about $0.001–$0.0024** |

Add the current Tavily per-search price from the team's Tavily plan. It cannot be derived from this repository and may exceed the GPT token cost for a refresh. Google Trends does not provide a paid API contract in this code path, so factor in reliability/rate-limit risk rather than an API line item.

## Cost risks and production actions

1. **Record real token usage.** Log model, provider, input, cached-input, output tokens, media type, feature, account/job ID, retry number, and estimated USD after every successful model call. Build budgets from 30 days of this data, not only planning assumptions.
2. **Set a model allowlist in production.** Pin `LLM_MODEL_NAME=gpt-4o-mini` and `GEMINI_MODEL=gemini-3.1-flash-lite` once migration is complete. Do not use the rolling `gemini-flash-lite-latest` alias for cost-sensitive workloads.
3. **Configure the OpenAI vision fallback explicitly.** Its fallback default is `gpt-4o`; make it `gpt-4o-mini` or disable it if the quality tradeoff is acceptable.
4. **Use prompt caching deliberately.** Share a stable prompt prefix across calls where it is useful, put dynamic post data last, and record `cached_tokens` to validate the discount.
5. **Set output limits per task.** S2, S3, and S4 currently inherit the generic 1,200-token cap even though their structured outputs are much smaller. A 250–400 token cap for those calls would bound failure-mode spend.
6. **Use Batch only for deferred work.** Move nightly/backfill account analysis, embeddings, and scheduled trend refreshes to Batch when a 24-hour completion window is acceptable.
7. **Measure the existing trend cache.** Trend generation already uses a 24-hour Redis cache keyed by account and post-content hash. Add cache-hit, bypass, and forced-refresh telemetry before changing the TTL or pricing trend credits.
8. **Treat Azure separately.** The image editor uses an Azure OpenAI deployment. Azure regional/deployment pricing, not OpenAI direct list pricing, is the billable source for that feature.
9. **Review pricing on cadence.** Reverify this table before Q4 budgeting and whenever either provider announces a deprecation, replacement, or pricing change.

## Sources

- OpenAI: <https://developers.openai.com/api/docs/models/gpt-4o-mini>
- OpenAI embeddings: <https://developers.openai.com/api/docs/models/text-embedding-3-small>
- OpenAI Batch API: <https://platform.openai.com/docs/api-reference/batch>
- OpenAI prompt caching: <https://openai.com/index/api-prompt-caching/>
- Google Gemini 3.1 Flash-Lite: <https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite>
- Google Gemini API pricing: <https://ai.google.dev/gemini-api/docs/pricing>
- Azure OpenAI pricing: consult the Azure Pricing page for the region and deployment actually configured in `IMAGE_EDITOR_AZURE_OPENAI_*`.
