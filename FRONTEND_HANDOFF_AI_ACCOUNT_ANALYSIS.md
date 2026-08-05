# Frontend Handoff: AI Account Analysis Dashboard

**For:** Frontend Developer
**API Endpoint:** `GET /api/account-analysis/{account_id}`
**Response Model:** `AccountHealthScore` (all new fields are optional/nullable)

---

## API Response Schema

Every field below is returned in a single JSON response. All new dashboard fields are optional — the frontend must handle `null` values gracefully.

```json
{
  "ahs_score": 86.4,
  "ahs_band": "STRONG",
  "growth_stage": "Growing",
  "pillars": { ... },
  "drivers": [ ... ],
  "recommendations": [ ... ],
  "metadata": { "post_count_used": 25, "min_history_threshold_met": true, "time_window_days": 30 },
  "brand_readiness": { ... },
  "core_metrics": { ... },
  "growth_overview_chart": [ ... ],
  "content_type_performance": { ... },
  "content_pillars": [ ... ],
  "engagement_heatmap": [ ... ],
  "top_hashtags": [ ... ],
  "top_posts": [ ... ],
  "audience_insights": null,
  "niche_benchmark": { ... },
  "audience_demographics": [],
  "conversion_funnel": { ... },
  "ai_summary": { ... }
}
```

---

## Section-by-Section Guide

### 1. Account Header

**Source:** Account metadata (not in `AccountHealthScore` — provided by the route layer)

| Field | Type | Display |
|---|---|---|
| `username` | `string` | @handle |
| `niche` | `string` | Category label |
| `post_count` | `int` | "X Posts" |
| `follower_count` | `int` | "XK Followers" |
| `following_count` | `int` | "X Following" |

---

### 2. Account Health Score

**Source:** `ahs_score`, `ahs_band`

| Field | Type | Display |
|---|---|---|
| `ahs_score` | `float` (0-100) | Circular gauge number |
| `ahs_band` | `string` | Label below gauge |

**Band-to-label mapping:**
| `ahs_band` | Display Label | Color |
|---|---|---|
| `EXCEPTIONAL` | Excellent | Green |
| `STRONG` | Very Good | Blue |
| `AVERAGE` | Good | Yellow |
| `NEEDS_WORK` | Needs Work | Red |

---

### 3. Growth Stage

**Source:** `growth_stage`

| Field | Type | Display |
|---|---|---|
| `growth_stage` | `string \| null` | Label + trend arrow |

**Values:** `"Thriving"`, `"Growing"`, `"Developing"`, `"Needs Attention"`

**Handling:** If `null`, hide the section.

---

### 4. Brand Readiness Score

**Source:** `brand_readiness`

| Field | Type | Display |
|---|---|---|
| `brand_readiness.score` | `float` (0-100) | Circular gauge |
| `brand_readiness.label` | `string` | "Highly Marketable", "Marketable", "Developing", "Early Stage" |
| `brand_readiness.est_rate_per_post` | `float \| null` | "$X,XXX" (single value) |
| `brand_readiness.est_cpm` | `float \| null` | "$XX.X" |

**Handling:** If `brand_readiness` is `null`, hide section.

---

### 5. Core Metrics Row

**Source:** `core_metrics`

| Field | Type | Display |
|---|---|---|
| `core_metrics.followers.current_value` | `float` | "45.2K" |
| `core_metrics.followers.trend_percentage` | `float \| null` | "↑ 8.7%" (green if positive, red if negative) |
| `core_metrics.reach_30d.current_value` | `float` | "312K" |
| `core_metrics.reach_30d.trend_percentage` | `float \| null` | "↑ 12.4%" |
| `core_metrics.impressions_30d.current_value` | `float` | "987K" |
| `core_metrics.impressions_30d.trend_percentage` | `float \| null` | "↑ 15.3%" |
| `core_metrics.engagement_rate.current_value` | `float` | "4.8%" |
| `core_metrics.engagement_rate.trend_percentage` | `float \| null` | "↑ 0.6pp" |
| `core_metrics.profile_visits_30d.current_value` | `float` | "18.7K" |
| `core_metrics.profile_visits_30d.trend_percentage` | `float \| null` | "↑ 10.2%" |
| `core_metrics.visit_to_follow_rate.current_value` | `float` | "3.2%" |
| `core_metrics.visit_to_follow_rate.trend_percentage` | `float \| null` | "↑ 0.4pp" |

**Number formatting:**
- >= 1,000,000: divide by 1,000,000 → "1.2M"
- >= 1,000: divide by 1,000 → "45.2K"
- < 1,000: show as-is

**Handling:** If `core_metrics` is `null`, show "Data unavailable" placeholders.

---

### 6. Growth Overview Chart (30 Days)

**Source:** `growth_overview_chart`

| Field | Type | Display |
|---|---|---|
| `growth_overview_chart` | `list[ChartSeries]` | Multi-line chart |

**Each point:**
| Field | Type | Display |
|---|---|---|
| `date` | `string` (ISO-8601) | X-axis label |
| `followers` | `float \| null` | Followers line (may be flat) |
| `reach` | `float \| null` | Reach line |
| `impressions` | `float \| null` | Impressions line |

