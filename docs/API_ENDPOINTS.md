# API Endpoints Reference

This document provides a complete reference for all Creonnect backend API endpoints, grouped by feature area.

## Base URL

- **Development:** `http://localhost:8000`
- **Production:** Configured via deployment

All endpoints are under `/api` or `/api/v1` prefixes.

---

## Authentication & OAuth

### 1. Instagram Login (Initiate OAuth)

**Endpoint:** `GET /api/auth/instagram/login`

**Description:** Returns Instagram OAuth authorization URL for user to initiate login flow.

**Parameters:** None

**Response:**
```json
{
  "oauth_url": "https://www.facebook.com/dialog/oauth?client_id=...&state=..."
}
```

**Status Codes:**
- `200` — Success
- `400` — OAuth configuration error (missing env vars)

---

### 2. Instagram OAuth Callback

**Endpoint:** `GET /api/auth/instagram/callback`

**Description:** Callback endpoint called by Instagram OAuth after user authorization. Exchanges code for access token.

**Query Parameters:**
- `code` (string, required) — Authorization code from Instagram.
- `state` (string, required) — State parameter for CSRF protection.

**Response:**
```json
{
  "user_id": "12345",
  "username": "johndoe",
  "status": "connected"
}
```

**Status Codes:**
- `200` — Success, user authenticated
- `400` — Invalid state or API error
- `401` — Authentication failed

**Side Effects:**
- Saves long-lived access token to token store.
- Sets session cookies (`instagram_user_id`, `instagram_username`).

---

### 3. Get Current User Profile

**Endpoint:** `GET /api/auth/me`

**Description:** Returns the authenticated user's Instagram profile data.

**Headers:**
- Requires valid session (set by login flow)

**Response:**
```json
{
  "id": "12345",
  "username": "johndoe",
  "biography": "...",
  "followers_count": 5000,
  "follows_count": 250,
  "media_count": 120
}
```

**Status Codes:**
- `200` — Success
- `401` — Not authenticated or token invalid

---

### 4. Logout

**Endpoint:** `POST /api/auth/logout`

**Description:** Logs out the user, deletes stored token, and clears session.

**Response:**
```json
{
  "status": "logged_out"
}
```

**Status Codes:**
- `200` — Success
- `401` — Not authenticated

---

## Creator Dashboard

### 5. Get Creator Dashboard

**Endpoint:** `GET /api/creator/dashboard`

**Description:** Returns complete creator dashboard with profile, posts, metrics, and action plan.

**Query Parameters:**
- `user_id` (string, optional) — Instagram user ID. When provided, fetches real data; when omitted, uses demo data.

**Response:**
```json
{
  "summary": {
    "username": "fitnesscreator",
    "followers": 12500,
    "growth_score": 72,
    "avg_engagement_rate_by_views": 0.075,
    "avg_views": 5200,
    "posts_per_week": 3.2,
    "niche": {
      "primary_niche": "fitness",
      "secondary_niche": "lifestyle",
      "confidence": 0.85
    },
    "momentum": {
      "momentum_label": "accelerating",
      "momentum_value": 45.5,
      "followers_change_7d": 320
    },
    "best_time_to_post": {
      "best_posting_hours": [18, 19, 20],
      "recommendation": "6–8 PM"
    }
  },
  "posts": [
    {
      "post_id": "12345",
      "post_type": "REEL",
      "media_url": "https://...",
      "thumbnail_url": "https://...",
      "caption_text": "...",
      "hashtags": ["#fitness", "#gym"],
      "likes": 450,
      "comments": 50,
      "views": 5500,
      "engagement_rate_by_views": 0.091,
      "like_rate": 8.18,
      "comment_rate": 0.91,
      "relative_performance": 1.21,
      "insights": [
        "Excellent engagement rate...",
        "This post performed 1.2x your average..."
      ]
    }
  ],
  "charts": {
    "engagement_over_time": [
      { "date": "2026-04-20", "value": 0.065 },
      { "date": "2026-04-21", "value": 0.078 }
    ],
    "views_over_time": [
      { "date": "2026-04-20", "value": 4500 },
      { "date": "2026-04-21", "value": 6200 }
    ]
  },
  "authenticity_analysis": {
    "available": true,
    "score": 82,
    "band": "high",
    "follower_count": 12500,
    "avg_views": 5200,
    "avg_likes": 375,
    "avg_comments": 42
  },
  "action_plan": {
    "diagnosis": "Your account is growing at 45 followers/day. Engagement is healthy.",
    "weekly_plan": [
      "Maintain 3–4 posts/week cadence",
      "Add CTAs to every post",
      "Engage with 10+ accounts daily"
    ],
    "content_suggestions": [
      "Workout transformation reel",
      "Quick exercise tutorial"
    ],
    "posting_schedule": [
      "Post between 6–8 PM",
      "Tuesday and Thursday peak engagement",
      "Space posts 6+ hours apart"
    ],
    "cta_tips": [
      "End captions with a question",
      "Use 'Save this for later'"
    ]
  }
}
```

**Status Codes:**
- `200` — Success
- `401` — Not authenticated (when user_id provided)
- `404` — Creator not found

