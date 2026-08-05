# 🚀 Frontend Developer Guide — AI Account Analysis Dashboard

**Prepared for:** Frontend Developer  
**Feature:** Instagram Account AI Analysis Dashboard  
**Version:** v1.0 (Current Production)  
**Backend Source of Truth:** [`account_models.py`](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/account_models.py)  
**Last Updated:** 2026-07-26

---

## 📌 Quick Reference

| Item | Value |
|------|-------|
| **Trigger endpoint** | `POST /api/account-analysis` |
| **Poll endpoint** | `GET /api/account-analysis/{job_id}` |
| **Auth** | `Authorization: Bearer <access_token>` |
| **Response model** | `AccountHealthScore` (inside `result`) |
| **All new fields** | **Optional / nullable** — always handle `null` gracefully |
| **Total dashboard sections** | 18 |

---

## 🔄 How the API Works (Job Flow)

The analysis is **asynchronous**. The frontend must:

1. **Submit** a `POST /api/account-analysis` request → get a `job_id`
2. **Poll** `GET /api/account-analysis/{job_id}` until `status === "succeeded"`
3. **Render** the dashboard from `response.result`

### Step 1 — Submit Job

```http
POST /api/account-analysis
Authorization: Bearer <token>
Content-Type: application/json

{
  "account_id": "acct_123",
  "post_limit": 30
}
```

**Response:**
```json
{
  "job_id": "3fce6c96-6f57-4df6-8e29-a1ea805181a6",
  "status": "queued"
}
```

### Step 2 — Poll Status

```http
GET /api/account-analysis/{job_id}
Authorization: Bearer <token>
```

**Response shape:**
```json
{
  "job_id": "...",
  "status": "queued | started | succeeded | failed",
  "created_at": "datetime",
  "started_at": "datetime | null",
  "finished_at": "datetime | null",
  "progress": {
    "stage": "aggregate",
    "done": 25,
    "total": 30
  },
  "error": null,
  "result": { ... }   ← null until status === "succeeded"
}
```

> **Polling strategy:** Poll every **3 seconds** while `status` is `queued` or `started`. Stop when `succeeded` or `failed`. Expected time: **5–60 seconds** depending on post count.

### Stale Job Detection

| Status | Stale threshold | What happens |
|--------|----------------|--------------|
| `queued` | > 15 minutes since `created_at` | API returns synthetic `failed` with `error.type = "TimeoutError"` |
| `started` | > 30 minutes since `started_at` | Same |

> Show the user a "This is taking longer than usual" message after 30 seconds of polling.

### Error Handling

| HTTP Code | Meaning | Frontend action |
|-----------|---------|-----------------|
| `401` | Invalid/expired token | Redirect to login |
| `403` | No permission | Show "access denied" |
| `404` | Unknown `job_id` | Show "analysis not found" |
| `422` | Bad request body | Show validation error |
| `429` | Rate limit (3/hour/account) | Show "Try again in 1 hour" |
| `500` | Server error | Show generic error, offer retry |

---

## 📦 Full API Response Structure

The `result` object inside the poll response matches `AccountHealthScore`. Here is the complete annotated shape:

