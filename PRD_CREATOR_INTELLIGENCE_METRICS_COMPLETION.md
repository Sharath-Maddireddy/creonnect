# PRD: Creator Intelligence Metrics Completion

**Status:** Draft
**Target:** Production
**Source of truth:** `Creonnect_AI_Creator_Intelligence_Metrics.pdf`

---

## 1. Overview

Creonnect's account analysis must provide one trustworthy, account-level Creator Intelligence report covering the 26 metrics defined in the source document. The report must combine deterministic post analysis, permitted platform insights, and AI explanations without presenting estimated, missing, or predicted values as observed account data.

This PRD completes the existing Account Health Score (AHS), creator score, peer ranking, revenue, and recommendation systems. It does not replace their scoring logic; it unifies their outputs under a versioned account-analysis contract and fills the missing metrics.

## 2. Goals

1. Return all 26 metrics from a single `creator_intelligence_report` object produced by account analysis.
2. Label every metric with its data status: `observed`, `derived`, `predicted`, or `unavailable`.
3. Never invent follower history, audience demographics, retention, posting-time performance, or earnings.
4. Give creators an ordered 30-day growth plan and a weekly action checklist tied to measurable evidence.
5. Preserve existing `AccountHealthScore` and dashboard consumers during migration.

## 3. Non-Goals

- Predicting guaranteed reach, revenue, or follower growth.
- Inferring age, gender, country, or active-time demographics without a permitted source.
- Treating model-generated recommendations as observed audience behavior.
- Building a separate analytics product outside the existing account-analysis job.

## 4. Users

| User | Need |
|---|---|
| Creator | Know what is working, what is not, and what to improve next. |
| Brand or agency | Assess quality, authenticity, safety, audience fit, and collaboration readiness. |
| Internal analyst | Audit calculation inputs, coverage, confidence, and unavailable data. |

## 5. Product Requirements

### 5.1 Unified Report Contract

Account analysis will add an optional `creator_intelligence_report` to its result payload. Every metric uses this envelope:

```json
{
  "metric_id": "virality_score",
  "label": "Virality Score",
  "status": "derived",
  "value": 74.2,
  "unit": "score_0_100",
  "confidence": 0.82,
  "coverage": 0.9,
  "methodology_version": "virality-v1",
  "evidence": ["avg_share_rate", "avg_save_rate", "watch_through_rate"],
  "unavailable_reason": null,
  "availability_guidance": null,
  "updated_at": "2026-08-05T00:00:00Z"
}
```

Allowed `status` values:

- `observed`: direct source-system metric.
- `derived`: deterministic calculation from observed inputs.
- `predicted`: model output; must include confidence and methodology version.
- `unavailable`: no value; must include `unavailable_reason`.

All percentages are stored as fractions in backend payloads (`0.035` for 3.5%) unless a field explicitly declares a `percent_0_100` unit. The frontend is responsible for formatting.

An unavailable metric is represented as:

```json
{
  "metric_id": "audience_demographics_summary",
  "label": "Audience Demographics Summary",
  "status": "unavailable",
  "value": null,
  "unit": null,
  "confidence": null,
  "coverage": 0.0,
  "methodology_version": "audience-demographics-v1",
  "evidence": [],
  "unavailable_reason": "no_authorized_data_source",
  "availability_guidance": "Connect an authorized audience-insights source to include demographics."
}
```

`unavailable_reason` must use one of: `no_authorized_data_source`, `insufficient_history`, `missing_required_metrics`, `cohort_too_small`, `source_refresh_failed`, or `calculation_failed`. The last two distinguish operational failures from genuinely absent data.

`availability_guidance` is required when status is `unavailable`. It is a short, user-facing explanation of the next condition that could make the metric available; it must not expose internal exceptions, provider credentials, or unsupported promises.

### 5.1.1 Confidence and Coverage Semantics

`coverage` and `confidence` are different values:

