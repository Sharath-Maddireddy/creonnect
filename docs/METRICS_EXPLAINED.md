# Creonnect Profile Analysis — Metrics Reference

This document explains every metric in the analysis result JSON and exactly how each one is computed.

---

## Result Structure Overview

```
result.json
├── ahs_score          ← Overall Account Health Score (0–100)
├── ahs_band           ← Band label for the AHS
├── pillars            ← 5 pillar scores that make up the AHS
├── drivers            ← What's helping or hurting the account
├── recommendations    ← Actionable steps to improve
├── metadata           ← Context about the analysis run
└── posts_summary      ← Per-post scores (S1–S6, P)
```

---

## 1. Account Health Score (AHS)

### `ahs_score` — Overall Account Health Score
**Range:** 0–100

The single top-level number representing how healthy the account is overall. It is a **weighted average of the 5 pillars**:

| Pillar | Weight |
|---|---|
| Content Quality | 30% |
| Engagement Quality | 25% |
| Niche Fit | 15% |
| Consistency | 15% |
| Brand Safety | 15% |

Weights are re-normalized if a pillar has no signal data (e.g., missing engagement rates).

**Formula:**
```
AHS = Σ (pillar_score × pillar_weight) / Σ (available pillar weights)
```

### `ahs_band` — Band Label
Maps `ahs_score` to a human-readable tier:

| Score Range | Band |
|---|---|
| 0 – 39 | `NEEDS_WORK` |
| 40 – 59 | `AVERAGE` |
| 60 – 79 | `STRONG` |
| 80 – 100 | `EXCEPTIONAL` |

---

## 2. The Five Pillars

### 2.1 `content_quality` — What is it?
**Range:** 0–100 | **Weight:** 30%

Measures the **average quality of content** across all posts, based on three per-post scores (S1, S2, S3).

**How it's computed:**
1. For each post, compute the mean of its available S1, S2, S3 values (each are on a 0–50 scale).
2. Average those per-post means across all posts → `mean_content_0_50`.
3. Multiply by 2 to bring it to 0–100.

```
content_quality = mean(per_post_mean(S1, S2, S3)) × 2
```

---

### 2.2 `engagement_quality` — What is it?
**Range:** 0–100 | **Weight:** 25%

Measures **how well posts perform in terms of actual audience interaction**.

**How it's computed:**
- Uses the **median engagement rate** across all posts.
- If `account_avg_engagement_rate` is provided: score = ratio of median ER vs. account avg.
- If not provided (as in our run): uses **absolute ER band mapping**:

| Engagement Rate | Score |
|---|---|
| ≤ 1% | 30 |
| ≤ 3% | 50 |
| ≤ 6% | 70 |
| ≤ 10% | 85 |
| > 10% | 95 |

A **±5 point bonus/penalty** is applied for strong or weak save/share signal.

---

### 2.3 `niche_fit` — What is it?
**Range:** 0–100 | **Weight:** 15%

Measures how well the **content topics align with the creator's dominant niche and their audience**.

**How it's computed:**
- Base score = `mean(S4 across all posts) × 2` (S4 is the per-post audience relevance score).
- If `niche_avg_engagement_rate` is provided, it's blended: `base × 0.70 + niche_er_ratio × 0.30`.
- In our run, no niche benchmark was provided → score is **S4-only**.

---

### 2.4 `consistency` — What is it?
**Range:** 0–100 | **Weight:** 15%

Two components averaged together:

| Component | What it measures | Scoring |
|---|---|---|
| **Posting cadence** | Posts per week | ≤0.5 → 30, ≤1.5 → 50, ≤3 → 70, ≤6 → 85, >6 → 95 |
| **Performance variance** | Std deviation of P scores | High stddev → low score; low stddev → high score |

```
consistency = mean(posting_score, performance_score)
```

The stddev to score mapping:

| Std Dev (P scores) | Score |
|---|---|
| ≥ 25 | 40 |
| ≥ 18 | 55 |
| ≥ 12 | 70 |
| ≥ 7 | 85 |
| < 7 | 95 |

---

### 2.5 `brand_safety` — What is it?
**Range:** 0–100 | **Weight:** 15%

Measures **how safe and brand-friendly the content is** (no profanity, harmful references, spam).

**How it's computed:**
```
brand_safety = mean(S6 across all posts) × 2
```
- If any post has S6_raw ≤ 40/100 ("severe"): additional `-10` penalty.
- A score of 100 (as in our result) means **zero penalties across all 30 posts**.

---

## 3. Per-Post Scores (S1–S6) and P

These appear in `posts_summary` for each individual post.

### S1 — Visual Quality Score
**Range:** 0–50 | **Engine:** `vision_s1_engine.py`

Scored by Gemini Vision analyzing the post image/thumbnail. Composed of 4 sub-dimensions (each 0–10):

| Sub-score | What it measures |
|---|---|
| `composition` | Framing, rule of thirds, layout |
| `lighting` | Lighting quality and clarity |
| `subject_clarity` | How clear and in-focus the main subject is |
| `aesthetic_quality` | Overall visual appeal and style |

```
S1_raw = composition + lighting + subject_clarity + aesthetic_quality  (max 40)
S1 = S1_raw * 1.25  (scaled to 0-50)
```

> **Note:** In our run, S1 = 20.25 uniformly due to some Gemini rate-limit hits. This is the "no vision signal" fallback baseline value — not a true individual post assessment.

---

### S2 — Caption Effectiveness Score
**Range:** 0–50 | **Engine:** `caption_s2_engine.py`

Pure **text analysis** of the post caption. Composed of 4 sub-dimensions (each 0–100, then mapped to 0–50):