```json
{
  "ahs_score": 86.4,
  "ahs_band": "STRONG",
  "growth_stage": "Growing",

  "pillars": {
    "content_quality":  { "score": 85.0, "band": "STRONG",      "notes": ["..."] },
    "engagement_quality":{ "score": 74.0, "band": "STRONG",     "notes": ["..."] },
    "niche_fit":        { "score": 65.0, "band": "AVERAGE",     "notes": ["..."] },
    "consistency":      { "score": 72.0, "band": "STRONG",      "notes": ["..."] },
    "brand_safety":     { "score": 100.0,"band": "EXCEPTIONAL", "notes": ["..."] }
  },

  "drivers": [
    { "id": "strong_save_rate", "label": "High Save Rate", "type": "POSITIVE", "explanation": "..." },
    { "id": "weak_visual_hook", "label": "Weak Visual Hook", "type": "LIMITING", "explanation": "..." }
  ],

  "recommendations": [
    { "id": "improve_hook", "text": "Improve opening hook...", "impact_level": "HIGH" }
  ],

  "metadata": {
    "post_count_used": 25,
    "min_history_threshold_met": true,
    "time_window_days": 30
  },

  "brand_readiness": {
    "score": 82.0,
    "label": "Highly Marketable",
    "est_rate_per_post": 1500.0,
    "est_rate_per_post_min": 1200.0,
    "est_rate_per_post_max": 1800.0,
    "est_cpm": 22.5
  },

  "core_metrics": {
    "followers":           { "current_value": 45200,  "trend_percentage": 8.7,  "label": "Followers" },
    "reach_30d":           { "current_value": 312000, "trend_percentage": 12.4, "label": "30D Reach" },
    "impressions_30d":     { "current_value": 987000, "trend_percentage": 15.3, "label": "30D Impressions" },
    "engagement_rate":     { "current_value": 4.8,    "trend_percentage": 0.6,  "label": "Engagement Rate" },
    "profile_visits_30d":  { "current_value": 18700,  "trend_percentage": 10.2, "label": "30D Profile Visits" },
    "visit_to_follow_rate":{ "current_value": 3.2,    "trend_percentage": 0.4,  "label": "Visit-to-Follow Rate" }
  },

  "growth_overview_chart": [
    { "date": "2024-05-20", "followers": 42100, "reach": 28000, "impressions": 85000 },
    { "date": "2024-05-27", "followers": 42800, "reach": 31000, "impressions": 92000 }
  ],

  "content_type_performance": {
    "breakdown": [
      {
        "content_type": "REEL",
        "post_count": 18,
        "percentage_of_total": 60.0,
        "avg_views": 45000,
        "total_views": 810000,
        "avg_engagement_rate": 0.056,
        "avg_likes": 2100,
        "avg_comments": 85,
        "avg_saves": 320,
        "avg_shares": 95,
        "avg_weighted_score": 72.5,
        "views_share_percent": 74.2
      }
    ],
    "best_for_views": "REEL",
    "best_for_engagement": "REEL",
    "insight": "Reels outperform other formats by 2.1x",
    "notes": []
  },

  "content_pillars": [
    { "name": "outfit ideas",  "engagement_percentage": 28.5 },
    { "name": "styling tips",  "engagement_percentage": 22.1 }
  ],

  "engagement_heatmap": [
    { "day_of_week": 0, "hour_of_day": 19, "intensity": 0.92 },
    { "day_of_week": 2, "hour_of_day": 18, "intensity": 0.87 }
  ],

  "top_hashtags": [
    {
      "hashtag": "#fashion",
      "post_count": 24,
      "reach": 128000,
      "engagement_rate": 0.052,
      "impact": "Keep"
    }
  ],

  "top_posts": [
    {
      "media_id": "abc123",
      "caption_preview": "5 Summer Outfit Ideas that...",
      "media_type": "REEL",
      "published_at": "2024-05-26T14:00:00Z",
      "engagement_rate": 0.068,
      "reach": 45000
    }
  ],

  "audience_insights": {
    "new_viewers_pct": 62.0,
    "returning_viewers_pct": 38.0,
    "follower_quality_score": 87.0,
    "non_follower_reach_pct": 68.0,
    "comment_sentiment_positive_pct": 72.0,
    "comment_sentiment_neutral_pct": 18.0,
    "comment_sentiment_negative_pct": 10.0,
    "is_estimated": true
  },

  "niche_benchmark": {
    "engagement_rate_vs_niche": 1.33,
    "reach_vs_niche": null,
    "growth_vs_niche": null
  },

  "audience_demographics": [
    { "country": "India",         "percentage": 62.0 },
    { "country": "United States", "percentage": 12.0 }
  ],

  "conversion_funnel": {
    "profile_visits": 18700,
    "website_clicks": 2450,
    "follows": 1200,
    "profile_visit_to_follow_pct": 6.4
  },

  "ai_summary": {
    "text_summary": "Your account is growing strongly with excellent reach...",
    "top_content_type": "REEL",
    "best_posting_time": "Mon 19:00, Wed 18:00, Fri 12:00",
    "top_content_pillar": "outfit ideas",
    "growth_potential": "High"
  }
}
```

> ⚠️ **Important:** The `result` key is directly nested **inside the job poll response**, not returned from a separate endpoint. Always read `response.result` when `status === "succeeded"`.

---

## 🗂️ Section-by-Section Data Guide

Each section below maps exactly to what the backend returns. Every field listed is what you'll read from `response.result`.

---

### Section 1 — Account Header

> **Source:** Route layer (not inside `result`) — provided as account metadata alongside the job.

| Field | Type | Display |
|-------|------|---------|
| `username` | `string` | `@handle` |
| `niche` | `string` | Category label/chip |
| `post_count` | `int` | "42 Posts" |
| `follower_count` | `int` | "45.2K Followers" |
| `following_count` | `int` | "312 Following" |

> Thumbnail / profile picture is not available from the API. Use a generic avatar placeholder.

---

### Section 2 — Account Health Score (AHS)

> **Source:** `result.ahs_score`, `result.ahs_band`