- `coverage` is the share of required observed inputs available for a metric, from `0.0` to `1.0`.
- `confidence` for a `derived` metric is deterministic evidence sufficiency, not a statistical confidence interval. It is calculated from input coverage, minimum sample attainment, and input freshness. The calculation version must be recorded in `methodology_version`.
- `confidence` for a `predicted` metric is a calibrated model confidence. It must identify the model/evaluation version and may not be reused as derived-metric confidence.
- A statistical confidence interval is optional and, when supplied, is a separate `interval` field. It must never be implied by the `confidence` value.

For derived metrics, the initial standard is:

`confidence = coverage * min(1, observed_sample_count / required_sample_count) * freshness_factor`

where `freshness_factor` is `1.0` within the configured refresh window and declines to `0.5` at twice that window. A metric below its required sample count is `unavailable` unless its metric-specific rules explicitly allow a lower-confidence result.

### 5.2 Metric Inventory

| # | Metric | Delivery | Required Inputs | Current State |
|---|---|---|---|---|
| 1 | Overall Grade | AHS plus growth component and coverage label | quality, engagement, consistency, safety, niche, growth | Partial |
| 2 | Growth Potential Score | Forecast range and confidence, not a band-only label | follower snapshots, reach/ER trend, cadence | Partial |
| 3 | Virality Score | Deterministic 0-100 score | shares, saves, watch-through, completion | Exists |
| 4 | Follower Quality Score | Authenticity score with signal breakdown | reach, ER, saves, shares, growth anomalies, spam signals | Partial |
| 5 | Posting Time Analysis | Ranked slots from observed ER only | published time, observed ER | Partial |
| 6 | Posting Frequency Analysis | Current cadence versus evidence-backed target range | timestamps, niche/format benchmark | Partial |
| 7 | Best Performing Posts | Top five plus evidence-backed success reasons | ER, reach, saves, shares, content scores | Partial |
| 8 | Worst Performing Posts | Bottom five plus underperformance reasons | same as #7 | Missing |
| 9 | Top Five Winning Hooks | Ranked opening hooks with post evidence | caption/opening transcript, hook score, performance | Missing |
| 10 | Top Five Weak Hooks | Lowest-performing hooks with reasons | same as #9 | Missing |
| 11 | Caption Quality Score | S2 rollup and subscore explanation | hook, readability, story, CTA | Exists |
| 12 | Visual Quality Score | S1 rollup and subscore explanation | composition, lighting, clarity, aesthetics | Exists |
| 13 | Editing Quality Score | Reel-only rollup | pacing, transitions, production/reel analysis | Partial |
| 14 | Thumbnail Score | Reel/post cover click-potential score | cover image, title/overlay, vision analysis | Missing |
| 15 | Retention Score | Reel retention rollup | average watch time, completion, replay, 3-second views | Partial |
| 16 | Hashtag Effectiveness | Per-tag performance and recommendation | tag usage, ER, reach, post count | Exists |
| 17 | CTA Effectiveness | S2 CTA subscore and outcome correlation | CTA score, comments/saves/profile visits | Exists |
| 18 | Content Pillars Distribution | Distribution and performance for each pillar | category, tags, ER, reach, saves, shares | Partial |
| 19 | Content Fatigue Detection | Repetition and declining-response risk | topic/format similarity, posting sequence, performance trend | Missing |
| 20 | Audience Demographics Summary | Age, gender, geography, active times | authorized platform demographics source | Missing |
| 21 | Competitor Comparison | Segment percentiles and evidence | peer cohort, follower band, niche, metrics | Partial |
| 22 | Brand Collaboration Readiness | Detailed readiness breakdown | quality, safety, engagement, consistency, niche, audience quality | Exists |
| 23 | Estimated Earnings Potential | Localized rate range and revenue scenarios | followers, ER, niche, quality, safety, currency | Partial |
| 24 | 30-Day Growth Plan | Four weekly evidence-linked actions | metric gaps, confidence, creator constraints | Missing |
| 25 | Weekly Action Checklist | Executable checklist with completion state | selected plan actions | Missing |
| 26 | Priority Improvements | Ranked improvement backlog | impact, effort, confidence, dependencies | Partial |

## 6. Functional Requirements

