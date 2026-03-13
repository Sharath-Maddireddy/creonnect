# API Endpoints

## Summary
- Total endpoints discovered: **11**
- Product/API endpoints (frontend-relevant): **7**
- Internal documentation endpoints: **4**

| Feature Area | Count | Endpoints |
|---|---:|---|
| System | 1 | `GET /health` |
| Dashboard | 3 | `GET /api/creator/dashboard`, `GET /api/creators/{creator_id}/snapshot`, `POST /api/creators/{creator_id}/generate-script` |
| Account Analysis | 2 | `POST /api/account-analysis`, `GET /api/account-analysis/{job_id}` |
| Post Analysis | 1 | `POST /api/post-analysis` |
| Internal Docs | 4 | `GET /openapi.json`, `GET /docs`, `GET /docs/oauth2-redirect`, `GET /redoc` |

## Base URL and Versioning
- App has **no global versioned prefix** in code.
- Main API router prefix is **`/api`**.
- Root-level routes also exist: `/health`, `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`.
- Coverage cross-check: route table validated via FastAPI app introspection (`backend/main.py` router registrations + runtime route listing).

## Authentication
- Protected scope: all product endpoints under `/api/*`.
- Required auth header for protected endpoints: `Authorization: Bearer <access_token>`.
- Missing/invalid/expired token: `401 Unauthorized`.
- Valid token without permission for the target resource: `403 Forbidden`.
- Public auth-exempt endpoints:
  - `GET /health`
  - `GET /openapi.json`
  - `GET /docs`
  - `GET /docs/oauth2-redirect`
  - `GET /redoc`

---

## 1) GET `/health`
- Purpose: Liveness/health probe.
- Visibility: Public.
- Auth: `none`
- Required headers: none

### Query Params
- None.

### Request Body
- None.

### Response Schema
```json
{
  "status": "string"
}
```

### Example Response
```json
{
  "status": "ok"
}
```

### Possible Errors
- `500`: Unexpected runtime failure.

### Pagination / Sorting / Filtering
- None.

---

## 2) GET `/api/creator/dashboard`
- Purpose: Returns complete dashboard payload for charts/summary/action plan.
- Visibility: Authenticated clients.
- Auth: `Authorization: Bearer <access_token>` required
- Required headers: `Authorization: Bearer <access_token>`

### Query Params
- None.

### Request Body
- None.

### Response Schema
```json
{
  "summary": {
    "username": "string",
    "followers": "integer",
    "growth_score": "number",
    "avg_engagement_rate_by_views": "number|null",
    "avg_views": "number|null",
    "views_to_followers_ratio": "number|null",
    "posts_per_week": "number",
    "niche": {
      "primary_niche": "string|null",
      "secondary_niche": "string|null",
      "confidence": "number"
    },
    "momentum": {
      "momentum_value": "number",
      "momentum_label": "accelerating|declining|flat"
    },
    "best_time_to_post": {
      "best_posting_hours": ["integer"],
      "hourly_engagement": {
        "<hour>": "number"
      }
    }
  },
  "posts": [
    {
      "post_id": "string",
      "total_interactions": "integer",
      "engagement_rate_by_views": "number|null",
      "like_rate": "number|null",
      "comment_rate": "number|null",
      "relative_performance": "number|null",
      "caption_context_present": "boolean",
      "cta_present": "boolean",
      "insights": ["string"],
      "comparison_to_previous": {
        "_type": "object|null",
        "delta_views": "integer",
        "delta_likes": "integer",
        "delta_comments": "integer",
        "engagement_change_pct": "number|null",
        "relative_performance_label": "better|worse|same",
        "explanation": "string"
      },
      "error": "string|null"
    }
  ],
  "charts": {
    "engagement_over_time": [{ "date": "string|null", "value": "number|null" }],
    "views_over_time": [{ "date": "string|null", "value": "number|null" }]
  },
  "action_plan": {
    "diagnosis": "string",
    "weekly_plan": ["string"],
    "content_suggestions": ["string"],
    "posting_schedule": ["string"],
    "cta_tips": ["string"]
  }
}
```
Notes:
- `posts[].comparison_to_previous` appears from 2nd post onward.
- `posts[].error` appears only when per-post analysis fails.