| Field | Type | Range | Display |
|-------|------|-------|---------|
| `ahs_score` | `float` | 0–100 | Circular gauge with number |
| `ahs_band` | `string` | See below | Colour-coded label |

**Band → Label → Colour:**

| `ahs_band` | Display Label | Color |
|------------|--------------|-------|
| `EXCEPTIONAL` | Excellent | `#10b981` (green) |
| `STRONG` | Very Good | `#3b82f6` (blue) |
| `AVERAGE` | Good | `#f59e0b` (yellow) |
| `NEEDS_WORK` | Needs Work | `#ef4444` (red) |

---

### Section 3 — Growth Stage

> **Source:** `result.growth_stage`

| Field | Type | Display |
|-------|------|---------|
| `growth_stage` | `string \| null` | Label + trend arrow icon |

**Possible values:** `"Thriving"`, `"Growing"`, `"Stable"`, `"Developing"`, `"Needs Attention"`

**Null handling:** If `null`, **hide** this section entirely.

---

### Section 4 — Five Pillar Scores

> **Source:** `result.pillars`

Five pillars are always present (unless the analysis failed). Each is a `PillarScore` object:

```json
{
  "score": 85.0,
  "band": "STRONG",
  "notes": ["This creator posts consistently across formats"]
}
```

| Pillar key | Display name |
|------------|-------------|
| `content_quality` | Content Quality |
| `engagement_quality` | Engagement Quality |
| `niche_fit` | Niche Fit |
| `consistency` | Consistency |
| `brand_safety` | Brand Safety |

**Display:** Radar/spider chart is ideal. Fallback: 5 horizontal progress bars (score out of 100).  
**Band colours** are the same as AHS band (EXCEPTIONAL=green, STRONG=blue, AVERAGE=yellow, NEEDS_WORK=red).  
**Notes:** Show as a tooltip or expandable list on each pillar card.

---

### Section 5 — Brand Readiness Score

> **Source:** `result.brand_readiness`

| Field | Type | Display |
|-------|------|---------|
| `score` | `float` (0–100) | Circular gauge |
| `label` | `string` | Label below gauge |
| `est_rate_per_post` | `float \| null` | Mid-point rate "$1,500/post" |
| `est_rate_per_post_min` | `float \| null` | Range low "$1,200" |
| `est_rate_per_post_max` | `float \| null` | Range high "$1,800" |
| `est_cpm` | `float \| null` | "$22.5 CPM" |

**Labels and their meanings:**
| Score range | `label` | Meaning |
|-------------|---------|---------|
| 75–100 | Highly Marketable | Ready for paid partnerships |
| 50–74 | Marketable | Good for select partnerships |
| 25–49 | Developing | 2–4 more weeks of growth needed |
| 0–24 | Early Stage | Not yet recommended for brand deals |

**Rate display format:**  
- Show as range: "$1,200 – $1,800 / post"  
- If `est_rate_per_post_min` and `_max` are `null`, show `est_rate_per_post` as a single value  
- If all rate fields are `null`, hide the rate row

**Null handling:** If `brand_readiness` is `null`, hide this section.

---

### Section 6 — Core Metrics Row

> **Source:** `result.core_metrics`

Six metric cards, each structured as `MetricWithTrend`:

```json
{ "current_value": 45200, "trend_percentage": 8.7, "label": "Followers" }
```

| Metric key | `label` | Value format | Trend format |
|------------|---------|--------------|-------------|
| `followers` | Followers | "45.2K" | "↑ 8.7%" |
| `reach_30d` | 30D Reach | "312K" | "↑ 12.4%" |
| `impressions_30d` | 30D Impressions | "987K" | "↑ 15.3%" |
| `engagement_rate` | Engagement Rate | "4.8%" | "↑ 0.6pp" |
| `profile_visits_30d` | 30D Profile Visits | "18.7K" | "↑ 10.2%" |
| `visit_to_follow_rate` | Visit-to-Follow Rate | "3.2%" | "↑ 0.4pp" |

**Number formatting:**
```
>= 1,000,000  →  "1.2M"
>= 1,000      →  "45.2K"
< 1,000       →  as-is (e.g. "312")
```

**Engagement rate / visit-to-follow special label:** Use `"pp"` (percentage points) for trend instead of `"%"` when the value itself is already a percentage.

**Trend colour:** Green `#10b981` if positive, Red `#ef4444` if negative, Grey if `null`.

**Null handling:** If `core_metrics` is `null`, show "Data unavailable" placeholder cards.

---

### Section 7 — Growth Overview Chart (30 Days)

> **Source:** `result.growth_overview_chart`