### 6.1 Data Provenance and Guardrails

- A posting-time slot is emitted only when it has at least three posts with observed engagement rate. Missing ER must not receive a neutral or synthetic score.
- Growth calculations require at least two follower snapshots separated by seven days. Otherwise return `unavailable`.
- Audience demographics require an authorized source. Empty data must remain unavailable, never estimated.
- Retention requires Reel insight inputs. It must not be inferred from likes, reach, or caption quality.
- Earnings are an estimate, must show currency and calculation assumptions, and must not be displayed as guaranteed income.
- AI-generated reasons must cite metric IDs and post IDs. If no evidence is available, return an unavailable reason rather than a generic explanation.
- Competitor Comparison requires at least 30 matched peer accounts after niche, follower-band, and platform filters. Smaller cohorts return `unavailable` with `cohort_too_small`.
- Content Fatigue requires at least six posts across 28 days, with at least three posts in the repeated topic/format cluster. It is flagged only when the median observed ER of the three most recent matching posts is at least 20% lower than the earlier matching-post median. Otherwise it returns a derived `false` value, or `unavailable` when history is insufficient.
- Hook Intelligence uses a Reel opening transcript when available; otherwise it may use the first caption sentence and must label that evidence source. A post with neither source is excluded, not silently scored with a proxy.
- Reel-derived metrics share a `reel_data_availability` manifest, but have separate input gates. Editing Quality can be `derived` from a successful Reel vision/editing analysis; Retention is `unavailable` unless observed watch time, completion, replay, or three-second-view insights are present. Existing Reel vision plumbing supports part of Editing Quality, while observed retention ingestion is a net-new dependency.

### 6.2 New Derived Modules

#### Post Performance Explainer

Produces best and worst post lists. Ranking uses a configurable composite of normalized ER, reach efficiency, saves, shares, and weighted post score. Reasons are deterministic templates grounded in the strongest positive or limiting inputs.

#### Hook Intelligence

Extracts the first caption sentence or Reel opening transcript. It ranks hooks only when a hook score and observed performance are available. The module returns text, source post ID, score, and evidence.

#### Content Fatigue Detector

Groups posts by embedding/category/format similarity. It flags fatigue only when repeated clusters have both a minimum sample size and statistically meaningful declining performance. It returns `unavailable` when history is insufficient.

#### Growth Plan Generator

Converts high-confidence metric gaps into four weekly goals. Every action includes target metric, baseline, success condition, expected impact, effort, and evidence references. The generation layer may rewrite wording but cannot create new facts or targets.

The enforcement path is mandatory: a deterministic planner selects eligible metric gaps and computes approved targets before any LLM call; the LLM receives only those fields and returns schema-constrained copy. A post-generation validator rejects unknown metric IDs, source post IDs, baselines, targets, or impact claims and falls back to deterministic templates on failure.

### 6.2.1 Earnings Localization and Calibration

Phase 1 launches with an explicit India rate card and `INR` output. The response includes `market`, `currency`, `rate_card_version`, and assumptions. Multi-currency rate cards are out of scope for Phase 1 and require separate calibration data before launch.

The Monetization Analytics owner reviews the INR rate card quarterly and triggers an out-of-cycle review when the observed accepted-rate median differs from the active card by 15% or more for two consecutive monthly cohorts. An uncalibrated or stale market returns `unavailable` rather than a converted amount.

### 6.3 API Shape

`GET /api/account-analysis/{job_id}` and persisted account analysis results will expose:

```json
{
  "account_health": {},
  "creator_score": {},
  "creator_intelligence_report": {
    "schema_version": "1.0",
    "overall_grade": {},
    "growth": {},
    "content": {},
    "audience": {},
    "competition": {},
    "monetization": {},
    "action_plan": {}
  }
}
```

Existing top-level fields remain available until all consumers migrate. The report must be persisted with its input-data timestamp and calculation version.

The report has `report_status`: `complete`, `partial`, or `failed`. A report is `partial` when the core account analysis succeeds but one or more non-core metric modules return `unavailable` because of a source or calculation failure. The account-analysis job fails only when it cannot produce the required core AHS result; it must persist a partial report with per-metric reasons whenever possible.