**Notes:**
- When `user_id` is provided with valid session, fetches real Instagram data.
- When `user_id` is omitted or is "demo", uses synthetic demo data.
- Authenticity analysis is unavailable for demo data.

---

### 6. Get Creator Analytics

**Endpoint:** `GET /api/creator/analytics`

**Description:** Extended analytics dashboard including account health, engagement signals, vision summary, and creator intelligence.

**Query Parameters:**
- `user_id` (string, optional) — Instagram user ID.

**Response:**
```json
{
  "...all dashboard fields...",
  "account_health": {
    "ahs_score": 68,
    "ahs_band": "good",
    "pillars": {
      "engagement_health": {
        "score": 70,
        "band": "good",
        "notes": ["Consistent engagement patterns", "No sudden drops"]
      },
      "content_quality": {
        "score": 65,
        "band": "fair",
        "notes": ["Good variety in content types", "Room for improvement in captions"]
      },
      "growth_consistency": {
        "score": 68,
        "band": "good",
        "notes": ["Regular posting schedule"]
      },
      "audience_alignment": {
        "score": 72,
        "band": "good",
        "notes": ["Strong niche alignment", "Audience expectations met"]
      }
    },
    "drivers": [
      {
        "name": "Posting frequency lower than optimal",
        "impact": "negative"
      }
    ],
    "recommendations": [
      "Increase to 4+ posts per week",
      "Add more CTAs to captions"
    ]
  },
  "engagement_signals": {
    "comment_to_like_ratio": 0.11,
    "save_engagement": 0.02,
    "share_rate": 0.01,
    "audience_response_time_hours": 2.5,
    "topic_consistency_score": 0.85
  },
  "vision_summary": {
    "avg_production_quality": "medium",
    "cringe_detection_rate": 0.05,
    "lighting_quality_avg": 7.2,
    "framing_clarity_avg": 8.1
  },
  "creator_intelligence": {
    "content_gaps": ["Educational content", "Behind-the-scenes"],
    "audience_composition": {
      "age_18_24": 0.35,
      "age_25_34": 0.45,
      "age_35_plus": 0.20
    },
    "growth_opportunities": [
      "Collaborate with 10k–50k fitness creators",
      "Explore trending audio formats"
    ],
    "trend_alignment": 0.78
  },
  "content_type_breakdown": {
    "REEL": {
      "count": 45,
      "avg_engagement_rate": 0.092
    },
    "IMAGE": {
      "count": 75,
      "avg_engagement_rate": 0.062
    }
  }
}
```

**Status Codes:**
- `200` — Success
- `401` — Not authenticated
- `404` — Creator not found

---

### 7. Get Creator Snapshot

**Endpoint:** `GET /api/creators/{creator_id}/snapshot`

**Description:** Returns daily snapshot (point-in-time metrics) for a creator.

**Path Parameters:**
- `creator_id` (string, required) — Creator identifier.

**Response:**
```json
{
  "creator_id": "fitnesscreator",
  "snapshot_date": "2026-04-30",
  "follower_count": 12500,
  "engagement_metrics": {
    "avg_engagement_rate": 0.075,
    "avg_views": 5200
  },
  "growth_score": 72,
  "top_posts": [
    {
      "post_id": "12345",
      "engagement_rate": 0.091,
      "views": 5500
    }
  ]
}
```

**Status Codes:**
- `200` — Success
- `404` — Creator not found

---

### 8. Generate Creator Script

**Endpoint:** `POST /api/creators/{creator_id}/generate-script`

**Description:** Generates a reel script tailored to the creator's niche and audience.

**Path Parameters:**
- `creator_id` (string, required) — Creator identifier.

**Request Body:** None

**Response:**
```json
{
  "hook": "Stop scrolling – here's the one workout you need...",
  "body": "Start with 10 reps, then rest 30 seconds. Repeat 3 times...",
  "cta": "Save this workout for your next gym session!",
  "niche": "fitness",
  "estimated_duration_sec": 30
}
```

**Status Codes:**
- `200` — Success
- `404` — Creator not found

---

## Post Analysis

### 9. Analyze Single Post

**Endpoint:** `POST /api/v1/post-analysis`

**Description:** Runs comprehensive single-post analysis including deterministic metrics, vision analysis, and AI scoring.

**Request Body:**
```json
{
  "post_id": "post_12345",
  "account_id": "fitnesscreator",
  "creator_id": "fitnesscreator",
  "platform": "instagram",
  "post_type": "REEL",
  "media_url": "https://example.com/video.mp4",
  "thumbnail_url": "https://example.com/thumb.jpg",
  "caption_text": "Quick 10-minute workout! 💪 What's your favorite exercise? #fitness #gym",
  "hashtags": ["#fitness", "#gym", "#workout"],
  "likes": 450,
  "comments": 50,
  "views": 5500,
  "audio_name": "motivational_beat_123",
  "posted_at": "2026-04-30T18:30:00Z"
}
```