Each data point:
```json
{ "date": "2024-05-20", "followers": 42100, "reach": 28000, "impressions": 85000 }
```

| Field | Type | Chart role |
|-------|------|-----------|
| `date` | `string` (ISO-8601) | X-axis label (format: "May 20") |
| `followers` | `float \| null` | Line 1 (may be flat — see note) |
| `reach` | `float \| null` | Line 2 |
| `impressions` | `float \| null` | Line 3 |

> **⚠️ Followers flat line is expected.** Instagram API doesn't expose daily follower history. The backend sets followers to the same value for every data point. Do NOT treat this as a bug.

**Chart library suggestions:** Recharts, Chart.js, ApexCharts  
**Null handling:** If `growth_overview_chart` is `null` or empty `[]`, hide chart completely.

---

### Section 8 — Engagement by Content Type

> **Source:** `result.content_type_performance`

The `breakdown` array contains one entry per content type:

```json
{
  "content_type": "REEL",
  "post_count": 18,
  "percentage_of_total": 60.0,
  "avg_views": 45000,
  "total_views": 810000,
  "avg_engagement_rate": 0.056,
  "avg_likes": 2100,
  "avg_comments": 85,
  "avg_saves": 320,
  "avg_shares": 95,
  "avg_weighted_score": 72.5,
  "views_share_percent": 74.2
}
```

**All available data points for display:**

| Field | Multiply for display | Example output |
|-------|---------------------|----------------|
| `avg_engagement_rate` | × 100 | "5.6%" |
| `avg_views` | format as K/M | "45K" |
| `total_views` | format as K/M | "810K" |
| `avg_likes` | format as K/M | "2.1K" |
| `avg_comments` | as-is | "85" |
| `avg_saves` | as-is | "320" |
| `avg_shares` | as-is | "95" |
| `avg_weighted_score` | as-is | "72.5/100" |
| `views_share_percent` | already % | "74.2%" |
| `percentage_of_total` | already % | "60%" of posts |

**Primary display:** Bar chart with `content_type` on X-axis, `avg_engagement_rate` on Y-axis (× 100 for %).  
**Insight text:** `content_type_performance.insight` — show below chart.  
**Best format badges:** `best_for_views`, `best_for_engagement` — show as "🏆 Best for Reach: REEL".

**Null handling:** If `content_type_performance` is `null` or `breakdown` is empty, hide section.

---

### Section 9 — Content Pillars (by Engagement)

> **Source:** `result.content_pillars`

```json
[
  { "name": "outfit ideas",  "engagement_percentage": 28.5 },
  { "name": "styling tips",  "engagement_percentage": 22.1 },
  { "name": "product hauls", "engagement_percentage": 18.7 }
]
```

| Field | Type | Display |
|-------|------|---------|
| `name` | `string` | Pillar label (capitalize first letter) |
| `engagement_percentage` | `float` (0–100) | Horizontal bar width + "28.5%" label |

**Display:** Ranked list 1–N, sorted descending (already sorted by backend).  
**Null/empty handling:** If `null` or `[]`, hide section.

---

### Section 10 — Engagement Heatmap

> **Source:** `result.engagement_heatmap`

```json
[
  { "day_of_week": 0, "hour_of_day": 19, "intensity": 0.92 },
  { "day_of_week": 2, "hour_of_day": 18, "intensity": 0.87 }
]
```

| Field | Range | Display |
|-------|-------|---------|
| `day_of_week` | 0–6 | Row (0 = Mon, 1 = Tue, ..., 6 = Sun) |
| `hour_of_day` | 0–23 | Column (12 = noon, 19 = 7PM, etc.) |
| `intensity` | 0.0–1.0 | Cell colour darkness |

**Grid:** 7 rows × 24 columns = 168 cells total.  
**Colour scale:** Gradient from dark/muted (0.0 = low engagement) → bright/vivid (1.0 = highest engagement).  
**Suggested palette:** `#1e0038` (0.0) → `#7c3aed` (0.5) → `#f97316` (1.0)

**Missing cells:** Not all 168 combinations will have data. Cells without data should show the lowest intensity colour (not an error state).

**Null/empty handling:** If `null` or `[]`, hide heatmap section.

---

### Section 11 — Best Times to Post

> **Source:** `result.ai_summary.best_posting_time`

```json
"Mon 19:00, Wed 18:00, Fri 12:00"
```

| Field | Type | Display |
|-------|------|---------|
| `best_posting_time` | `string \| null` | Comma-separated time slots |

**Parse and display:** Split by `", "` and render each as a chip/badge.  
Example: `["Mon 7PM", "Wed 6PM", "Fri 12PM"]`

