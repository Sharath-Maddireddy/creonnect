# Advanced Account Analysis API Documentation

**Version:** 1.0.0
**Last Updated:** 2025-07-23
**Base URL:** `http://localhost:8000`

---

## Overview

The Advanced Account Analysis API provides endpoints for revenue optimization, risk assessment, and brand readiness scoring. These endpoints complement the existing Account Analysis system by providing actionable insights for creators and brands.

### Key Features

- **Revenue Optimization Calculator** - Dynamic rate recommendations based on performance metrics
- **Risk Assessment Dashboard** - Proactive monitoring of engagement, brand safety, and growth risks
- **Brand Readiness Scoring** - Detailed component scores with improvement recommendations

---

## Authentication

All endpoints require authentication via session cookie or API key. See the main API documentation for authentication details.

---

## Endpoints

### 1. Revenue Calculator

#### `POST /api/account-analysis/revenue`

Calculate rate recommendation based on performance metrics.

**Request Body:**

```json
{
  "engagement_rate": 0.05,
  "follower_count": 50000,
  "niche": "fashion",
  "brand_safety_score": 90,
  "content_quality_score": 80,
  "save_rate": 0.08,
  "share_rate": 0.02
}
```

**Request Schema:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `engagement_rate` | float | Yes | Average engagement rate (0.0-1.0) |
| `follower_count` | int | Yes | Current follower count |
| `niche` | string | Yes | Primary content niche |
| `brand_safety_score` | float | No | Brand safety score (0-100, default: 80) |
| `content_quality_score` | float | No | Content quality score (0-100, default: 70) |
| `save_rate` | float | No | Average save rate (0.0-1.0, default: 0.05) |
| `share_rate` | float | No | Average share rate (0.0-1.0, default: 0.01) |

**Response:**

```json
{
  "base_rate": 750.0,
  "recommended_rate": 810.75,
  "rate_min": 648.6,
  "rate_max": 972.9,
  "cpm_estimate": 54.05,
  "breakdown": {
    "base_rate": 750.0,
    "engagement_component": 300.0,
    "follower_component": 225.0,
    "niche_component": 135.0,
    "quality_premium": 1.34
  },
  "optimization_tips": [
    "Your save rate is strong - highlight this as proof of content value",
    "Fashion/beauty creators command premium rates - showcase brand partnerships",
    "Negotiate 3-month packages for 15-20% rate premium",
    "Bundle Reels + Stories for higher total deal value"
  ],
  "revenue_projections": {
    "monthly_deals_4": [2594.4, 3891.6],
    "monthly_deals_8": [5188.8, 7783.2],
    "annual_potential": [31132.8, 93422.4]
  }
}
```

**Response Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `base_rate` | float | Base rate calculated from engagement rate |
| `recommended_rate` | float | Final recommended rate per post |
| `rate_min` | float | Minimum recommended rate (recommended - 20%) |
| `rate_max` | float | Maximum recommended rate (recommended + 20%) |
| `cpm_estimate` | float | Estimated cost per 1000 impressions |
| `breakdown` | object | Rate calculation component breakdown |
| `optimization_tips` | array | Actionable tips to increase rates |
| `revenue_projections` | object | Revenue projections by deal volume |

**Example cURL:**

```bash
curl -X POST http://localhost:8000/api/account-analysis/revenue \
  -H "Content-Type: application/json" \
  -d '{
    "engagement_rate": 0.05,
    "follower_count": 50000,
    "niche": "fashion",
    "brand_safety_score": 90,
    "content_quality_score": 80,
    "save_rate": 0.08,
    "share_rate": 0.02
  }'
```

---

### 2. Risk Assessment

#### `POST /api/account-analysis/risks`

Perform comprehensive risk assessment for an account.

**Request Body:**

```json
{
  "posts": [
    {
      "media_id": "post_1",
      "media_type": "REEL",
      "published_at": "2025-07-20T14:00:00Z",
      "caption_text": "Summer outfit ideas",
      "core_metrics": {
        "likes": 1500,
        "comments": 45,
        "saves": 120,
        "shares": 35,
        "reach": 25000
      },
      "derived_metrics": {
        "engagement_rate": 0.068
      },
      "brand_safety_score": {
        "total_0_50": 45
      }
    }
  ]
}
```

**Request Schema:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `posts` | array | Yes | List of post objects to analyze |