**Response:**
```json
{
  "status": "succeeded",
  "post": {
    "post_id": "post_12345",
    "post_type": "REEL",
    "media_url": "https://example.com/video.mp4",
    "caption_text": "Quick 10-minute workout!..."
  },
  "vision": {
    "provider": "gemini",
    "status": "ok",
    "signals": [
      {
        "composition": 8.5,
        "lighting": 7.5,
        "subject_clarity": 9.0,
        "aesthetic_quality": 8.0,
        "cringe_score": 18,
        "cringe_label": "not_cringe",
        "cringe_signals": ["Slightly generic pose"],
        "production_level": "medium",
        "adult_content_detected": false
      }
    ]
  },
  "scores": {
    "S1": 8.3,
    "S2": 8.6,
    "S3": 8.1,
    "S4": 8.7,
    "S5": 8.2,
    "S6": 8.8,
    "P": 8.4,
    "predicted_engagement_rate": 0.087,
    "predicted_engagement_rate_notes": [
      "Strong visual quality supports high engagement",
      "CTA present in caption boosts interaction"
    ]
  },
  "ai": {
    "summary": "Excellent post. Strong production quality, clear message, good CTA. Expected to outperform creator average.",
    "drivers": [
      "High-quality production",
      "Relevant trending audio",
      "Clear call-to-action"
    ],
    "recommendations": [
      "Maintain this production quality",
      "Experiment with longer hooks",
      "Add text overlays for clarity"
    ],
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

**Status Codes:**
- `200` — Analysis succeeded
- `400` — Invalid request (missing required fields)
- `500` — Analysis failed

**Notes:**
- S1–S4 scores are deterministic (content, caption, clarity, audience relevance).
- S5–S6 and overall P score may use LLM/vision (fallback to heuristics if unavailable).
- `predicted_engagement_rate` is estimated based on post signals.

---

### 10. Get Post Cringe Summary

**Endpoint:** `GET /api/v1/posts/{post_id}/cringe-summary`

**Description:** Returns cached cringe/brand-safety summary for a previously analyzed post.

**Path Parameters:**
- `post_id` (string, required) — Post identifier (must have been analyzed via endpoint #9).

**Response:**
```json
{
  "cringe_score": 18,
  "cringe_label": "not_cringe",
  "is_cringe": false,
  "cringe_signals": ["Slightly generic pose"],
  "cringe_fixes": ["Use more natural framing"],
  "production_level": "medium",
  "adult_content_detected": false,
  "vision_status": "ok"
}
```

**Status Codes:**
- `200` — Success
- `400` — Invalid post_id
- `404` — Post not found (not analyzed yet)

---

### 11. Get Post Insights

**Endpoint:** `GET /api/v1/posts/{post_id}/insights`

**Description:** Returns cached full analysis payload (deterministic + AI) for a previously analyzed post.

**Path Parameters:**
- `post_id` (string, required) — Post identifier.

**Response:**
```json
{
  "status": "succeeded",
  "post": {
    "post_id": "post_12345",
    "engagement_rate_by_views": 0.0818,
    "like_rate": 8.18,
    "comment_rate": 0.91,
    ...
  },
  "ai_analysis": {
    "summary": "...",
    "drivers": [...],
    "recommendations": [...]
  }
}
```

**Status Codes:**
- `200` — Success
- `404` — Post not found

---

## Health Check

### 12. Health Check

**Endpoint:** `GET /health`

**Description:** Simple health check endpoint for monitoring and load balancers.

**Response:**
```json
{
  "status": "ok"
}
```

**Status Codes:**
- `200` — Service is healthy

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common Status Codes:**
- `400` — Bad Request (invalid input)
- `401` — Unauthorized (not authenticated)
- `404` — Not Found (resource missing)
- `500` — Internal Server Error (server-side issue)

---

## Authentication & Sessions

- **Session-based:** Instagram OAuth sets session cookies (`instagram_user_id`, `instagram_username`).
- **Token storage:** Long-lived Instagram tokens are stored in the token store and retrieved per-user.
- **CORS:** Configured to allow `localhost:3000` (frontend) by default; override with `CORS_ALLOWED_ORIGINS`.

---

## Rate Limiting

- No explicit rate limiting is currently configured; implement via middleware if needed (see `backend/app/api/rate_limiter.py`).

---

## Example Workflows

### Workflow 1: Authenticate & View Dashboard

```
1. GET /api/auth/instagram/login
   → Returns oauth_url
2. User navigates to oauth_url, authorizes
3. Instagram redirects to /api/auth/instagram/callback?code=...&state=...
   → Sets session, stores token
4. GET /api/creator/dashboard?user_id=<instagram_user_id>
   → Returns dashboard with real data
```

### Workflow 2: Analyze a Single Post

```
1. POST /api/v1/post-analysis
   → Analyzes post, caches results
2. GET /api/v1/posts/{post_id}/cringe-summary
   → Returns brand-safety summary
3. GET /api/v1/posts/{post_id}/insights
   → Returns full cached insights
```

### Workflow 3: Demo Mode (No Auth)

```
1. GET /api/creator/dashboard
   → Returns demo dashboard (no user_id param)
```

---

## Versioning

- Current version: `v1` (under `/api/v1/`)
- Legacy endpoints: Under `/api/` (deprecated, no longer developed)

