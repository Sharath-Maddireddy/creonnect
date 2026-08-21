# Single Post Analysis response contract

**Status:** locked for the report redesign  
**Endpoint:** `POST /api/v1/post-analysis`  
**Version:** `v2`

The frontend must check `contract_version` and render this response directly. It must not reconstruct the headline score from any other score field.

## Authoritative score and score matrix

`score` is the one authoritative headline result:

```json
{"value": 73, "max": 100, "band": "STRONG_FOUNDATION", "source": "ai_creative_weighted_score"}
```

The score is computed from AI creative dimensions S1-S6. It is not derived from
likes, comments, views, reach, impressions, saves, shares, watch time, or
engagement rate. `ai.creative_score` and `ai.creative_band` mirror the headline
for presentation. Internal legacy `ai_analysis.ai_content_score` and
`ai_analysis.ai_content_band` fields are compatibility aliases of this same
creative score and band.

`scores` is compatibility-only: there is no known in-repository consumer of it, but external consumers have not been audited. `scores.P` is a deprecated mirror of `score.value`; it is never a second score and must not be shown independently. Do not add new consumers. Its removal requires an external-consumer check and a separately versioned breaking change.

The six raw scorer outputs `scores.S1` through `scores.S6` are all on a **0–50** scale. Frontends must use `score_components` for score bars:

```json
{
  "id": "S1",
  "label": "Visual quality",
  "raw_value": 41,
  "raw_max": 50,
  "normalized_value": 82,
  "normalized_max": 100,
  "confidence": "high",
  "status": "available",
  "reason": null
}
```

`normalized_value` is a presentation value (`raw_value * 2`), not a separately modelled result. A bar’s width must use `normalized_value / normalized_max`; raw values must be displayed as `raw_value/raw_max` if shown.

Audience Fit (`S4`) requires both post category and creator niche context. When
either is missing, its component has `status: "unavailable"`, null score values,
`confidence: "unavailable"`, and a reason. S4 is then excluded from the weighted
denominator and from coaching context; the frontend must not render a neutral
25/50 bar. The nested legacy S4 object may retain 25/50 for compatibility, but
its own `status` is authoritative.

## Confidence and availability

`confidence.level` is one of `high`, `standard`, `limited`, or `estimated`, with a user-facing `reason`. Component confidence uses the same vocabulary. **Current limitation:** a run-level fallback cascades `estimated` to every populated component; independently calculated per-component confidence is not implemented yet. The UI must treat component confidence as a run-level signal until that changes.

`data_sources` states provenance and prevents URL-test inputs from being presented as OAuth-backed insights:

```json
{"media": "request_supplied", "engagement_metrics": "request_supplied_not_used_for_ai_score|not_provided",
 "score": "ai_creative_weighted_score", "account_baseline": "durable_post_analysis_history"}
```

The current direct-URL flow does not return OAuth post-insight metrics. When connected-account metrics are added, their source must be a new explicit value such as `oauth_insight`, never inferred from field presence.

Observed performance percentiles must not cap or floor Engagement Pull (`S5`).
S5 may only be constrained by creative evidence such as contradictory Visual
Quality and Content Clarity scores.

`predicted_er` is retained as a compatibility object but is not part of this AI-only report:

```json
{"status": "not_supported", "value": null, "confidence": "unavailable",
 "reason": "Predicted engagement is not part of the AI-only creative analysis contract."}
```

The frontend must omit the predicted-ER card. Compatibility keys under `scores`
also return a null value and `unavailable` confidence; they must never be shown
as zero.

`unavailable_features` is a deliberate product boundary, not a retry state. Its keys are `retention_curve`, `post_attributed_follows`, and `post_demographics`, each with `status: "not_supported"` and a reason. The report redesign must not reserve chart or metric-card space for those fields. Account-level demographics belong in Account Analysis.

`account_score_baseline` is additive history data. It is based on the latest analysis of up to 12 distinct **other** posts for the authenticated account and has provenance `data_sources.account_baseline: "durable_post_analysis_history"`:

```json
{"status": "available|insufficient_history|unavailable", "sample_size": 6,
 "minimum_sample_size": 3, "average_score": 68.4, "delta_from_average": 4.6,
 "reason": "..."}
```

Only `status: "available"` may render an up/down comparison. `insufficient_history` is expected for new accounts and must show the reason; it is not a failed analysis.

The baseline compares prior analyses, not observed Instagram performance. It should be rendered as a score-history comparison only; do not label it as an OAuth/account-insights benchmark until history stores per-observation metric provenance and exposes an aggregate provenance summary.

## Evidence, safety, and diagnostics

`score_evidence` is a list of traceable constraints:

```json
{"component_id": "S2", "signal_type": "caption_missing",
 "label": "Main score constraint: Caption strength", "detail": "..."}
```

`component_id` is one of `S1`–`S6`; `signal_type` identifies the observed condition used to form the explanation. A recommendation that cites an evidence item must retain both fields rather than matching free text.

`cringe` is a separate brand-safety diagnostic: `cringe_score`, `cringe_label`, `is_cringe`, `cringe_signals`, `cringe_fixes`, `production_level`, `adult_content_detected`, and `vision_status`. It must not affect the headline score unless the scoring service explicitly records that effect.

Brand Safety (`S6`) also records brand-suitability flags from vision descriptions.
Blood/gore imagery and ambiguous drinking-from-container depictions receive
explicit, reviewable penalties instead of being described as fully clean.

`quality` is run diagnostics: `vision_enabled` indicates whether vision was configured; `ai_fallback_used` is the source of a run-level fallback confidence downgrade. Neither field is an independent score.

## Stable top-level response

```text
contract_version, status, post, data_sources, vision, reel_analysis, scores, score, confidence,
score_components, account_score_baseline, predicted_er, score_evidence,
unavailable_features, ai, cringe, score_analysis, warnings, quality
```

`post` contains `post_id`, `post_type`, `media_url`, and `caption_text`. Carousels use `post_type: "CAROUSEL"`; their slide/aggregate vision signals remain in `vision.signals`.

## Rollout rule

The UI may begin only against this documented v2 shape. Do not expose a legacy raw content score, a fake retention curve, per-post follower attribution, or post-level demographics in this report.