**Post Object Schema:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `media_id` | string | Yes | Unique post identifier |
| `media_type` | string | Yes | Content type (REEL, IMAGE, CAROUSEL) |
| `published_at` | string | Yes | ISO 8601 timestamp |
| `caption_text` | string | No | Post caption |
| `core_metrics` | object | Yes | Engagement metrics |
| `derived_metrics` | object | No | Calculated metrics |
| `brand_safety_score` | object | No | Brand safety assessment |

**Response:**

```json
{
  "overall_risk_level": "low",
  "risks": [],
  "risk_count": 0,
  "recommended_actions": []
}
```

**Response Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `overall_risk_level` | string | Overall risk level (low, medium, high, critical) |
| `risks` | array | List of detected risks |
| `risk_count` | int | Total number of risks detected |
| `recommended_actions` | array | List of recommended actions |

**Risk Object Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique risk identifier |
| `category` | string | Risk category |
| `level` | string | Risk severity level |
| `title` | string | Human-readable risk title |
| `description` | string | Detailed risk description |
| `metric_affected` | string | Metric causing the risk |
| `current_value` | float | Current metric value |
| `previous_value` | float | Previous metric value |
| `change_percentage` | float | Percentage change |
| `recommended_actions` | array | Actions to address the risk |

**Risk Categories:**

| Category | Description |
|----------|-------------|
| `brand_safety` | Brand safety concerns |
| `engagement_decline` | Engagement rate declining |
| `growth_slowdown` | Follower growth slowing |
| `content_performance` | Content quality issues |
| `audience_quality` | Audience quality concerns |

**Example cURL:**

```bash
curl -X POST http://localhost:8000/api/account-analysis/risks \
  -H "Content-Type: application/json" \
  -d '{
    "posts": [
      {
        "media_id": "post_1",
        "media_type": "REEL",
        "published_at": "2025-07-20T14:00:00Z",
        "core_metrics": {"likes": 1500, "comments": 45, "reach": 25000},
        "derived_metrics": {"engagement_rate": 0.068},
        "brand_safety_score": {"total_0_50": 45}
      }
    ]
  }'
```

---

### 3. Brand Readiness

#### `POST /api/account-analysis/brand-readiness`

Calculate detailed brand readiness score with component breakdown.

**Request Body:**

```json
{
  "posts": [
    {
      "media_id": "post_1",
      "media_type": "REEL",
      "published_at": "2025-07-20T14:00:00Z",
      "core_metrics": {
        "likes": 1500,
        "comments": 45,
        "saves": 120,
        "shares": 35,
        "reach": 25000
      },
      "derived_metrics": {
        "engagement_rate": 0.068
      },
      "brand_safety_score": {
        "total_0_50": 45
      }
    }
  ],
  "pillar_scores": {
    "content_quality": {"score": 80},
    "brand_safety": {"score": 90}
  }
}
```

**Request Schema:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `posts` | array | Yes | List of post objects to analyze |
| `pillar_scores` | object | No | Optional pillar scores from account health |

**Response:**

```json
{
  "overall_score": 73.8,
  "overall_label": "Marketable",
  "content_quality_score": 50.0,
  "brand_safety_score": 87.0,
  "engagement_score": 90.0,
  "consistency_score": 50.0,
  "niche_clarity_score": 50.0,
  "audience_quality_score": 60.0,
  "percentile_rank": 73.8,
  "improvement_opportunities": [
    "Content Quality",
    "Niche Clarity",
    "Consistency"
  ]
}
```

**Response Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `overall_score` | float | Overall brand readiness score (0-100) |
| `overall_label` | string | Human-readable label |
| `content_quality_score` | float | Content quality component score |
| `brand_safety_score` | float | Brand safety component score |
| `engagement_score` | float | Engagement rate component score |
| `consistency_score` | float | Posting consistency score |
| `niche_clarity_score` | float | Niche focus clarity score |
| `audience_quality_score` | float | Audience quality score |
| `percentile_rank` | float | Percentile rank in segment |
| `improvement_opportunities` | array | Top areas for improvement |

**Score Labels:**

| Score Range | Label |
|-------------|-------|
| 85-100 | Highly Marketable |
| 70-84 | Marketable |
| 55-69 | Developing |
| 40-54 | Early Stage |
| 0-39 | Needs Work |

**Example cURL:**