**Null handling:** Show "Not enough post data to determine best times."

---

### Section 12 — Top Performing Posts

> **Source:** `result.top_posts`

```json
[
  {
    "media_id": "abc123",
    "caption_preview": "5 Summer Outfit Ideas that...",
    "media_type": "REEL",
    "published_at": "2024-05-26T14:00:00Z",
    "engagement_rate": 0.068,
    "reach": 45000
  }
]
```

| Field | Type | Display |
|-------|------|---------|
| `media_id` | `string \| null` | Post link (to Instagram, if applicable) |
| `caption_preview` | `string \| null` | Truncated at 120 chars (already trimmed by backend) |
| `media_type` | `string \| null` | Badge: REEL / CAROUSEL / IMAGE |
| `published_at` | ISO-8601 `string \| null` | Format: "May 26" |
| `engagement_rate` | `float \| null` | × 100 → "6.8%" |
| `reach` | `float \| null` | "45K" |

> **Thumbnail images are NOT available.** Use a placeholder icon based on `media_type`:
> - `REEL` → 🎬 or play icon
> - `CAROUSEL` → 📸 or carousel icon
> - `IMAGE` → 🖼️ or image icon

**Sort:** Already sorted by `engagement_rate` descending.  
**Count:** Show top 3–5 posts.  
**Null/empty handling:** If `[]` or `null`, hide section.

---

### Section 13 — Top 10 Hashtags Performance

> **Source:** `result.top_hashtags`

```json
[
  {
    "hashtag": "#fashion",
    "post_count": 24,
    "reach": 128000,
    "engagement_rate": 0.052,
    "impact": "Keep"
  }
]
```

**Display as table:**

| Column | Field | Display |
|--------|-------|---------|
| # | (index) | 1, 2, 3... |
| Hashtag | `hashtag` | "#fashion" |
| Posts | `post_count` | "24" |
| Reach | `reach` | "128K" |
| Engagement | `engagement_rate` | × 100 → "5.2%" |
| Impact | `impact` | Colour-coded badge |

**Impact badge colours:**
| `impact` value | Color | Hex |
|----------------|-------|-----|
| `"Keep"` | Green | `#10b981` |
| `"Test"` | Yellow | `#f59e0b` |
| `"Drop"` | Red | `#ef4444` |

**Sort:** Already sorted by `post_count` descending.  
**Null/empty handling:** If `[]` or `null`, hide section.

---

### Section 14 — Audience Insights

> **Source:** `result.audience_insights`

```json
{
  "new_viewers_pct": 62.0,
  "returning_viewers_pct": 38.0,
  "follower_quality_score": 87.0,
  "non_follower_reach_pct": 68.0,
  "comment_sentiment_positive_pct": 72.0,
  "comment_sentiment_neutral_pct": 18.0,
  "comment_sentiment_negative_pct": 10.0,
  "is_estimated": true
}
```

**Display as 4 sub-cards:**

#### Sub-card A: New vs Returning Viewers (Donut Chart)
| Slice | Field | Colour |
|-------|-------|--------|
| New | `new_viewers_pct` | `#3b82f6` |
| Returning | `returning_viewers_pct` | `#8b5cf6` |

#### Sub-card B: Follower Quality Score
| Field | Display |
|-------|---------|
| `follower_quality_score` | Gauge 0–100, label "87/100 — High Quality" |

#### Sub-card C: Non-Follower Reach
| Field | Display |
|-------|---------|
| `non_follower_reach_pct` | "68% of viewers don't follow yet" — good discovery signal |

#### Sub-card D: Comment Sentiment (Donut Chart)
| Slice | Field | Colour |
|-------|-------|--------|
| Positive | `comment_sentiment_positive_pct` | `#10b981` |
| Neutral | `comment_sentiment_neutral_pct` | `#6b7280` |
| Negative | `comment_sentiment_negative_pct` | `#ef4444` |

**`is_estimated` flag:** If `true`, show a small badge on the section: `"Estimated"` in yellow. This means the data is synthetic, not from real Instagram API.

**Null handling:** If `audience_insights` is `null`, show:  
> "Audience insights unavailable — not yet exposed by the Instagram API for this account."

---

### Section 15 — You vs Niche Benchmark

> **Source:** `result.niche_benchmark`

```json
{
  "engagement_rate_vs_niche": 1.33,
  "reach_vs_niche": null,
  "growth_vs_niche": null
}
```

**Each value is a ratio** (not a percentage):
- `1.33` means "33% above niche average"
- `0.85` means "15% below niche average"
- `null` means data is not available for this metric

