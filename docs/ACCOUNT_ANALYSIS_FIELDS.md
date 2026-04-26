# Account Analysis Fields Reference

This document lists what the account analysis API shows in the `result` payload returned by `GET /api/account-analysis/{job_id}`.

## Top-Level Result Fields

| Field | What we show | Notes |
|---|---|---|
| `ahs_score` | Overall Account Health Score out of 100 | Weighted composite of the five pillars |
| `ahs_band` | Human-readable label for the overall score | One of `NEEDS_WORK`, `AVERAGE`, `STRONG`, `EXCEPTIONAL` |
| `pillars` | Breakdown of the five account health pillars | Each pillar includes `score`, `band`, and `notes` |
| `drivers` | Main reasons helping or limiting account performance | Deterministic account-level explanations |
| `recommendations` | Suggested next actions to improve the account | Ordered, deduplicated action items |
| `metadata` | Context about the analysis window and confidence | Includes post count and time window |
| `creator_intelligence` | AI-generated creator summary and brand-fit rollup | Optional |
| `vision_summary` | Aggregate vision signals across analyzed posts | Optional |
| `engagement_signals` | Aggregate engagement behavior signals | Optional |
| `posts_summary` | Per-post summary rows and scores | Included only when `include_posts_summary=true` |

## Pillars

| Pillar | What it means | Source signals |
|---|---|---|
| `content_quality` | Overall quality and clarity of content | Built from post-level `S1`, `S2`, and `S3` |
| `engagement_quality` | Strength of audience interaction | Uses engagement rate and save/share behavior |
| `niche_fit` | Alignment between content and audience niche | Uses `S4` and niche benchmarks when available |
| `consistency` | Posting cadence and performance stability | Uses posts-per-week and weighted score variance |
| `brand_safety` | Safety and brand-friendliness of the account | Uses `S6` and safety penalties/flags |

Each pillar has the same shape:

| Subfield | What we show |
|---|---|
| `score` | Pillar score from 0 to 100 |
| `band` | Score label: `NEEDS_WORK`, `AVERAGE`, `STRONG`, `EXCEPTIONAL` |
| `notes` | Explanations about fallbacks, missing signals, or benchmark logic |

## Drivers

| Field | What we show |
|---|---|
| `drivers[].id` | Stable machine-friendly identifier |
| `drivers[].label` | Short human-readable title |
| `drivers[].type` | `POSITIVE` or `LIMITING` |
| `drivers[].explanation` | Why this driver was generated |

Example driver ids include:

| Example id | Meaning |
|---|---|
| `limited_history_context` | Fewer than 10 posts were available |
| `content_quality_low` | Average content signals are weak |
| `engagement_quality_low` | Engagement is below benchmark |
| `niche_fit_low` | Content appears misaligned with audience |
| `consistency_low` | Posting or performance is unstable |
| `brand_safety_risks` | Safety issues or severe penalties were detected |

## Recommendations

| Field | What we show |
|---|---|
| `recommendations[].id` | Stable machine-friendly identifier |
| `recommendations[].text` | Actionable recommendation text |
| `recommendations[].impact_level` | `HIGH`, `MEDIUM`, or `LOW` |

## Metadata

| Field | What we show |
|---|---|
| `metadata.post_count_used` | Number of recent posts included in the analysis |
| `metadata.min_history_threshold_met` | Whether the 10-post confidence threshold was met |
| `metadata.time_window_days` | Number of days covered by the analyzed posts |

## Creator Intelligence

`creator_intelligence` is an optional AI-generated rollup.

| Field | What we show |
|---|---|
| `creator_intelligence.creator_persona` | Short description of the creator persona |
| `creator_intelligence.content_style_summary` | Summary of the creator's content style |
| `creator_intelligence.top_performing_themes` | Themes that appear to perform best |
| `creator_intelligence.brand_fit.fit_categories` | Categories the creator fits well |
| `creator_intelligence.brand_fit.red_flags` | Brand-fit concerns or red flags |

## Vision Summary

`vision_summary` is an optional deterministic rollup of visual signals across posts.

| Field | What we show |
|---|---|
| `vision_summary.avg_cringe_score` | Average cringe score across posts |
| `vision_summary.avg_hook_strength` | Average hook strength across posts |
| `vision_summary.avg_production_level` | Dominant production level such as `low`, `medium`, or `high` |
| `vision_summary.flagged_posts_count` | Count of posts flagged by cringe/adult-content signals |
| `vision_summary.common_technical_flaws` | Most common repeated technical flaws |

## Engagement Signals

`engagement_signals` is an optional deterministic rollup of interaction signals across posts.

| Field | What we show |
|---|---|
| `engagement_signals.avg_save_rate` | Average save rate |
| `engagement_signals.avg_share_rate` | Average share rate |
| `engagement_signals.avg_watch_through_rate` | Average watch-through rate |
| `engagement_signals.avg_profile_visit_rate` | Average profile-visit rate |
| `engagement_signals.audience_trust_index` | Composite trust-style interaction score |
| `engagement_signals.virality_potential` | Composite virality-style interaction score |
| `engagement_signals.consistency_score` | Engagement consistency score |

## Posts Summary

`posts_summary` is an optional per-post breakdown included when requested during enqueue.

| Field | What we show |
|---|---|
| `posts_summary[].post_id` | Post/media identifier |
| `posts_summary[].shortcode` | Shortcode if available |
| `posts_summary[].post_type` | `IMAGE`, `REEL`, or `null` |
| `posts_summary[].media_url` | Media URL when available |
| `posts_summary[].caption_preview` | Caption preview truncated to 120 chars |
| `posts_summary[].ai_summary` | AI or scene-style short summary when available |
| `posts_summary[].scores.S1` | Visual quality score |
| `posts_summary[].scores.S2` | Caption effectiveness score |
| `posts_summary[].scores.S3` | Content clarity score |
| `posts_summary[].scores.S4` | Audience relevance score |
| `posts_summary[].scores.S5` | Engagement potential score |
| `posts_summary[].scores.S6` | Brand safety score |
| `posts_summary[].scores.P` | Weighted post score |
| `posts_summary[].scores.predicted_er` | Predicted engagement rate |
| `posts_summary[].notes.vision_status` | `ok`, `error`, or `disabled` |
| `posts_summary[].notes.fallback_used` | Whether post analysis used fallback behavior |
| `posts_summary[].notes.cringe_score` | Vision-derived cringe score when available |
| `posts_summary[].notes.cringe_label` | Cringe label when available |
| `posts_summary[].notes.production_level` | Production level when available |
| `posts_summary[].notes.hook_strength_score` | Hook strength when available |
| `posts_summary[].notes.technical_flaws` | Technical flaw list when available |

## Job-Level Fields Outside `result`

The polling response also includes execution fields outside the analysis result itself.

| Field | What we show |
|---|---|
| `status` | Job state such as `queued`, `started`, `succeeded`, `failed` |
| `progress` | Current stage plus done/total counts |
| `warnings` | Non-fatal warnings collected during processing |
| `quality` | Runtime quality flags such as vision enabled/error/fallback counts |
| `error` | Failure payload when the job does not succeed |