### 6.4 Dashboard Requirements

- Show metric values only when `status` is not `unavailable`.
- Show a concise unavailable state with source requirement when a metric lacks data.
- Distinguish observed, derived, and predicted values through accessible labels/tooltips.
- Provide a metric detail drawer with formula summary, confidence, evidence posts, and data freshness.
- Provide plan/checklist completion state per account, stored separately from calculated analysis data.

## 7. Data and Storage Requirements

| Data set | Purpose | Retention / Refresh |
|---|---|---|
| Follower snapshots | Growth score and trajectory | Daily snapshot; retain 13 months |
| Post insight snapshots | Trend, retention, and post explainers | Fetch on analysis and refresh eligible posts |
| Reel insight fields | Retention and hook performance | Preserve source timestamp and nullability |
| Audience demographics | #20 only | Authorized source; refresh weekly or provider cadence |
| Peer cohort aggregates | #6 and #21 | Versioned cohort calculation; refresh weekly |
| Plan completion state | #25 | Account-owned user actions; preserve until replaced |
| Creator intelligence reports | Auditability and historical comparisons | Retain immutable versioned reports for 13 months; retain latest report separately for fast reads |

When `schema_version` changes, existing reports are not mutated. A read adapter supports the prior version during the migration window, and the next successful analysis writes the current schema version. Expired reports may be deleted after the retention window, subject to account deletion and legal-retention policy.

## 8. Delivery Plan

### Phase 0: Trust Foundation

- Correct account-health heatmap handling for missing ER.
- Add data-status envelopes and report schema versioning.
- Store follower snapshots and preserve observed Reel insight fields.
- Add coverage/confidence to every computed metric.
- Deliver metric IDs: `1, 3, 5, 11, 12, 16, 17, 22`.

### Phase 1: Consolidate Existing Signals

- Integrate AHS, creator score, peer rankings, detailed brand readiness, and revenue estimate into the unified report.
- Upgrade content pillars from distribution-only to distribution plus per-pillar performance.
- Add posting-frequency target ranges using peer/niche benchmarks.
- Add priority improvement ranking with impact, effort, and confidence.
- Deliver metric IDs: `2, 4, 6, 18, 21, 23, 26`.

### Phase 2: Post and Hook Intelligence

- Implement best/worst post explainers.
- Implement winning/weak hook ranking.
- Add editing and retention account rollups where source data exists.
- Build the new thumbnail scoring module, including cover-image vision inputs and score calibration.
- Implement content-fatigue detection with conservative minimum-history thresholds.
- Deliver metric IDs: `7, 8, 9, 10, 13, 14, 15, 19`.

### Phase 3: Plans, Demographics, and UX

- Implement 30-day plan and persistent weekly checklist.
- Integrate authorized demographics and active-time data when available.
- Build dashboard metric detail drawers, unavailable states, and plan workflow.
- Deliver metric IDs: `20, 24, 25`.

### 8.1 Phase-to-Metric Coverage

| Phase | Metric IDs | Completion Bar |
|---|---|---|
| Phase 0 | 1, 3, 5, 11, 12, 16, 17, 22 | Available metrics are provenance-safe; all 26 IDs exist with valid unavailable states. |
| Phase 1 | 2, 4, 6, 18, 21, 23, 26 | Existing systems are integrated into the unified report with required thresholds and INR-only earnings. |
| Phase 2 | 7, 8, 9, 10, 13, 14, 15, 19 | New post, hook, thumbnail, retention, and fatigue modules meet deterministic evidence rules. |
| Phase 3 | 20, 24, 25 | Authorized demographics, plan, and checklist workflows are production-ready. |

### 8.2 Preliminary Sizing and Sequencing

Dates are intentionally unset until engineering capacity and provider-access dependencies are confirmed. The following are planning ranges, not commitments:

| Phase | Preliminary Size | Key Exit Dependency |
|---|---|---|
| Phase 0 | 3-4 engineering sprints | schema, provenance, follower snapshots, and contract test baseline |
| Phase 1 | 3-4 engineering sprints | peer cohort data, INR rate-card owner, and shadow-mode compatibility |
| Phase 2 | 5-7 engineering sprints | post evidence model, Reel insight ingestion, and thumbnail calibration set |
| Phase 3 | 3-5 engineering sprints, excluding provider approval time | authorized demographics source and persistent plan state |

Phase 2 order is mandatory:

| Sequence | Work | Dependency |
|---|---|---|
| 2A | Best/worst post explainer | Requires normalized observed post metrics and deterministic reason templates. |
| 2B | Hook Intelligence | Uses post evidence from 2A but does not depend on fatigue detection. |
| 2C | Editing and retention rollups | Editing uses existing Reel vision data where available; retention waits for observed Reel insights. |
| 2D | Thumbnail scoring | Net-new vision/calibration module; independent of retention but requires a labeled calibration set. |
| 2E | Content Fatigue | Depends on normalized post history and performance evidence from 2A; does not depend on hooks or thumbnail scoring. |

## 9. Acceptance Criteria

1. Every one of the 26 metric IDs is present in `creator_intelligence_report` with a valid status.
2. No unavailable metric contains a synthetic numeric value.
3. Every derived score exposes its input metric IDs and calculation version.
4. Posting-time recommendations contain only slots with observed ER and the minimum sample size.
5. Best/worst posts and hook rankings link to source post IDs and deterministic reasons.
6. Growth, retention, demographics, and earnings display source and confidence requirements in the UI.
7. Existing account-analysis consumers remain compatible during rollout.
8. Unit tests cover formulas, missing-data behavior, and status labels; integration tests cover persistence and API serialization.
9. Competitor Comparison returns `cohort_too_small` below 30 matched peers.
10. Content Fatigue is tested against the documented six-post, 28-day, three-post-cluster, and 20%-decline thresholds.
11. Growth-plan validation rejects unsupported generated claims and uses deterministic fallback copy.
12. Property-based tests generate sparse, partial, and malformed account inputs and verify that unavailable metrics never contain numeric values or fabricated evidence.
13. Shadow-mode runs compare legacy AHS/creator-score outputs with the unified-report integration before it is enabled for user traffic; score changes require an approved methodology change.
14. Canary telemetry tracks report status, unavailable reasons, calculation failures, and schema-validation failures before each rollout increase.

## 10. Success Metrics

| Measure | Target |
|---|---|
| Metric-contract coverage | Phase 0: 26/26 IDs with valid status; Phase 3: 26/26 metrics production-complete |
| Unsupported-value rate | 0 synthetic values for unavailable source data |
| Evidence coverage | 100% of derived/predicted metrics include evidence or methodology |
| Plan usefulness | At least 70% of active creators open a weekly action within 30 days |
| Analysis freshness | 95% of displayed reports show source timestamps within configured refresh windows |

## 11. Rollout and Failure Controls

- The unified report is introduced behind `CREATOR_INTELLIGENCE_REPORT_V1_ENABLED` and can be disabled without disabling the legacy AHS or creator-score response.
- Phase 1 runs in shadow mode first: compute and persist the report, but keep existing dashboard reads unchanged while contract and score-drift checks run.
- Contract tests validate that legacy top-level fields remain byte-for-byte compatible where their calculation versions have not changed.
- If report calculation errors exceed the agreed canary threshold, the feature flag is disabled and existing account analysis continues. Failed report modules are persisted as `unavailable` with `calculation_failed` where the core AHS remains valid.
- Rollout ownership is Engineering for flags and rollback, Data/Analytics for methodology approval, and Product for availability guidance and UI copy.

## 12. Dependencies and Risks

- Instagram/provider permissions may not expose demographics, follower history, or Reel retention for every account.
- Peer comparisons need enough matched creators to avoid unstable percentiles.
- Earnings models require explicit market/currency configuration and regular calibration.
- AI explanations must be constrained to evidence from the report to prevent unsupported claims.