### Example Response
```json
{
  "summary": {
    "username": "demo",
    "followers": 125000,
    "growth_score": 72,
    "avg_engagement_rate_by_views": 0.0542,
    "avg_views": 93000,
    "views_to_followers_ratio": 0.74,
    "posts_per_week": 4.0,
    "niche": {
      "primary_niche": "fitness",
      "secondary_niche": "lifestyle",
      "confidence": 0.64
    },
    "momentum": {
      "momentum_value": 80.0,
      "momentum_label": "accelerating"
    },
    "best_time_to_post": {
      "best_posting_hours": [18, 20],
      "hourly_engagement": {
        "18": 0.0712,
        "20": 0.0698
      }
    }
  },
  "posts": [
    {
      "post_id": "m_1",
      "total_interactions": 115,
      "engagement_rate_by_views": 0.051,
      "like_rate": 4.8,
      "comment_rate": 0.3,
      "relative_performance": 1.08,
      "caption_context_present": true,
      "cta_present": true,
      "insights": ["Good engagement rate by views (5.10%). Above average for Instagram content."]
    }
  ],
  "charts": {
    "engagement_over_time": [{ "date": "2024-01-01T00:00:00+00:00", "value": 0.051 }],
    "views_over_time": [{ "date": "2024-01-01T00:00:00+00:00", "value": 2200 }]
  },
  "action_plan": {
    "diagnosis": "Your account is growing at 80 followers/day. Engagement is healthy. Overall growth score is strong.",
    "weekly_plan": ["Keep up your 4.0 posts/week cadence"],
    "content_suggestions": ["Workout transformation reel", "Quick exercise tutorial"],
    "posting_schedule": ["Post between 6 PM - your audience is most active"],
    "cta_tips": ["End captions with a question to encourage comments"]
  }
}
```

### Possible Errors
- `401`: Missing, malformed, expired, or invalid bearer token.
- `403`: Authenticated caller is not allowed to access this resource.
- `404`: Creator not found (raised as `ValueError`, mapped in handler).
- `500`: Unhandled internal errors (model load, AI dependency, data failures).

### Pagination / Sorting / Filtering
- None.

---

## 3) GET `/api/creators/{creator_id}/snapshot`
- Purpose: Returns a daily creator snapshot.
- Visibility: Authenticated clients.
- Auth: `Authorization: Bearer <access_token>` required
- Required headers: `Authorization: Bearer <access_token>`

### Path Params
| Name | Type | Required |
|---|---|---|
| `creator_id` | `string` | yes |

### Query Params
- None.

### Request Body
- None.

### Response Schema
```json
{
  "creator_id": "string",
  "date": "YYYY-MM-DD",
  "followers": "integer",
  "avg_views": "number",
  "avg_likes": "number",
  "avg_comments": "number",
  "total_interactions": "number",
  "engagement_rate_by_views": "number",
  "growth_score": "number"
}
```

### Example Response
```json
{
  "creator_id": "demo",
  "date": "2026-03-01",
  "followers": 125000,
  "avg_views": 93000,
  "avg_likes": 4200,
  "avg_comments": 310,
  "total_interactions": 4510,
  "engagement_rate_by_views": 0.0485,
  "growth_score": 72
}
```

### Possible Errors
- `401`: Missing, malformed, expired, or invalid bearer token.
- `403`: Authenticated caller is not allowed to access this resource.
- `404`: Unknown creator id.
- `422`: Path parameter validation error.
- `500`: Unhandled internal errors.

### Pagination / Sorting / Filtering
- None.

---

## 4) POST `/api/creators/{creator_id}/generate-script`
- Purpose: Generates a reel script for a creator profile.
- Visibility: Authenticated clients.
- Auth: `Authorization: Bearer <access_token>` required
- Required headers: `Authorization: Bearer <access_token>`

### Path Params
| Name | Type | Required |
|---|---|---|
| `creator_id` | `string` | yes |

### Query Params
- None.

### Request Body
- None.

### Response Schema
```json
{
  "hook": "string",
  "body": "string",
  "cta": "string",
  "niche": "string",
  "tone": "string"
}
```

