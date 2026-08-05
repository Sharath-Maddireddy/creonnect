# Creator Intelligence Metrics Implementation Plan

**Companion PRD:** `PRD_CREATOR_INTELLIGENCE_METRICS_COMPLETION.md`
**Delivery strategy:** additive, versioned, feature-flagged, and backward compatible.

## 0. Reference Dashboard Scope and Delivery Sequence

The reference dashboard is a presentation benchmark, not a source of facts. Every card must read only a report metric with observed evidence, an explicitly labelled prediction, or a clear unavailable state. Do not copy demo values, inferred demographics, follower history, retention, or earnings estimates into production accounts.

| Screen | UI modules to deliver | Required report inputs | Depends on |
|---|---|---|---|
| Overview | Account header, score ring, grade band, pillar bars, confidence, narrative, export | overall grade, pillar scores, report status, analysis timestamp | Phase 0 |
| Overview: growth | Historical/forecast chart, 30/90-day cards, opportunity, blocker | follower snapshots, forecast model, priority gaps | Phases 1 and 4 |
| Overview: monetization | Virality, follower quality, brand readiness, INR earnings cards | engagement signals, audience source, brand readiness, INR rate card | Phases 1 and 4 |
| Content | Best/worst post cards, hook cards, quality scorecards, retention and fatigue panels | post performance, hook, caption, visual, Reel and fatigue modules | Phase 2 |
| Audience | Timing heatmap, cadence, demographics, competitor table | observed timing data, cadence, audience insights, peer cohort | Phases 1 and 3 |
| Action plan | Four-week roadmap, checklist, priority-improvement cards | validated priorities, plan version, checklist persistence | Phase 3 |

**Indicative delivery estimate:** 14 to 18 calendar weeks with two backend engineers, one frontend engineer, and shared product/data support. This assumes the Instagram/Reel and audience-insights permissions are available. External data-provider approval, a new thumbnail-labeling program, or peer-data acquisition can extend the relevant workstream.

| Phase | Scope | Estimate | Dependency order |
|---|---|---:|---|
| 0 | Report contract, truthful availability, persistence, flags | 2 weeks | Start first |
| 1 | Existing signal consolidation, snapshots, peers, INR rate card | 3 to 4 weeks | After Phase 0 write path |
| 2 | Post, hook, visual, Reel, thumbnail, fatigue intelligence | 4 to 5 weeks | Post data and Reel inputs first; thumbnail calibration parallel |
| 3 | Audience source, plan/checklist, report UI shell | 3 weeks | Requires stable metric contract |
| 4 | Forecasting, earnings calibration, full UI, export, rollout | 2 to 4 weeks | Requires Phase 1 history and all metric modules |

### Current Phase 0 Status

Completed in the current workspace:

1. Added the versioned `CreatorIntelligenceReport` and 26-metric inventory contract.
2. Added truthful `derived` and `unavailable` metric handling with user-facing availability guidance.
3. Added feature-flagged account-analysis generation and shadow persistence behavior.
4. Removed the heatmap's neutral missing-engagement fallback and require three observed posts per slot.

Remaining before Phase 0 can exit:

1. Add immutable report-version and follower-snapshot tables plus migrations and retention cleanup.
2. Record methodology version, source timestamps, and structured evidence in the persisted contract.
3. Add the daily follower-snapshot writer, Reel-data availability manifest, shadow comparison telemetry, and sparse-account property tests.

## 1. Execution Model

The existing account-analysis job remains the orchestration entry point. New metric modules build a versioned `creator_intelligence_report` after post analysis, AHS, creator score, and peer ranking have completed. A module failure must create an `unavailable` metric entry rather than fail a valid core AHS calculation.

**Primary integration points**

| Area | Current location | Planned change |
|---|---|---|
| Report schema | `backend/app/domain/account_models.py` | Add versioned report, metric envelope, evidence, and availability models. |
| Job orchestration | `backend/app/services/account_analysis_jobs.py` | Build, attach, persist, and report partial Creator Intelligence results. |
| Core calculations | `backend/app/analytics/account_health_engine.py` | Reuse provenance-safe AHS signals; remove missing-ER heatmap fallback. |
| Creator signals | `backend/app/analytics/creator_scoring_engine.py` | Adapt growth, authenticity, retention, and AI signal outputs into report modules. |
| Persistence | `backend/app/infra/models.py`, Alembic | Add immutable report versions, follower snapshots, and plan/checklist state. |
| API | `backend/app/api/account_analysis_routes.py` | Expose report without changing legacy fields. |
| UI | `frontend/src/pages/Dashboard.jsx` | Read the report behind a feature flag; show evidence and unavailable states. |