**Display:** Horizontal comparison bar for each non-null metric.

| Metric | Formula |
|--------|---------|
| Engagement Rate | `1.33 → "You: +33% vs Niche"` |
| Reach | Only show if not `null` |
| Growth | Only show if not `null` |

**Logic:** `(ratio - 1) * 100` = percentage above/below niche.  
- Above niche: green label "↑ 33% above niche avg"
- Below niche: red label "↓ 15% below niche avg"
- Exactly 1.0: grey "At niche avg"

**Null handling:** If ALL three fields are `null`, **hide the entire section**.

---

### Section 16 — Audience Top Countries

> **Source:** `result.audience_demographics`

```json
[
  { "country": "India",         "percentage": 62.0 },
  { "country": "United States", "percentage": 12.0 },
  { "country": "Pakistan",      "percentage": 8.0 }
]
```

| Field | Display |
|-------|---------|
| `country` | Country name + flag emoji (use a flag emoji library or hard-code top 20) |
| `percentage` | Progress bar (max width = 100%) + "62%" label |

**Null/empty handling:** If `[]` or `null`, show:  
> "Country demographics are not exposed by the Instagram API for this account."

---

### Section 17 — Profile Conversion Funnel

> **Source:** `result.conversion_funnel`

```json
{
  "profile_visits": 18700,
  "website_clicks": 2450,
  "follows": 1200,
  "profile_visit_to_follow_pct": 6.4
}
```

**Display:** Funnel visualization (widest bar at top, narrowing down):

```
Profile Visits       ████████████████████  18,700
Website Clicks       ██████████            2,450   (13.1% of visits)
Follows              ████████              1,200   (6.4% of visits)
```

| Field | Display |
|-------|---------|
| `profile_visits` | "18,700" |
| `website_clicks` | "2,450" |
| `follows` | "1,200" (show "Estimated" badge — see below) |
| `profile_visit_to_follow_pct` | "6.4% visit-to-follow rate" |

> ⚠️ **`follows` is synthetic** (approximated as 15% of profile visits) until real data is available from Instagram. Show an `"Estimated"` badge on the follows row.

**Null handling:** If `conversion_funnel` is `null` or all fields are `null`, hide section.

---

### Section 18 — AI Recommendations

> **Source:** `result.recommendations`

```json
[
  {
    "id": "improve_visual_hook",
    "text": "Improve opening visual hook and framing to raise S1/S3 scores on most posts.",
    "impact_level": "HIGH"
  },
  {
    "id": "post_more_reels",
    "text": "Increase Reel output from 4/week to 5/week based on your engagement data.",
    "impact_level": "MEDIUM"
  }
]
```

| Field | Display |
|-------|---------|
| `text` | Recommendation body |
| `impact_level` | Colour badge: HIGH (red), MEDIUM (yellow), LOW (green) |

**Sort order:** HIGH first, then MEDIUM, then LOW. Already sorted by backend.

**Impact badge:**
```
HIGH   → 🔴 HIGH IMPACT
MEDIUM → 🟡 MEDIUM IMPACT
LOW    → 🟢 LOW IMPACT
```

**Empty handling:** If `[]`, show "No recommendations at this time — great job!"

---

### Section 19 — AI Drivers (Positive & Limiting Factors)

> **Source:** `result.drivers`

```json
[
  {
    "id": "strong_save_rate",
    "label": "High Save Rate",
    "type": "POSITIVE",
    "explanation": "Average save rate of 8.2% significantly exceeds the 5% benchmark."
  },
  {
    "id": "weak_visual_hook",
    "label": "Weak Visual Hook",
    "type": "LIMITING",
    "explanation": "Visual hook strength score is 0.22, below the 0.40 threshold."
  }
]
```

| Field | Display |
|-------|---------|
| `label` | Short title |
| `type` | `POSITIVE` = green ✅, `LIMITING` = red ❌ |
| `explanation` | Detail text (one sentence) |

**Layout suggestion:** Two columns — "What's Working" (POSITIVE) and "Areas to Improve" (LIMITING).

---

### Section 20 — AI Summary

> **Source:** `result.ai_summary`

```json
{
  "text_summary": "Your account is growing strongly with excellent reach...",
  "top_content_type": "REEL",
  "best_posting_time": "Mon 19:00, Wed 18:00, Fri 12:00",
  "top_content_pillar": "outfit ideas",
  "growth_potential": "High"
}
```

**Two display areas:**

#### Full-width text paragraph
`text_summary` — AI-generated narrative. Wrap in a card with a "✨ AI-Generated Summary" label.