### Example Response
```json
{
  "hook": "Stop scrolling if you want to build strength",
  "body": "Focus on form over speed. Start with 12 reps and build up gradually.",
  "cta": "Save this for your next workout!",
  "niche": "fitness",
  "tone": "fitness creator style"
}
```

### Possible Errors
- `401`: Missing, malformed, expired, or invalid bearer token.
- `403`: Authenticated caller is not allowed to access this resource.
- `404`: Unknown creator id.
- `422`: Path parameter validation error.
- `500`: Unhandled internal errors.

### Pagination / Sorting / Filtering
- None.

---

## 5) POST `/api/account-analysis`
- Purpose: Enqueue account-level analysis job; dedupes/rate-limits by account.
- Visibility: Authenticated clients.
- Auth: `Authorization: Bearer <access_token>` required
- Required headers: `Authorization: Bearer <access_token>`, `Content-Type: application/json`

### Query Params
- None.

### Request Body Schema (`AccountAnalysisRequest`)
| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `account_id` | `string` | yes | - | Non-empty expected by job service. |
| `post_limit` | `integer` | no | `30` | Range `1..30`. |
| `account_avg_engagement_rate` | `number|null` | no | `null` | Optional benchmark input. |
| `niche_avg_engagement_rate` | `number|null` | no | `null` | Optional niche benchmark input. |
| `follower_band` | `string|null` | no | `null` | Optional context label. |
| `posts` | `array<object>|null` | no | `null` | If provided, each item should be `SinglePostInsights`-compatible payload. |
| `include_posts_summary` | `boolean` | no | `false` | Adds bounded `result.posts_summary` in status payload. |
| `include_posts_summary_max` | `integer` | no | `30` | Range `1..30`. |

Unknown JSON keys are rejected with HTTP `422` validation error.

### Example Request
```json
{
  "account_id": "acct_queue",
  "post_limit": 10,
  "account_avg_engagement_rate": 0.06,
  "niche_avg_engagement_rate": 0.055,
  "follower_band": "10k-50k",
  "include_posts_summary": true,
  "include_posts_summary_max": 5,
  "posts": [
    {
      "account_id": "acct_queue",
      "media_id": "m_1",
      "media_type": "IMAGE",
      "caption_text": "How to improve content quality? Save this guide.",
      "published_at": "2024-01-01T00:00:00+00:00",
      "core_metrics": {"reach": 2000, "impressions": 2200, "likes": 120, "comments": 20, "saves": 25, "shares": 15},
      "derived_metrics": {"engagement_rate": 0.08, "save_rate": 0.02, "share_rate": 0.01},
      "benchmark_metrics": {"account_avg_engagement_rate": 0.06}
    }
  ]
}
```

### Response Schema
```json
{
  "job_id": "string",
  "status": "queued|started|succeeded"
}
```
Notes:
- Full lifecycle statuses for account-analysis jobs are `queued|started|succeeded|failed`.
- This enqueue (`POST`) response returns only `queued|started|succeeded` (new job or reusable active/succeeded job). `failed` is surfaced when polling `GET /api/account-analysis/{job_id}`.

### Example Response
```json
{
  "job_id": "3fce6c96-6f57-4df6-8e29-a1ea805181a6",
  "status": "queued"
}
```

### Possible Errors
- `401`: Missing, malformed, expired, or invalid bearer token.
- `403`: Authenticated caller is not allowed to enqueue for this resource.
- `422`: Body validation error (type mismatch, missing required field, unknown extra keys, range violation).
- `429`: Rate limit exceeded (`ACCOUNT_ANALYSIS_RATE_LIMIT_PER_HOUR`, default 3/hour/account).
- `500`: Enqueue failure or unexpected exception.

### Pagination / Sorting / Filtering
- No pagination/sorting/filtering.
- Result shaping flag: `include_posts_summary_max` only bounds embedded summary count (max 30), it is **not** cursor/page pagination.

---

## 6) GET `/api/account-analysis/{job_id}`
- Purpose: Poll account-analysis job status/result.
- Visibility: Authenticated clients.
- Auth: `Authorization: Bearer <access_token>` required
- Required headers: `Authorization: Bearer <access_token>`

### Path Params
| Name | Type | Required |
|---|---|---|
| `job_id` | `string` | yes |

### Query Params
- None.

### Request Body
- None.