## 2. Workstream A: Foundation and Contract (Phase 0)

**Goal:** Emit all 26 metric IDs with valid data status while making existing metrics truthful.

1. Add `MetricStatus`, `UnavailableReason`, `MetricEvidence`, `CreatorIntelligenceMetric`, and `CreatorIntelligenceReport` Pydantic models.
2. Add report groups: `overall_grade`, `growth`, `content`, `audience`, `competition`, `monetization`, and `action_plan`.
3. Implement one metric-factory helper that enforces status/value rules, coverage/confidence rules, methodology versions, and required availability guidance.
4. Add `build_creator_intelligence_report_v1(...)` as a pure orchestration service with independently guarded module calls.
5. Change account-health posting-time logic so bins without observed ER are omitted; require three observed ER posts per emitted slot.
6. Add a daily follower-snapshot writer and read service. Store the source timestamp and prevent duplicate daily snapshots.
7. Preserve raw Reel insight nullability and expose a `reel_data_availability` manifest per report.
8. Use `FEATURE_CREATOR_INTELLIGENCE_REPORT_V1` and `FEATURE_CREATOR_INTELLIGENCE_REPORT_V1_SHADOW_MODE` configuration flags.
9. In shadow mode, build and persist the report but leave Dashboard reads on the legacy payload.

**Migration work**

- Create `creator_intelligence_reports` with account ID, analysis job ID, schema version, report status, JSON payload, source timestamp, and created timestamp.
- Create `follower_snapshots` with account ID, follower count, observed timestamp, source, and uniqueness on account/date/source.
- Add retention cleanup for reports and follower snapshots older than 13 months.

**Exit criteria**

- All 26 metric IDs serialize successfully with `derived`, `predicted`, or `unavailable` status.
- No unavailable entry has a numeric value, evidence list, or missing availability guidance.
- Existing account-analysis API snapshots remain unchanged when the flag is disabled.

## 3. Workstream B: Consolidate Existing Signals (Phase 1)

**Goal:** Move existing calculations into the report rather than duplicate them.