#### 4 Highlight Cards
| Card | Field | Example display |
|------|-------|----------------|
| Top Content Type | `top_content_type` | "🎬 Reels" |
| Best Posting Time | `best_posting_time` | "🕖 Mon 7PM, Wed 6PM" |
| Top Content Theme | `top_content_pillar` | "👗 Outfit Ideas" |
| Growth Potential | `growth_potential` | "📈 High" |

**Null handling:** If `ai_summary` is `null`, hide the entire section.

---

## 🎨 Design System Reference

### Colour Palette

| Token | Hex | Usage |
|-------|-----|-------|
| `--color-success` | `#10b981` | Positive trends, Keep badges, POSITIVE drivers |
| `--color-info` | `#3b82f6` | STRONG band, neutral/info states |
| `--color-warning` | `#f59e0b` | MEDIUM impact, Test badges, AVERAGE band |
| `--color-danger` | `#ef4444` | Negative trends, Drop badges, HIGH impact |
| `--color-accent` | `#8b5cf6` | Primary purple accent, gauges |
| `--color-bg-card` | `#0f172a` | Card backgrounds |
| `--color-bg-page` | `#020817` | Page background |
| `--color-text-primary` | `#f1f5f9` | Primary text |
| `--color-text-secondary` | `#94a3b8` | Secondary labels |

### Number Formatting (Utility Function)

```js
function formatValue(value, type = 'number') {
  if (value === null || value === undefined) return '—'
  
  if (type === 'engagement_rate') {
    return `${(value * 100).toFixed(1)}%`  // 0.048 → "4.8%"
  }
  
  if (type === 'percentage') {
    return `${value.toFixed(1)}%`  // already a percentage
  }
  
  if (type === 'number') {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
    if (value >= 1_000)     return `${(value / 1_000).toFixed(1)}K`
    return `${value}`
  }
  
  if (type === 'currency') {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: 'USD', maximumFractionDigits: 0
    }).format(value)
  }
  
  return `${value}`
}
```

### Trend Arrow Formatting

```js
function formatTrend(trendPct) {
  if (trendPct === null || trendPct === undefined) return null
  const arrow = trendPct >= 0 ? '↑' : '↓'
  const colour = trendPct >= 0 ? 'var(--color-success)' : 'var(--color-danger)'
  return { text: `${arrow} ${Math.abs(trendPct).toFixed(1)}%`, colour }
}
```

---

## ⚠️ Empty State Rules

**Never show fake/placeholder numbers.** Follow this table strictly:

| Scenario | Rule |
|----------|------|
| Field is `null` | Show "Data unavailable" text OR hide the section |
| List is `[]` | Show "No data available" OR hide the section |
| Field is `0` or `0.0` | Show as-is — zero is a legitimate value |
| `is_estimated: true` | Add "Estimated" badge — do NOT show as real data |
| `follows` in conversion funnel | Always show "Estimated" badge |
| `audience_demographics` is `[]` | Show specific message about Instagram API limitation |

---

## 🏗️ Suggested Dashboard Layout

```
┌──────────────────────────────────────────────────────────────┐
│  ACCOUNT HEADER (Section 1)                                  │
│  @username  •  45.2K Followers  •  Fashion                   │
├─────────────────┬────────────────┬───────────────────────────┤
│  AHS SCORE      │  GROWTH STAGE  │  BRAND READINESS          │
│  (Section 2)    │  (Section 3)   │  (Section 5)              │
├─────────────────┴────────────────┴───────────────────────────┤
│  5 PILLAR SCORES  (Section 4)                                │
│  [Radar Chart or 5 bars]                                     │
├──────────────────────────────────────────────────────────────┤
│  CORE METRICS ROW  (Section 6)                               │
│  [Followers] [Reach] [Impressions] [ER] [Profile V] [V→F]   │
├──────────────────────────────────────────────────────────────┤
│  GROWTH CHART (Section 7)          │  CONTENT TYPE (Sec 8)  │
│  [Multi-line 30-day chart]         │  [Bar chart]           │
├──────────────────────────────────────────────────────────────┤
│  CONTENT PILLARS (Sec 9)    │  ENGAGEMENT HEATMAP (Sec 10)  │
├──────────────────────────────────────────────────────────────┤
│  BEST POSTING TIMES (Sec 11)       │  TOP POSTS (Sec 12)    │
├──────────────────────────────────────────────────────────────┤
│  HASHTAG PERFORMANCE TABLE  (Section 13)                     │
├──────────────────────────────────────────────────────────────┤
│  AUDIENCE INSIGHTS (Section 14)                              │
│  [Donut] [Quality] [Non-Follower] [Sentiment Donut]          │
├────────────────────────┬─────────────────────────────────────┤
│  NICHE BENCHMARK       │  AUDIENCE COUNTRIES                 │
│  (Section 15)          │  (Section 16)                       │
├──────────────────────────────────────────────────────────────┤
│  CONVERSION FUNNEL  (Section 17)                             │
├──────────────────────────────────────────────────────────────┤
│  AI RECOMMENDATIONS  (Section 18)                            │
├──────────────────────────────────────────────────────────────┤
│  AI DRIVERS  (Section 19) — Positive + Limiting side-by-side │
├──────────────────────────────────────────────────────────────┤
│  AI SUMMARY  (Section 20) — Text + 4 highlight cards         │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔧 API Integration Code Snippet

```js
// accountAnalysisApi.js

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000'