**Note:** The `followers` line may be flat (same value for all points) because Instagram API doesn't provide historical daily follower data. This is expected.

**Handling:** If `growth_overview_chart` is empty or `null`, hide chart.

---

### 7. Engagement Rate by Content Type

**Source:** `content_type_performance`

| Field | Type | Display |
|---|---|---|
| `content_type_performance.breakdown` | `list[ContentTypeBreakdownEntry]` | Bar chart |
| `content_type_performance.best_for_views` | `string \| null` | "REEL leads views" |
| `content_type_performance.best_for_engagement` | `string \| null` | "REEL leads engagement" |
| `content_type_performance.insight` | `string \| null` | Summary text |

**Each entry:**
| Field | Type | Display |
|---|---|---|
| `content_type` | `string` | Bar label (REEL, CAROUSEL, IMAGE) |
| `avg_engagement_rate` | `float \| null` | Y-axis value (multiply by 100 for %) |
| `post_count` | `int` | "X posts" subtitle |
| `percentage_of_total` | `float` | "% of total" |

**Handling:** If `content_type_performance` is `null` or `breakdown` is empty, hide chart.

---

### 8. Content Pillars (by Engagement)

**Source:** `content_pillars`

| Field | Type | Display |
|---|---|---|
| `content_pillars` | `list[ContentPillar]` | Ranked list with bars |

**Each pillar:**
| Field | Type | Display |
|---|---|---|
| `name` | `string` | Pillar name |
| `engagement_percentage` | `float` (0-100) | Horizontal bar width + "X.X%" |

**Sorted by:** `engagement_percentage` descending (already sorted by backend).

**Handling:** If empty or `null`, hide section.

---

### 9. Engagement Heatmap

**Source:** `engagement_heatmap`

| Field | Type | Display |
|---|---|---|
| `engagement_heatmap` | `list[HeatmapData]` | 7×24 grid |

**Each cell:**
| Field | Type | Display |
|---|---|---|
| `day_of_week` | `int` (0-6) | Row (0=Mon, 6=Sun) |
| `hour_of_day` | `int` (0-23) | Column |
| `intensity` | `float` (0.0-1.0) | Color intensity (dark=low, bright=high) |

**Color scale:** Use a gradient from dark purple (0.0) to bright pink/orange (1.0).

**Handling:** If empty or `null`, hide heatmap.

---

### 10. Best Times to Post

**Source:** `ai_summary.best_posting_time`

| Field | Type | Display |
|---|---|---|
| `ai_summary.best_posting_time` | `string \| null` | "Mon 19:00, Wed 18:00, Fri 12:00" |

**Format:** Comma-separated list of "Day Hour:00" slots.

**Handling:** If `null`, show "Data unavailable".

---

### 11. Top Performing Posts

**Source:** `top_posts`

| Field | Type | Display |
|---|---|---|
| `top_posts` | `list[TopPostSummary]` | Top 3-5 post cards |

**Each post:**
| Field | Type | Display |
|---|---|---|
| `media_id` | `string \| null` | Post ID (for linking) |
| `caption_preview` | `string \| null` | Truncated caption (max 100 chars) |
| `media_type` | `string \| null` | Content type badge (REEL, CAROUSEL, IMAGE) |
| `published_at` | `string \| null` | ISO-8601 date → "May 26" format |
| `engagement_rate` | `float \| null` | "6.8%" (multiply by 100) |
| `reach` | `float \| null` | "45K" |

**Note:** Thumbnail images are not available from the API. Use a placeholder icon based on `media_type`.

**Handling:** If empty or `null`, hide section.

---

### 12. Top 10 Hashtags Performance

**Source:** `top_hashtags`

| Field | Type | Display |
|---|---|---|
| `top_hashtags` | `list[HashtagPerformance]` | Table |

**Each hashtag:**
| Field | Type | Display |
|---|---|---|
| `hashtag` | `string` | "#fashion" |
| `post_count` | `int` | "24" |
| `reach` | `float \| null` | "128K" |
| `engagement_rate` | `float \| null` | "5.2%" (multiply by 100) |
| `impact` | `string` | Badge: "Keep" (green), "Test" (yellow), "Drop" (red) |

**Sorted by:** `post_count` descending (already sorted by backend).

**Handling:** If empty or `null`, hide section.

---

### 13. Audience Insights

**Source:** `audience_insights`

| Field | Type | Display |
|---|---|---|
| `audience_insights` | `AudienceInsights \| null` | 4 sub-cards |

**Sub-cards:**

**New vs Returning Viewers (donut chart):**
| Field | Type | Display |
|---|---|---|
| `new_viewers_pct` | `float \| null` | "62% New Viewers" |
| `returning_viewers_pct` | `float \| null` | "38% Returning" |

**Follower Quality Score:**
| Field | Type | Display |
|---|---|---|
| `follower_quality_score` | `float \| null` | Gauge 0-100, "87/100" |

**Non-Follower Reach:**
| Field | Type | Display |
|---|---|---|
| `non_follower_reach_pct` | `float \| null` | "68% Good discovery" |