### Response Schema
```json
{
  "job_id": "string",
  "status": "queued|started|succeeded|failed",
  "created_at": "datetime",
  "started_at": "datetime|null",
  "finished_at": "datetime|null",
  "progress": {
    "stage": "string",
    "done": "integer",
    "total": "integer"
  },
  "error": {
    "type": "string",
    "message": "string"
  },
  "warnings": [
    {
      "component": "string",
      "code": "string",
      "message": "string",
      "post_id": "string"
    }
  ],
  "quality": {
    "vision_enabled": "boolean",
    "vision_error_count": "integer",
    "ai_fallback_count": "integer"
  },
  "result": {
    "ahs_score": "number",
    "ahs_band": "NEEDS_WORK|AVERAGE|STRONG|EXCEPTIONAL",
    "pillars": {
      "content_quality": {"score": "number", "band": "...", "notes": ["string"]},
      "engagement_quality": {"score": "number", "band": "...", "notes": ["string"]},
      "niche_fit": {"score": "number", "band": "...", "notes": ["string"]},
      "consistency": {"score": "number", "band": "...", "notes": ["string"]},
      "brand_safety": {"score": "number", "band": "...", "notes": ["string"]}
    },
    "drivers": [{"id": "string", "label": "string", "type": "POSITIVE|LIMITING", "explanation": "string"}],
    "recommendations": [{"id": "string", "text": "string", "impact_level": "HIGH|MEDIUM|LOW"}],
    "metadata": {
      "post_count_used": "integer",
      "min_history_threshold_met": "boolean",
      "time_window_days": "integer|null"
    },
    "posts_summary": [
      {
        "post_id": "string|null",
        "shortcode": "string|null",
        "post_type": "IMAGE|REEL|null",
        "media_url": "string|null",
        "caption_preview": "string(<=120)",
        "scores": {
          "S1": "number|null", "S2": "number|null", "S3": "number|null",
          "S4": "number|null", "S5": "number|null", "S6": "number|null",
          "P": "number|null", "predicted_er": "number|null"
        },
        "notes": {
          "vision_status": "ok|error|disabled",
          "fallback_used": "boolean"
        }
      }
    ]
  }
}
```
Notes:
- `result` is `null` for queued/started/failed states.
- Stale job thresholds are enforced on poll (`GET /api/account-analysis/{job_id}`):
  - Queued stale threshold: `>900s` (`15` minutes) since `created_at`.
  - Started stale threshold: `>1800s` (`30` minutes) since `started_at` (or `created_at` when `started_at` is missing).
- If stale is detected during poll, the API returns a projected `failed` view (`error.type=TimeoutError`, `result=null`) without persisting that transition.
- `posts_summary` exists only when enqueue flag `include_posts_summary=true` was used.

### Example Response
```json
{
  "job_id": "job_success",
  "status": "succeeded",
  "created_at": "2026-03-01T00:00:00+00:00",
  "started_at": "2026-03-01T00:00:01+00:00",
  "finished_at": "2026-03-01T00:00:02+00:00",
  "progress": {"stage": "aggregate", "done": 10, "total": 10},
  "error": null,
  "warnings": [],
  "quality": {"vision_enabled": true, "vision_error_count": 0, "ai_fallback_count": 0},
  "result": {
    "ahs_score": 70.0,
    "ahs_band": "STRONG",
    "pillars": {
      "content_quality": {"score": 68.0, "band": "STRONG", "notes": []},
      "engagement_quality": {"score": 74.0, "band": "STRONG", "notes": []},
      "niche_fit": {"score": 65.0, "band": "STRONG", "notes": []},
      "consistency": {"score": 72.0, "band": "STRONG", "notes": []},
      "brand_safety": {"score": 80.0, "band": "EXCEPTIONAL", "notes": []}
    },
    "drivers": [],
    "recommendations": [],
    "metadata": {"post_count_used": 10, "min_history_threshold_met": true, "time_window_days": 30}
  }
}
```

### Possible Errors
- `401`: Missing, malformed, expired, or invalid bearer token.
- `403`: Authenticated caller is not allowed to read this job.
- `404`: Unknown `job_id`.
- `422`: Path parameter validation error.
- `500`: Unexpected read/processing failure.

