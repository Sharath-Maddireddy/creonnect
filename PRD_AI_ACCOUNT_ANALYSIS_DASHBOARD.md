# PRD: Instagram Account AI Analysis Dashboard

**Author:** Engineering Team
**Status:** Draft
**Last Updated:** 2025-07-22
**Target:** Production

---

## 1. Overview

The Instagram Account AI Analysis Dashboard is a comprehensive, single-page view that gives creators and brands a complete picture of an Instagram account's performance, audience, content quality, and growth potential. It replaces fragmented analytics with a unified, AI-powered assessment — combining deterministic metrics (engagement rates, reach, impressions) with AI-generated insights (niche classification, content recommendations, brand readiness).

### 1.1 Background

Currently, creators rely on Instagram's native Insights (limited to 7-day/14-day/30-day windows, no cross-account comparison, no AI analysis) or third-party tools that require separate logins and subscriptions. Our platform already processes post-level data through a multi-engine AI pipeline (S1 visual quality, S2 caption effectiveness, S3 content clarity, S4 audience relevance, S5 engagement potential, S6 brand safety). This dashboard surfaces those backend computations in a single, actionable view.

### 1.2 Target Users

| User | Primary Need |
|---|---|
| **Creator** | Understand account health, identify growth opportunities, optimize posting strategy |
| **Brand Manager** | Assess creator suitability for campaigns, evaluate brand fit and safety |
| **Agency** | Compare multiple creator accounts, prioritize outreach |

---

## 2. Goals and Objectives

| Goal | Success Metric | Target |
|---|---|---|
| Provide a complete account health assessment | All 5 pillar scores populated for accounts with 10+ posts | 100% coverage |
| Surface AI-powered insights without manual analysis | AI Summary, Content Pillars, Hashtag Performance returned in response | Always present |
| Enable brand readiness evaluation | Brand Readiness score + estimated rate/CPM returned | Score 0-100, rate in USD |
| Support data-driven posting decisions | Best Posting Time, Engagement Heatmap, Growth Overview chart | Derived from real post data |
| Maintain backward compatibility | Existing API consumers see no breaking changes | All new fields optional |

---

## 3. User Stories

### 3.1 Creator Stories

| ID | Story | Priority |
|---|---|---|
| US-01 | As a creator, I want to see my Account Health Score so I know how my account is performing overall | P0 |
| US-02 | As a creator, I want to see my core metrics (followers, reach, impressions, engagement rate, profile visits) with trend indicators so I know if I'm improving | P0 |
| US-03 | As a creator, I want to see a growth overview chart so I can visualize my trajectory over the past 30 days | P0 |
| US-04 | As a creator, I want to see which content types (Reels, Carousel, Image) perform best so I can focus my efforts | P0 |
| US-05 | As a creator, I want to see my top content pillars so I know what themes resonate most | P1 |
| US-06 | As a creator, I want to see an engagement heatmap so I know the best times to post | P1 |
| US-07 | As a creator, I want to see my top hashtags ranked by performance so I can optimize my hashtag strategy | P1 |
| US-08 | As a creator, I want to see audience insights (new vs returning viewers, follower quality, non-follower reach) so I understand my audience composition | P1 |
| US-09 | As a creator, I want to see my top performing posts so I can replicate what works | P1 |
| US-10 | As a creator, I want to see AI-generated recommendations with impact levels so I know what to prioritize | P0 |
| US-11 | As a creator, I want to see an AI summary with key takeaways so I don't have to interpret raw data myself | P0 |
| US-12 | As a creator, I want to see a growth stage indicator so I know where I am in my journey | P2 |

### 3.2 Brand Manager Stories