1. Map AHS to Overall Grade (#1), including coverage and the explicit absence of growth when snapshots are insufficient.
2. Build Growth Potential (#2) from at least two snapshots seven days apart; otherwise return `insufficient_history`.
3. Adapt creator-score authenticity signals to Follower Quality (#4), preserving individual flags and source coverage.
4. Add Posting Frequency (#6) with current cadence, peer/niche target range, and `cohort_too_small` behavior below 30 matched peers.
5. Upgrade Content Pillars (#18) to return distribution plus per-pillar ER, reach, saves, shares, sample size, and status.
6. Adapt peer ranking to Competitor Comparison (#21) using the same cohort definition and threshold.
7. Integrate detailed brand readiness (#22) rather than only its compact AHS label.
8. Integrate the rate calculator as Earnings Potential (#23) with `market=IN`, `currency=INR`, rate-card version, assumptions, and stale-calibration guardrails.
9. Produce Priority Improvements (#26) from deterministic metric gaps, ordered by impact, effort, confidence, and dependencies.

**Exit criteria**

- Metrics `1, 2, 4, 6, 18, 21, 23, 26` are computed from one report request.
- Revenue is never returned in USD for the Phase 1 account-analysis report.
- Shadow comparison confirms legacy AHS and creator-score values have no unapproved drift.

## 4. Workstream C: Post, Hook, and Reel Intelligence (Phase 2)

### 4.1 Sequence 2A: Post Performance Explainer

1. Add a normalized post-performance index using observed ER, reach efficiency, saves, shares, and weighted post score.
2. Build Best Posts (#7) and Worst Posts (#8) from posts with sufficient observed metrics.
3. Generate deterministic success/underperformance reasons from the strongest component deltas.
4. Return source post IDs, input values, methodology version, and explicit unavailable entries where data is insufficient.

### 4.2 Sequence 2B: Hook Intelligence

1. Add hook-source extraction: Reel transcript opening first, then caption first sentence.
2. Build Winning Hooks (#9) and Weak Hooks (#10) from hook score plus observed post performance.
3. Exclude posts with neither transcript nor caption hook; do not create a proxy hook.

### 4.3 Sequence 2C: Reel Editing and Retention

1. Map existing Reel vision/reel-analysis outputs into Editing Quality (#13).
2. Add ingestion and persistence for observed average watch time, completion, replay, and three-second views.
3. Build Retention (#15) only when the required Reel insight inputs are observed.
4. Keep Editing and Retention independently unavailable when their individual input gates are not met.

### 4.4 Sequence 2D: Thumbnail Scoring

1. Define a labeled calibration dataset and score rubric for cover clarity, text legibility, subject prominence, and click potential.
2. Implement the Thumbnail Score (#14) module and attach score evidence to each analyzed Reel/post cover.
3. Validate calibration against held-out labeled examples before enabling user traffic.

### 4.5 Sequence 2E: Content Fatigue

1. Cluster posts by category, format, and approved content embedding similarity.
2. Enforce six posts across 28 days and a three-post repeated cluster before calculation.
3. Flag fatigue only at a 20% or greater median observed-ER decline between early and recent matching posts.
4. Return derived `false` when evaluated but not detected, or `unavailable` when history is insufficient.

**Exit criteria**

- Metrics `7, 8, 9, 10, 13, 14, 15, 19` contain post-level evidence or a valid unavailable state.
- Thumbnail scoring remains disabled unless the calibration quality gate passes.

## 5. Workstream D: Plans, Demographics, and UI (Phase 3)

1. Integrate authorized Audience Demographics (#20) with source timestamp, permission status, and unavailable guidance.
2. Implement a deterministic four-week Growth Plan (#24) selector from high-confidence report gaps.
3. Permit an LLM to rewrite plan wording only through schema-constrained output.
4. Add a validator that permits only preselected metric IDs, source post IDs, baselines, targets, and impact claims; fall back to deterministic copy on rejection.
5. Add account-owned Weekly Checklist (#25) persistence, completion state, and plan-version linkage.
6. Add Dashboard report sections behind the read flag, metric detail drawers, evidence links, confidence labels, and unavailable guidance.
7. Gradually migrate existing Dashboard cards to report-backed fields after shadow-mode validation.

**Exit criteria**

- Metrics `20, 24, 25` work without exposing unsupported demographic or plan claims.
- Checklist state survives report recalculation and is clearly linked to its plan version.

## 6. Test Plan

| Level | Coverage |
|---|---|
| Unit | Every metric formula, threshold, methodology version, and unavailable reason. |
| Property-based | Sparse, null, malformed, and mixed-source accounts never produce synthetic values or unsupported evidence. |
| Contract | Legacy account-analysis fields retain their response shape when the report flag is disabled. |
| Integration | Job orchestration persists `complete` and `partial` reports; module errors remain localized. |
| Migration | Snapshot uniqueness, report immutability, schema-version read adapter, and retention cleanup. |
| UI | Observed/derived/predicted/unavailable rendering, evidence drawer, feature-flag fallback, and checklist persistence. |
| Canary | Telemetry for report status, unavailable reasons, module failures, schema errors, and AHS score drift. |

## 7. Rollout Checklist

1. Ship schema, migrations, and write path behind both flags.
2. Enable shadow mode for internal accounts; compare legacy and report outputs daily.
3. Resolve score-drift and serialization regressions before enabling Dashboard reads.
4. Canary read access for a small internal cohort, then a controlled creator cohort.
5. Monitor module failures and synthetic-value property checks continuously.
6. Enable each phase only after its acceptance criteria and methodology review pass.
7. Disable the report read flag immediately if canary thresholds are exceeded; keep legacy AHS and creator-score reads active.

## 8. Ownership and Decisions Required

| Decision | Owner | Needed Before |
|---|---|---|
| Follower snapshot source and schedule | Backend + Data | Phase 0 migration |
| Reel retention data provider and permissions | Product + Integrations | Phase 0/2C |
| Peer cohort definition and refresh job | Data + Backend | Phase 1 |
| INR rate-card inputs and calibration owner | Monetization Analytics | Phase 1 |
| Thumbnail labeled calibration set | Product + ML/Analytics | Phase 2D |
| Demographics provider approval | Product + Integrations | Phase 3 |
| Sprint staffing and target dates | Engineering leadership | Before Phase 0 kickoff |

## 9. Definition of Done

The initiative is complete when all 26 metric IDs are report-backed, provenance-safe, persisted with schema versioning, exposed without breaking legacy consumers, and rendered in the Dashboard with evidence or clear availability guidance. All feature flags may then be retired only after the legacy consumers have migrated and the canary metrics remain healthy for the agreed observation period.