### Pagination / Sorting / Filtering
- No pagination/sorting/filtering.
- `posts_summary` (if present) is internally sorted and hard-capped (`<=30`).

---

## 7) POST `/api/post-analysis`
- Purpose: Runs single-post analysis and returns normalized deterministic payload.
- Visibility: Authenticated clients.
- Auth: `Authorization: Bearer <access_token>` required
- Required headers: `Authorization: Bearer <access_token>`, `Content-Type: application/json`

### Query Params
- None.

### Request Body Schema (`PostAnalysisRequest`)
| Field | Type | Required | Default | Notes |
|---|---|---:|---|---|
| `post_id` | `string|null` | no | `null` | Auto-generated if missing. |
| `account_id` | `string|null` | no | `null` | Used to populate `creator_id`. |
| `creator_id` | `string|null` | no | `null` | Fallback if `account_id` missing. |
| `platform` | `string` | no | `"instagram"` | |
| `post_type` | `"IMAGE"|"REEL"` | no | `"IMAGE"` | |
| `media_url` | `string` | yes | - | Must be non-empty (custom validator). |
| `thumbnail_url` | `string` | no | `""` | |
| `caption_text` | `string` | no | `""` | |
| `hashtags` | `array<string>` | no | `[]` | |
| `likes` | `integer` | no | `0` | |
| `comments` | `integer` | no | `0` | |
| `views` | `integer|null` | no | `null` | |
| `audio_name` | `string|null` | no | `null` | |
| `posted_at` | `datetime|null` | no | `null` | ISO datetime expected. |

Unknown JSON keys are rejected with HTTP `422` validation error.

### Example Request
```json
{
  "post_id": "post_123",
  "account_id": "creator_1",
  "platform": "instagram",
  "post_type": "IMAGE",
  "media_url": "https://example.com/post.jpg",
  "thumbnail_url": "https://example.com/post-thumb.jpg",
  "caption_text": "Deterministic caption",
  "hashtags": ["creator", "growth"],
  "likes": 100,
  "comments": 10,
  "views": 1000,
  "audio_name": "Original Audio",
  "posted_at": "2024-01-01T00:00:00+00:00"
}
```

### Response Schema
```json
{
  "status": "succeeded",
  "post": {
    "post_id": "string",
    "post_type": "string",
    "media_url": "string",
    "caption_text": "string"
  },
  "vision": {
    "provider": "string",
    "status": "ok|error|disabled|no_media",
    "signals": []
  },
  "scores": {
    "S1": "number|null",
    "S2": "number|null",
    "S3": "number|null",
    "S4": "number|null",
    "S5": "number|null",
    "S6": "number|null",
    "P": "number|null",
    "predicted_engagement_rate": "number|null",
    "predicted_engagement_rate_notes": ["string"]
  },
  "ai": {
    "summary": "string",
    "drivers": [
      {
        "id": "string",
        "label": "string",
        "type": "POSITIVE|LIMITING",
        "explanation": "string"
      }
    ],
    "recommendations": [
      {
        "id": "string",
        "text": "string",
        "impact_level": "HIGH|MEDIUM|LOW"
      }
    ],
    "vision_status": "string|null",
    "fallback_used": "boolean"
  },
  "warnings": [
    {
      "component": "string",
      "code": "string",
      "message": "string",
      "post_id": "string|null"
    }
  ],
  "quality": {
    "vision_enabled": "boolean",
    "ai_fallback_used": "boolean"
  }
}
```
Notes:
- Stable minimum contract: when `ai.drivers` has items, each item includes `id`, `label`, `type`, and `explanation`.
- Stable minimum contract: when `ai.recommendations` has items, each item includes `id`, `text`, and `impact_level`.

Minimum contract for `ai.drivers[]` items:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `id` | `string` | yes | Stable machine-readable driver key. |
| `label` | `string` | yes | Short human-readable title. |
| `type` | `"POSITIVE" \| "LIMITING"` | yes | Driver direction. |
| `explanation` | `string` | yes | One-sentence reason for the driver. |

Example `ai.drivers[]` item:
```json
{
  "id": "deterministic_weak_visual_hook",
  "label": "Weak visual hook",
  "type": "LIMITING",
  "explanation": "Vision hook_strength_score is 0.22, below the 0.40 threshold."
}
```