| ID | Story | Priority |
|---|---|---|
| BM-01 | As a brand manager, I want to see a Brand Readiness Score so I can assess if this creator is marketable | P0 |
| BM-02 | As a brand manager, I want to see estimated rate per post and CPM so I can budget for campaigns | P0 |
| BM-03 | As a brand manager, I want to see brand safety signals so I can assess risk | P0 |
| BM-04 | As a brand manager, I want to see audience demographics (top countries) so I can match geographic targeting | P1 |
| BM-05 | As a brand manager, I want to see a niche benchmark comparison so I can evaluate if this creator outperforms their niche average | P1 |
| BM-06 | As a brand manager, I want to see a conversion funnel (profile visits → website clicks → follows) so I can estimate ROI | P2 |

---

## 4. Functional Requirements

### 4.1 Dashboard Sections

Each section maps to a specific data structure returned by the `GET /api/account-analysis/{account_id}` endpoint.

#### Section 1: Account Header
- **Data:** `account_id`, `username`, `niche`, `post_count`, `follower_count`, `following_count`
- **Source:** Account metadata (not part of `AccountHealthScore`; provided by the API route layer)
- **Display:** Profile picture, @handle, niche label, post/follower/following counts

#### Section 2: Account Health Score
- **Data:** `ahs_score` (0-100), `ahs_band` ("NEEDS_WORK" | "AVERAGE" | "STRONG" | "EXCEPTIONAL")
- **Display:** Circular gauge with score, band label ("Very Good", "Good", etc.), color coding
- **Derived:** Band-to-label mapping: EXCEPTIONAL→"Excellent", STRONG→"Very Good", AVERAGE→"Good", NEEDS_WORK→"Needs Work"

#### Section 3: Growth Stage
- **Data:** Derived from `ahs_band` + `core_metrics.followers.trend_percentage`
- **Display:** Label ("Thriving", "Growing", "Stable", "Developing", "Needs Attention") with trend description
- **Logic:**
  - EXCEPTIONAL → "Thriving"
  - STRONG + positive follower trend → "Growing"
  - STRONG + negative/neutral trend → "Stable"
  - AVERAGE → "Developing"
  - NEEDS_WORK → "Needs Attention"

#### Section 4: Brand Readiness Score
- **Data:** `brand_readiness.score` (0-100), `.label`, `.est_rate_per_post`, `.est_cpm`
- **Display:** Circular gauge, label ("Highly Marketable", "Marketable", "Developing", "Early Stage"), estimated rate range, estimated CPM
- **Note:** `est_rate_per_post` may be displayed as a ±20% range in the UI

#### Section 5: Core Metrics Row
- **Data:** `core_metrics.followers`, `.reach_30d`, `.impressions_30d`, `.engagement_rate`, `.profile_visits_30d`, `.visit_to_follow_rate`
- **Each metric:** `current_value`, `trend_percentage` (delta vs previous period), `label`
- **Display:** 6 metric cards with value, trend arrow, and percentage change

#### Section 6: Growth Overview Chart (30 Days)
- **Data:** `growth_overview_chart` (`list[ChartSeries]`)
- **Each point:** `date`, `followers`, `reach`, `impressions`
- **Display:** Multi-line chart with date on X-axis, values on Y-axis, 3 series (Followers, Reach, Impressions)
- **Note:** Followers line may be flat if historical daily data is unavailable

#### Section 7: Engagement Rate by Content Type
- **Data:** `content_type_performance.breakdown` (`list[ContentTypeBreakdownEntry]`)
- **Each entry:** `content_type`, `avg_engagement_rate`, `post_count`
- **Display:** Bar chart with content type on X-axis, engagement rate on Y-axis

#### Section 8: Content Pillars (by Engagement)
- **Data:** `content_pillars` (`list[ContentPillar]`)
- **Each pillar:** `name`, `engagement_percentage`
- **Display:** Ranked list with horizontal bar showing engagement share
- **Sorted by:** `engagement_percentage` descending

#### Section 9: Engagement Heatmap
- **Data:** `engagement_heatmap` (`list[HeatmapData]`)
- **Each cell:** `day_of_week` (0-6), `hour_of_day` (0-23), `intensity` (0.0-1.0)
- **Display:** 7×24 grid, color intensity from low (dark) to high (bright)
- **Tabs:** "Engagement" (default) and "Posting Activity" (post count per slot)