| Sub-score | What it measures |
|---|---|
| `hook_score_0_100` | Opening line strength — does it grab attention? |
| `length_score_0_100` | Is the caption an optimal length? |
| `hashtag_score_0_100` | Quality and relevance of hashtags used |
| `cta_score_0_100` | Presence of call-to-action (comment/save/share) |

```
S2_raw = weighted_average(hook, length, hashtag, cta)
S2 = S2_raw / 2  (scaled to 0–50)
```

> Posts with **empty captions** score S2 = 12.5 (the minimum floor). Posts with strong captions like "Not everyone gets access..." score higher (S2 = 44.0).

---

### S3 — Content Clarity Score
**Range:** 0–50 | **Engine:** `vision_s3_engine.py`

Measures **how clearly the post communicates a single coherent message**, combining visual + caption signals. 5 sub-dimensions (each 0–10):

| Sub-score | What it measures |
|---|---|
| `message_singularity` | Does the post have a single clear message? |
| `context_clarity` | Is the context immediately understandable? |
| `caption_alignment` | Does the caption support what the visual shows? |
| `visual_message_support` | Does the visual reinforce the message? |
| `cognitive_load` | Is the post easy to process (low clutter)? |

```
S3 = sum of 5 sub-scores  (max 50)
```

---

### S4 — Audience Relevance Score
**Range:** 0–50 | **Engine:** `s4_audience_relevance_engine.py`

Measures how well the **post topic fits the creator's dominant niche**.

Determined by the **affinity band** between the post's category and creator's dominant category:

| Affinity Band | Score |
|---|---|
| `EXACT` — post topic matches creator niche | High |
| `ADJACENT` — related but not exact | Medium |
| `UNRELATED` — off-brand | Low |
| `UNKNOWN` — no category data | Neutral (25.0) |

```
S4 = s4_raw_0_100 / 2  (scaled to 0–50)
```

> In our run, S4 = 25.0 uniformly → `UNKNOWN` affinity because post categories haven't been classified yet.

---

### S5 — Engagement Potential Score
**Range:** 0–50 | **Engine:** AI-derived (LLM)

The **only AI-generated score** — the LLM evaluates likely audience engagement. 5 sub-dimensions (each 0–10):

| Sub-score | What it measures |
|---|---|
| `emotional_resonance` | Does it evoke emotion? |
| `shareability` | Would people share it? |
| `save_worthiness` | Would people save it for later? |
| `comment_potential` | Does it invite comments/discussion? |
| `novelty_or_value` | Is it original or useful? |

```
S5 = sum of 5 sub-scores  (max 50)
```

---

### S6 — Brand Safety Score
**Range:** 0–50 | **Engine:** `s6_brand_safety_engine.py`

Fully **deterministic rule-based score** — checks for risky content in captions/flags.

Starts at 100/100 and **deducts penalty points** for:
- Profanity or harmful language
- Hashtag spam
- Sensitive brand mentions
- Other flagged content

```
S6_raw = 100 - sum(penalties)
S6 = S6_raw / 2  (scaled to 0–50)
```

> All 30 posts scored S6 = 50.0 (perfect) → no brand safety issues detected anywhere.

---

### P — Weighted Post Score
**Range:** 0–100 | **Engine:** `post_weighted_score_engine.py`

The **composite score for a single post**, calculated by taking a weighted average of S1–S6 (and S7 for Reels):

**Weights for IMAGE posts:**

| Score | Weight |
|---|---|
| S1 | 23% |
| S2 | 22% |
| S3 | 15% |
| S4 | 15% |
| S5 | 15% |
| S6 | 10% |

**Weights for REEL posts:**

| Score | Weight |
|---|---|
| S1 | 20% |
| S2 | 20% |
| S3 | 15% |
| S4 | 15% |
| S5 | 15% |
| S6 | 10% |
| S7 (watch-through) | 5% |

```
P_normalized = Σ(Si × weight_i) / Σ(available weights)   [0..50]
P = P_normalized × 2                                       [0..100]
```

---

### `predicted_er` — Predicted Engagement Rate
Computed from the tier-level average ER scaled by S5:

```
predicted_er = tier_avg_engagement_rate × (S5 / 50)
```

Returns `null` when tier ER benchmarks are unavailable (as in our run).

---

## 4. Drivers & Recommendations

### `drivers`
A list of signal-driven insights. Each driver is either:
- **LIMITING** — a factor holding the account back
- *(AMPLIFYING drivers planned but not yet triggered in this result)*

Triggered automatically when a pillar score drops below 50.

### `recommendations`
Actionable steps ranked by `impact_level`:
- `HIGH` — directly addresses a limiting driver
- `MEDIUM` — supplementary improvement

---

## 5. Metadata

| Field | Meaning |
|---|---|
| `post_count_used` | Number of posts analyzed (max 30 most recent) |
| `min_history_threshold_met` | `true` if ≥ 10 posts available (sufficient confidence) |
| `time_window_days` | Days between oldest and newest post in the analysis window |

---

## ig_dhirendra Result Summary

| Metric | Value | Interpretation |
|---|---|---|
| AHS Score | **63.08** | STRONG — solid but improvable |
| Content Quality | 45.68 | AVERAGE — S1/S3 dragging it down (vision fallback) |
| Engagement Quality | 70.0 | STRONG — good engagement relative to absolute benchmarks |
| Niche Fit | 50.0 | AVERAGE — post categories not yet classified (S4 = UNKNOWN) |
| Consistency | 62.5 | STRONG — posting cadence is decent, P scores fairly stable |
| Brand Safety | 100.0 | EXCEPTIONAL — zero risky content detected |
| Best post (P) | 62.38 | "Not everyone gets access…" — strong caption (S2=44) |
| Weakest posts (P) | 48.22 | Captionless images — S2 floors at 12.5 |