export async function submitAnalysis(accountId, token) {
  const res = await fetch(`${API_BASE}/api/account-analysis`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ account_id: accountId, post_limit: 30 }),
  })
  if (!res.ok) throw new Error(`Submit failed: ${res.status}`)
  return res.json()  // { job_id, status }
}

export async function pollAnalysis(jobId, token) {
  const res = await fetch(`${API_BASE}/api/account-analysis/${jobId}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`Poll failed: ${res.status}`)
  return res.json()  // { job_id, status, progress, result }
}

// Usage example with polling
export async function runAnalysis(accountId, token, onProgress, onComplete, onError) {
  try {
    const { job_id } = await submitAnalysis(accountId, token)
    
    const interval = setInterval(async () => {
      const job = await pollAnalysis(job_id, token)
      
      onProgress(job.progress)  // { stage, done, total }
      
      if (job.status === 'succeeded') {
        clearInterval(interval)
        onComplete(job.result)   // AccountHealthScore
      }
      
      if (job.status === 'failed') {
        clearInterval(interval)
        onError(job.error?.message || 'Analysis failed')
      }
    }, 3000)  // poll every 3 seconds
    
  } catch (err) {
    onError(err.message)
  }
}
```

---

## 📁 Codebase References

| File | Purpose |
|------|---------|
| [`backend/app/domain/account_models.py`](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/account_models.py) | **Source of truth** — all Pydantic models |
| [`backend/app/analytics/account_health_engine.py`](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/analytics/account_health_engine.py) | All computation logic |
| [`backend/app/api/account_analysis_routes.py`](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/api/account_analysis_routes.py) | API route handlers |
| [`API_ENDPOINTS.md`](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/API_ENDPOINTS.md) | Complete API reference |
| [`PRD_AI_ACCOUNT_ANALYSIS_DASHBOARD.md`](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/PRD_AI_ACCOUNT_ANALYSIS_DASHBOARD.md) | Full product requirements |
| [`PRD_ADVANCED_ACCOUNT_ANALYSIS.md`](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/PRD_ADVANCED_ACCOUNT_ANALYSIS.md) | v2.0 advanced features roadmap |

---

## ✅ Developer Checklist

Use this before shipping:

### Data Handling
- [ ] All `null` fields handled gracefully (no "undefined" renders)
- [ ] Engagement rates correctly multiplied ×100 for display (0.048 → "4.8%")
- [ ] Numbers formatted as K/M where needed
- [ ] Trend arrows green for positive, red for negative
- [ ] `is_estimated: true` → shows "Estimated" badge on audience insights
- [ ] `follows` in conversion funnel always shows "Estimated" badge
- [ ] Empty `[]` lists show appropriate empty states

### Sections
- [ ] If `growth_stage` is `null` → section hidden
- [ ] If `brand_readiness` is `null` → section hidden
- [ ] If `niche_benchmark` all `null` → section hidden
- [ ] If `audience_insights` is `null` → API limitation message shown
- [ ] If `audience_demographics` is `[]` → API limitation message shown
- [ ] `followers` line in growth chart accepted as flat (not treated as bug)

### Polling
- [ ] Poll every 3 seconds while `queued` or `started`
- [ ] Stop polling on `succeeded` or `failed`
- [ ] Handle `429` rate limit gracefully (show "try in 1 hour")
- [ ] Handle stale jobs (timeout > 15–30 min) with user-friendly message

### UX
- [ ] Loading skeleton shown while polling
- [ ] Progress bar reflects `progress.done / progress.total`
- [ ] AI-generated content labelled as AI (text_summary, recommendations)
- [ ] Rate range shown as "$1,200 – $1,800 / post" not single value when range available

---

*Questions? Ping the backend team or check the Pydantic models in [`account_models.py`](file:///c:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/account_models.py) — it's the canonical source of truth.*