#### Section 10: Best Times to Post
- **Data:** Derived from `engagement_heatmap` — top 3-4 day/hour slots by intensity
- **Display:** List of day + time range (e.g., "Mon 7PM–10PM")
- **Backend field:** `ai_summary.best_posting_time`

#### Section 11: Top Performing Posts
- **Data:** `top_posts` (`list[TopPostSummary]`)
- **Each post:** `media_id`, `caption_preview`, `media_type`, `published_at`, `engagement_rate`, `reach`
- **Display:** Top 3-5 posts with thumbnail, caption snippet, content type badge, date, engagement rate
- **Sorted by:** `engagement_rate` descending

#### Section 12: Top 10 Hashtags Performance
- **Data:** `top_hashtags` (`list[HashtagPerformance]`)
- **Each hashtag:** `hashtag`, `post_count`, `reach`, `engagement_rate`, `impact` ("Keep" | "Test" | "Drop")
- **Display:** Table with columns: #, Hashtag, Posts, Reach, Engagement Rate, Impact (color-coded badge)

#### Section 13: Audience Insights
- **Data:** `audience_insights` (`AudienceInsights`)
- **Fields:** `new_viewers_pct`, `returning_viewers_pct`, `follower_quality_score`, `non_follower_reach_pct`, `comment_sentiment_positive_pct`, `comment_sentiment_neutral_pct`, `comment_sentiment_negative_pct`
- **Display:** 4 sub-cards:
  1. New vs Returning Viewers (donut chart)
  2. Follower Quality Score (gauge 0-100)
  3. Non-Follower Reach (percentage + label)
  4. Comment Sentiment (donut chart: positive/neutral/negative)
- **Handling:** If `audience_insights` is `None`, show "Data unavailable" state. If `is_estimated` is `True`, show "Estimated" badge.

#### Section 14: You vs Niche Benchmark
- **Data:** `niche_benchmark` (`NicheBenchmark`)
- **Fields:** `engagement_rate_vs_niche`, `reach_vs_niche`, `growth_vs_niche`
- **Display:** Horizontal bar comparison (You vs Niche Avg) for each metric
- **Handling:** If all fields are `None`, hide the section

#### Section 15: Audience Top Countries
- **Data:** `audience_demographics` (`list[AudienceDemographics]`)
- **Each country:** `country`, `percentage`
- **Display:** Ranked list with country flag, name, percentage bar
- **Handling:** If empty list, show "Data unavailable"

#### Section 16: Profile Conversion Funnel
- **Data:** `conversion_funnel` (`ConversionFunnel`)
- **Fields:** `profile_visits`, `website_clicks`, `follows`, `profile_visit_to_follow_pct`
- **Display:** Funnel visualization (Profile Visits → Website Clicks → Follows) with counts and conversion percentages
- **Note:** `follows` may be synthetic (15% of profile visits) until real API data is available

#### Section 17: AI Recommendations
- **Data:** `recommendations` (`list[DeterministicRecommendation]`)
- **Each recommendation:** `id`, `text`, `impact_level` ("HIGH" | "MEDIUM" | "LOW")
- **Display:** List with icon, recommendation text, impact badge (color-coded: HIGH=red, MEDIUM=yellow, LOW=green)
- **Sorted by:** Impact level (HIGH first), then by generation order

#### Section 18: AI Summary
- **Data:** `ai_summary` (`AISummary`)
- **Fields:** `text_summary`, `top_content_type`, `best_posting_time`, `top_content_pillar`, `growth_potential`
- **Display:**
  - Full-width text summary paragraph
  - 4 summary cards: Top Content Type, Best Posting Time, Top Content Pillar, Growth Potential

---

## 5. Data Requirements

### 5.1 Input Data

The dashboard is powered by the existing `AccountHealthScore` model, which is computed from:

| Input | Source | Required |
|---|---|---|
| `posts: list[SinglePostInsights]` | Instagram Graph API (via background job) | Yes (min 10 for full analysis) |
| `account_avg_engagement_rate: float` | Computed from historical posts | No (fallback to absolute ER bands) |
| `niche_avg_engagement_rate: float` | External niche benchmark data | No (falls back to S4-only niche fit) |
| `follower_band: str` | Account metadata | No (used for context notes only) |
| `follower_count: int` | Instagram Graph API | No (defaults to 0) |

### 5.2 Output Schema

All dashboard data is returned in a single `AccountHealthScore` response object. The schema is defined in `backend/app/domain/account_models.py`. All new fields are optional (`None` default) for backward compatibility.

### 5.3 Data Freshness

| Data | Freshness | Source |
|---|---|---|
| Core metrics | Per-post (aggregated over 30 days) | Instagram Graph API |
| Pillar scores | Per-post analysis | AI pipeline (S1-S6) |
| Content type performance | Per-post | Instagram Graph API |
| Hashtag performance | Per-post caption analysis | Deterministic extraction |
| Audience insights | Stubbed until API integration | Synthetic / `None` |
| Niche benchmark | On-demand | External benchmark data |
| Demographics | Stubbed until API integration | Synthetic / `None` |
| AI summary | Generated from deterministic signals | Derived from other fields |

---

## 6. Non-Functional Requirements

### 6.1 Performance
- Dashboard data must be returned within **2 seconds** for accounts with 30 posts
- Background computation (AI pipeline) may take up to **60 seconds**; dashboard polling must handle this gracefully
- Response payload size should be under **50KB** (compressed)

### 6.2 Backward Compatibility
- All new fields in `AccountHealthScore` are optional (default `None`)
- Existing consumers (background jobs, polling endpoints) must not break
- No new API endpoints required; all data flows through existing `AccountHealthScore` response

### 6.3 Data Integrity
- No fabricated metrics presented as real data — stubs must be labeled or return `None`
- Engagement rates, reach, and impressions must come from actual Instagram API data
- AI-generated text (summary, recommendations) must be clearly labeled as AI-generated

### 6.4 Error Handling
- If any section fails to compute, it returns `None` — the rest of the dashboard renders
- If the entire computation fails, return the existing `AccountHealthScore` with only the original fields populated

---

## 7. Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| Dashboard sections populated | ≥14 of 18 sections show real data | Response payload audit |
| Stub sections labeled | 0 sections showing fake data as real | Code review + QA |
| Response time (p95) | <2s for 30-post accounts | APM monitoring |
| Backward compatibility | 0 breaking changes to existing consumers | Regression test suite |
| User engagement | Users spend ≥30s on dashboard page | Analytics |

---

## 8. Dependencies

| Dependency | Status | Risk |
|---|---|---|
| Instagram Graph API (post insights) | Active | Medium — API rate limits, scope changes |
| AI pipeline (S1-S6 scoring) | Active | Low — deterministic, no external calls |
| Niche benchmark data | Not yet integrated | High — no data source identified |
| Audience demographics API | Not available from Instagram | High — requires alternative data source |
| Comment sentiment analysis | Not yet integrated | Medium — requires NLP pipeline |

---

## 9. Out of Scope (v1)

| Feature | Rationale |
|---|---|
| Real-time audience demographics | Instagram API does not expose this; requires third-party data |
| Real-time comment sentiment | Requires NLP pipeline not yet built |
| Historical follower daily data | Instagram API does not expose daily follower counts |
| Cross-account comparison | Separate feature, not part of single-account dashboard |
| Export to PDF/CSV | Nice-to-have, not v1 |
| Mobile-responsive layout | Desktop-first for v1 |

---

## 10. Open Questions