**Comment Sentiment (donut chart):**
| Field | Type | Display |
|---|---|---|
| `comment_sentiment_positive_pct` | `float \| null` | Green slice |
| `comment_sentiment_neutral_pct` | `float \| null` | Gray slice |
| `comment_sentiment_negative_pct` | `float \| null` | Red slice |

**Handling:** If `audience_insights` is `null`, show "Data unavailable — no audience data from Instagram API" message.

---

### 14. You vs Niche Benchmark

**Source:** `niche_benchmark`

| Field | Type | Display |
|---|---|---|
| `niche_benchmark.engagement_rate_vs_niche` | `float \| null` | Ratio (e.g., 1.33 = 33% above niche) |
| `niche_benchmark.reach_vs_niche` | `float \| null` | Ratio (currently `null`) |
| `niche_benchmark.growth_vs_niche` | `float \| null` | Ratio (currently `null`) |

**Display:** Horizontal bar comparing "You" vs "Niche Avg" for each metric.

**Handling:** If all three fields are `null`, hide the section. Only show rows where the value is not `null`.

---

### 15. Audience Top Countries

**Source:** `audience_demographics`

| Field | Type | Display |
|---|---|---|
| `audience_demographics` | `list[AudienceDemographics]` | Country list with bars |

**Each country:**
| Field | Type | Display |
|---|---|---|
| `country` | `string` | Country name + flag emoji |
| `percentage` | `float` (0-100) | Percentage bar |

**Handling:** If empty list `[]`, show "Data unavailable — demographics not exposed by Instagram API".

---

### 16. Profile Conversion Funnel

**Source:** `conversion_funnel`

| Field | Type | Display |
|---|---|---|
| `conversion_funnel.profile_visits` | `int \| null` | "18,700" |
| `conversion_funnel.website_clicks` | `int \| null` | "2,450" |
| `conversion_funnel.follows` | `int \| null` | "1,200" |
| `conversion_funnel.profile_visit_to_follow_pct` | `float \| null` | "6.4%" (already a percentage) |

**Display:** Funnel visualization: Profile Visits → Website Clicks → Follows

**Note:** `follows` is synthetic (15% of profile visits) until real API data is available. Consider showing "Estimated" label.

**Handling:** If `conversion_funnel` is `null` or all fields are `null`, hide section.

---

### 17. AI Recommendations

**Source:** `recommendations`

| Field | Type | Display |
|---|---|---|
| `recommendations` | `list[DeterministicRecommendation]` | List with impact badges |

**Each recommendation:**
| Field | Type | Display |
|---|---|---|
| `id` | `string` | Unique identifier |
| `text` | `string` | Recommendation text |
| `impact_level` | `string` | Badge: "HIGH" (red), "MEDIUM" (yellow), "LOW" (green) |

**Sorted by:** Impact level (HIGH first), then generation order.

**Handling:** If empty, show "No recommendations available".

---

### 18. AI Summary

**Source:** `ai_summary`

| Field | Type | Display |
|---|---|---|
| `ai_summary.text_summary` | `string \| null` | Full-width text paragraph |
| `ai_summary.top_content_type` | `string \| null` | "Reels" card |
| `ai_summary.best_posting_time` | `string \| null` | "6PM – 10PM" card |
| `ai_summary.top_content_pillar` | `string \| null` | "Outfit Ideas" card |
| `ai_summary.growth_potential` | `string \| null` | "High" card |

**Handling:** If `ai_summary` is `null`, hide the entire summary section.

---

## Number Formatting Rules

| Range | Format | Example |
|---|---|---|
| >= 1,000,000 | `X.XM` | 1,200,000 → "1.2M" |
| >= 1,000 | `X.XK` | 45,200 → "45.2K" |
| >= 100 | `X.X%` | 4.8 → "4.8%" |
| < 100 | `X.X` | 3.2 → "3.2" |

**Engagement rates** are returned as decimals (0.048 = 4.8%). Multiply by 100 for display.

---

## Color Palette Reference

| Element | Color | Usage |
|---|---|---|
| Green | `#10b981` | Positive trends, "Keep" badges, "HIGH" scores |
| Blue | `#3b82f6` | Neutral/info, STRONG band |
| Yellow | `#f59e0b` | "MEDIUM" impact, "Test" badges |
| Red | `#ef4444` | Negative trends, "DROP" badges, "LOW" scores |
| Purple | `#8b5cf6` | Primary accent, gauges |
| Dark bg | `#0f172a` | Card backgrounds |

---

## Empty State Handling

| Field is... | Frontend action |
|---|---|
| `null` | Show "Data unavailable" or hide section |
| Empty list `[]` | Show "No data" or hide section |
| `0` or `0.0` | Show as-is (could be legitimate) |

**Never show fake data.** If a field is `null`, say so.

---

## File Reference

| File | Purpose |
|---|---|
| `backend/app/domain/account_models.py` | All Pydantic models (source of truth) |
| `backend/app/analytics/account_health_engine.py` | All computation logic |
| `backend/app/api/account_analysis_routes.py` | API endpoint |
| `frontend/src/pages/Dashboard.jsx` | Existing dashboard (reference) |