```bash
curl -X POST http://localhost:8000/api/account-analysis/brand-readiness \
  -H "Content-Type: application/json" \
  -d '{
    "posts": [
      {
        "media_id": "post_1",
        "media_type": "REEL",
        "published_at": "2025-07-20T14:00:00Z",
        "core_metrics": {"likes": 1500, "comments": 45, "reach": 25000},
        "derived_metrics": {"engagement_rate": 0.068},
        "brand_safety_score": {"total_0_50": 45}
      }
    ]
  }'
```

---

## Error Responses

All endpoints return standard HTTP error codes:

| Status Code | Description |
|-------------|-------------|
| 400 | Bad Request - Invalid input parameters |
| 401 | Unauthorized - Authentication required |
| 404 | Not Found - Resource does not exist |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error - Server-side error |

**Error Response Format:**

```json
{
  "detail": "Error message describing the issue"
}
```

---

## Rate Limits

| Endpoint | Rate Limit | Window |
|----------|------------|--------|
| `/revenue` | 100 requests | 1 minute |
| `/risks` | 50 requests | 1 minute |
| `/brand-readiness` | 50 requests | 1 minute |

---

## Data Models

### Niche Multipliers

The revenue calculator uses niche-specific multipliers based on market data:

| Niche | Multiplier |
|-------|------------|
| Fashion | 1.20 |
| Beauty | 1.15 |
| Tech | 1.10 |
| Finance | 1.12 |
| Travel | 1.08 |
| Fitness | 1.05 |
| Lifestyle | 1.00 |
| Food | 0.95 |
| Education | 0.90 |
| Comedy | 0.92 |
| Gaming | 0.88 |
| Music | 0.85 |

### Risk Detection Rules

| Risk | Threshold | Level |
|------|-----------|-------|
| Engagement Decline | >15% drop in 30 days | MEDIUM |
| Engagement Decline | >25% drop in 30 days | HIGH |
| Low Save Rate | <3% average | MEDIUM |
| Flagged Content | 1-2 posts | MEDIUM |
| Flagged Content | 3+ posts | HIGH |
| Low Posting Frequency | <3 posts/week | MEDIUM |
| Inconsistent Performance | CV > 0.5 | MEDIUM |

---

## Integration Examples

### JavaScript/Fetch

```javascript
// Revenue Calculator
const revenueResponse = await fetch('/api/account-analysis/revenue', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    engagement_rate: 0.05,
    follower_count: 50000,
    niche: 'fashion',
    brand_safety_score: 90,
    content_quality_score: 80,
    save_rate: 0.08,
    share_rate: 0.02
  })
});
const revenueData = await revenueResponse.json();
console.log(`Recommended rate: $${revenueData.recommended_rate}`);

// Risk Assessment
const risksResponse = await fetch('/api/account-analysis/risks', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ posts: postsArray })
});
const risksData = await risksResponse.json();
console.log(`Risk level: ${risksData.overall_risk_level}`);

// Brand Readiness
const brandResponse = await fetch('/api/account-analysis/brand-readiness', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ posts: postsArray })
});
const brandData = await brandResponse.json();
console.log(`Brand score: ${brandData.overall_score}/100`);
```

### Python/Requests

```python
import requests

# Revenue Calculator
revenue_response = requests.post(
    'http://localhost:8000/api/account-analysis/revenue',
    json={
        'engagement_rate': 0.05,
        'follower_count': 50000,
        'niche': 'fashion',
        'brand_safety_score': 90,
        'content_quality_score': 80,
        'save_rate': 0.08,
        'share_rate': 0.02
    }
)
revenue_data = revenue_response.json()
print(f"Recommended rate: ${revenue_data['recommended_rate']}")

# Risk Assessment
risks_response = requests.post(
    'http://localhost:8000/api/account-analysis/risks',
    json={'posts': posts_list}
)
risks_data = risks_response.json()
print(f"Risk level: {risks_data['overall_risk_level']}")

# Brand Readiness
brand_response = requests.post(
    'http://localhost:8000/api/account-analysis/brand-readiness',
    json={'posts': posts_list}
)
brand_data = brand_response.json()
print(f"Brand score: {brand_data['overall_score']}/100")
```

---

## Changelog

### v1.0.0 (2025-07-23)

- Initial release
- Revenue Calculator endpoint
- Risk Assessment endpoint
- Brand Readiness endpoint

---

## Support

For issues or questions, contact the engineering team or open an issue in the repository.