Minimum contract for `ai.recommendations[]` items:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `id` | `string` | yes | Stable machine-readable recommendation key. |
| `text` | `string` | yes | Actionable recommendation text. |
| `impact_level` | `"HIGH" \| "MEDIUM" \| "LOW"` | yes | Relative priority/impact. |

Example `ai.recommendations[]` item:
```json
{
  "id": "recommendation_add_clear_first_line_hook",
  "text": "Open with a clearer first-line hook that names the audience problem in under 8 words.",
  "impact_level": "HIGH"
}
```

### Example Response
```json
{
  "status": "succeeded",
  "post": {
    "post_id": "post_123",
    "post_type": "IMAGE",
    "media_url": "https://example.com/post.jpg",
    "caption_text": "Deterministic caption"
  },
  "vision": {
    "provider": "gemini",
    "status": "ok",
    "signals": []
  },
  "scores": {
    "S1": 40.0,
    "S2": 35.0,
    "S3": 30.0,
    "S4": 25.0,
    "S5": 20.0,
    "S6": 45.0,
    "P": 55.0,
    "predicted_engagement_rate": 0.08,
    "predicted_engagement_rate_notes": ["deterministic-note"]
  },
  "ai": {
    "summary": "",
    "drivers": [],
    "recommendations": [],
    "vision_status": "ok",
    "fallback_used": false
  },
  "warnings": [],
  "quality": {
    "vision_enabled": true,
    "ai_fallback_used": false
  }
}
```

### Possible Errors
- `401`: Missing, malformed, expired, or invalid bearer token.
- `403`: Authenticated caller is not allowed to analyze this post.
- `422`: Body validation error (required `media_url`, enum/type/date validation, extra keys).
- `500`: Pipeline execution failure.

### Pagination / Sorting / Filtering
- None.

---

## 8) GET `/openapi.json` (Internal)
- Purpose: Returns generated OpenAPI spec.
- Visibility: Internal tooling/docs.
- Auth: `none`
- Required headers: none

### Query Params
- None.

### Request Body
- None.

### Response Schema
- OpenAPI JSON object (framework-generated).
- Exact schema keys are framework-defined and may vary with FastAPI/OpenAPI version.

### Example Response
```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Creonnect API",
    "version": "1.0.0"
  },
  "paths": {
    "/api/post-analysis": {}
  }
}
```

### Possible Errors
- `500`: Spec generation/runtime error.

### Pagination / Sorting / Filtering
- None.

---

## 9) GET `/docs` (Internal)
- Purpose: Swagger UI HTML.
- Visibility: Internal tooling/docs.
- Auth: `none`
- Required headers: none

### Query Params
- None.

### Request Body
- None.

### Response Schema
- `text/html` page (framework-generated).

### Example Response
- HTML document for Swagger UI.

### Possible Errors
- `500`: Template/runtime error.

### Pagination / Sorting / Filtering
- None.

---

## 10) GET `/docs/oauth2-redirect` (Internal)
- Purpose: OAuth redirect helper page used by Swagger UI.
- Visibility: Internal tooling/docs.
- Auth: `none`
- Required headers: none

### Query Params
- None.

### Request Body
- None.

### Response Schema
- `text/html` page (framework-generated).

### Example Response
- HTML redirect helper page.

### Possible Errors
- `500`: Template/runtime error.

### Pagination / Sorting / Filtering
- None.

---

## 11) GET `/redoc` (Internal)
- Purpose: ReDoc HTML documentation page.
- Visibility: Internal tooling/docs.
- Auth: `none`
- Required headers: none

### Query Params
- None.

### Request Body
- None.

### Response Schema
- `text/html` page (framework-generated).

### Example Response
- HTML document for ReDoc.

### Possible Errors
- `500`: Template/runtime error.

### Pagination / Sorting / Filtering
- None.

---

## Source Trace Notes (for unclear/loose schemas)
- `POST /api/post-analysis` documents a stable minimum contract for `ai.drivers[]` and `ai.recommendations[]` based on the AI service output schema (`backend/app/services/ai_analysis_service.py`).
- FastAPI docs/OpenAPI route response payloads are framework-generated and not explicitly modeled in this repository (`backend/main.py` app initialization; routes confirmed by runtime route introspection).