| # | Question | Owner | Status |
|---|---|---|---|
| 1 | Should stub sections be hidden entirely or shown with "Data unavailable" labels? | Product | Open |
| 2 | Is the 15% synthetic visit-to-follow conversion rate acceptable for v1, or should we show "N/A"? | Product | Open |
| 3 | Should `niche_benchmark` show "N/A" for reach and growth until real niche data is available, or hide those rows? | Product | Open |
| 4 | Do we need an "Estimated" badge on synthetic audience insights, or is returning `None` sufficient? | Product | Open |
| 5 | Should the Growth Stage factor in engagement trend, or only follower trend? | Product | Open |

---

## 11. Appendix: API Response Example

```json
{
  "ahs_score": 86.4,
  "ahs_band": "STRONG",
  "growth_stage": "Growing",
  "pillars": { ... },
  "drivers": [ ... ],
  "recommendations": [
    {
      "id": "improve_visual_hook_and_clarity",
      "text": "Improve opening visual hook and framing to raise S1/S3 on most posts.",
      "impact_level": "HIGH"
    }
  ],
  "brand_readiness": {
    "score": 82.0,
    "label": "Highly Marketable",
    "est_rate_per_post": 1500.0,
    "est_rate_per_post_min": 1200.0,
    "est_rate_per_post_max": 1800.0,
    "est_cpm": 22.5
  },
  "core_metrics": {
    "followers": { "current_value": 45200, "trend_percentage": 8.7, "label": "Followers" },
    "reach_30d": { "current_value": 312000, "trend_percentage": 12.4, "label": "30D Reach" },
    "impressions_30d": { "current_value": 987000, "trend_percentage": 15.3, "label": "30D Impressions" },
    "engagement_rate": { "current_value": 4.8, "trend_percentage": 0.6, "label": "Engagement Rate" },
    "profile_visits_30d": { "current_value": 18700, "trend_percentage": 10.2, "label": "30D Profile Visits" },
    "visit_to_follow_rate": { "current_value": 3.2, "trend_percentage": 0.4, "label": "Visit-to-Follow Rate" }
  },
  "growth_overview_chart": [
    { "date": "2024-05-20", "followers": 42100, "reach": 28000, "impressions": 85000 },
    { "date": "2024-05-27", "followers": 42800, "reach": 31000, "impressions": 92000 }
  ],
  "content_type_performance": {
    "breakdown": [
      { "content_type": "REEL", "post_count": 18, "avg_engagement_rate": 0.056 },
      { "content_type": "CAROUSEL", "post_count": 7, "avg_engagement_rate": 0.042 },
      { "content_type": "IMAGE", "post_count": 5, "avg_engagement_rate": 0.027 }
    ],
    "best_for_views": "REEL",
    "best_for_engagement": "REEL"
  },
  "content_pillars": [
    { "name": "outfit ideas", "engagement_percentage": 28.5 },
    { "name": "styling tips", "engagement_percentage": 22.1 }
  ],
  "engagement_heatmap": [
    { "day_of_week": 0, "hour_of_day": 19, "intensity": 0.92 },
    { "day_of_week": 2, "hour_of_day": 18, "intensity": 0.87 }
  ],
  "top_hashtags": [
    { "hashtag": "fashion", "post_count": 24, "reach": 128000, "engagement_rate": 0.052, "impact": "Keep" }
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
    { "country": "India", "percentage": 62.0 },
    { "country": "United States", "percentage": 12.0 }
  ],
  "conversion_funnel": {
    "profile_visits": 18700,
    "website_clicks": 2450,
    "follows": 1200,
    "profile_visit_to_follow_pct": 6.4
  },
  "top_posts": [
    {
      "media_id": "abc123",
      "caption_preview": "5 Summer Outfit Ideas",
      "media_type": "REEL",
      "published_at": "2024-05-26T14:00:00Z",
      "engagement_rate": 0.068,
      "reach": 45000
    }
  ],
  "ai_summary": {
    "text_summary": "Your account is growing strong with excellent reach and engagement...",
    "top_content_type": "REEL",
    "best_posting_time": "Mon 19:00, Wed 18:00, Fri 12:00",
    "top_content_pillar": "outfit ideas",
    "growth_potential": "High"
  }
}
```
