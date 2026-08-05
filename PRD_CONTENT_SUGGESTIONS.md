# PRD: Content Suggestions - Complete Flow

## Overview
End-to-end implementation of the Content Suggestions feature, covering idea generation, script/caption creation, content planning, idea management, and AI assistant integration.

---

## 1. Generate New Ideas Modal

### UI Elements
- **"Generate New Ideas" button** — top-right of Content Suggestions page, opens modal
- **Close (X)** — dismiss modal

### Form Fields
| Field | Type | Options | Required |
|-------|------|---------|----------|
| Optimize For | Multi-select chips | Maximum Reach, Followers, Engagement, Brand Deals, Saves, Product Sales | Yes (default: Maximum Reach) |
| Content Type | Multi-select chips | Reel, Carousel, Photo | Yes (default: Reel) |
| Topic | Text input | Free text | Optional |
| Audience | Dropdown | Everyone (default), + custom segments | Yes |
| Tone of Voice | Multi-select chips | Professional, Funny, Storytelling, Luxury, Educational | Yes (default: Storytelling) |

### Action
- **"Generate 20 Ideas"** button — triggers background job, shows loading state

---

## 2. AI Generation Progress

### UI Elements
- **Loading spinner** with "Generating Ideas..." heading
- **Progress checklist** showing completed/active steps:
  - Analyzing your recent content
  - Researching trending topics
  - Analyzing your audience
  - Checking competitors
  - Generating high-potential ideas...
- **"Please don't close this window"** warning
- **Close (X)** — dismissible, continues in background

---

## 3. New Ideas Added

### UI Elements
- **Idea cards** in a list, each showing:
  - Thumbnail image
  - Trending Potential badge (Rising, High, Medium, Low)
  - Title
  - Tags (Reel, Carousel, Photo, etc.)
  - Opportunity Score (e.g., 92/100)
  - Expected Reach (e.g., 42K–58K)
- **"Load 20 More Ideas"** button — pagination/infinite scroll

### Actions per Card
- Click → opens idea detail view (step 5)
- Hover → reveals action buttons

---

## 4. Idea Detail View (Click Suggestion Card)

### Header
- "Back to Suggestions" link
- Trending Potential badge
- Title
- Tags (Reel, Travel, Budget Travel)
- Opportunity Score circle (e.g., 92/100)

### Content
- **Hook** — quoted text
- **Why This Idea?** — AI-generated rationale
- **Best Time to Post** — e.g., Thursday, 8:30 PM
- **Content Type** — e.g., Reel
- **Duration** — e.g., 15–30 sec
- **Difficulty** — e.g., Easy
- **Expected Metrics**:
  - Reach: 42K–58K
  - Views: 28K–40K
  - Saves: 1.2K–1.8K
  - Shares: 800–1.2K

### Action Buttons
- **Generate Script** → opens script generator (step 6)
- **Generate Caption** → opens caption generator (step 7)
- **Add to Planner** → opens calendar picker (step 8)
- **More Options (...)** → dropdown menu (step 11)

---

## 5. Generate Script

### Header
- "Back to Idea Details" link
- Title: "Script Generator"

### Layout
- **Left panel**: Script Preview with scenes
- **Right panel**: Script Type selector + Tone + Language

### Script Preview
- Scene-by-scene breakdown:
  - Hook (Scene 1)
  - Scene 2 (1–2s)
  - Scene 3 (3–5s)
  - Scene 4 (6–8s)
  - Scene 5 (9–12s)
  - Scene 6 (13–20s)
  - CTA
- **Estimated Duration** at bottom

### Right Panel Options
| Field | Type | Options |
|-------|------|---------|
| Script Type | Radio/Select | Viral Script, Natural Script, Story Script |
| Tone | Dropdown | Friendly, Professional, Funny, Educational |
| Language | Dropdown | English, Hindi, Spanish, etc. |

### Actions
- **Regenerate** — re-generate with same params
- **Copy Script** — copies full script to clipboard

---

## 6. Generate Caption

### Header
- "Back to Idea Details" link
- Title: "Caption Generator"

### Content
- **Generated caption** with hashtags
- **Caption Tips** sidebar:
  - Open with a strong hook
  - Add question to increase comments
  - Use emoji to increase engagement
  - Add trending hashtags
- **Character count** and **Hashtag count**

### Options
| Field | Type | Options |
|-------|------|---------|
| Tone | Dropdown | Friendly, Professional, Funny, Educational |
| Language | Dropdown | English, Hindi, Spanish, etc. |

### Actions
- **Regenerate** — re-generate caption
- **Copy Caption** — copies to clipboard

---

## 7. Add to Content Planner

### UI Elements
- **Calendar picker** — month view with date selection
- **Time picker** — hour:minute selector
- **"Add Notes (Optional)"** — textarea for reminders
- **Idea summary card** — thumbnail, title, tags, opportunity score

### Actions
- **Cancel** — dismiss
- **Add to Planner** — saves to scheduled_items table

---

## 8. Content Planner View

### UI Elements
- **Week view** — Mon–Sun with date range
- **"Ideas for This Week"** sidebar — scrollable list of saved ideas with scores
- **Filter** button — filter by content type, status, etc.
- **"+ Add Idea"** button — add idea from suggestions

### Idea Cards in Calendar
- Thumbnail + title + content type badge
- Click → opens idea detail or edit view

---

## 9. Save Idea (Collections)

### UI Elements
- **Collection list** with checkboxes:
  - Favorites
  - Next Month Ideas
  - Brand Collaboration Ideas
- **"+ Create New Collection"** — inline input

### Actions
- **Save Idea** — saves to selected collection(s)

---

## 10. More Options Menu (...)

### Menu Items
| Action | Description |
|--------|-------------|
| Duplicate Idea | Creates a copy of the idea |
| Improve This Idea | AI refines the idea with feedback |
| Generate Variations | Creates 3–5 alternative angles |
| Change Content Type | Switch between Reel, Carousel, Photo |
| Schedule for Later | Opens calendar picker |
| Hide This Idea | Removes from visible list (soft delete) |
| Delete Idea | Permanently removes (with confirmation) |

---

## 11. AI Assistant (Optional)

### UI Elements
- **Chat interface** — bottom-right floating panel
- **Pre-filled suggestions**:
  - "Give me 10 ideas for travel reels"
  - "What's trending in my niche?"
- **Input field** with send button

### Behavior
- Context-aware: knows the creator's niche and recent ideas
- Can generate ideas, refine suggestions, answer questions
- Responses are inline in the chat

---

## Backend Endpoints Required

### New Ideas
| Method | Endpoint | Query Params | Description |
|--------|----------|--------------|-------------|
| POST | `/api/v1/accounts/{id}/ideas/generate` | — | Start idea generation job |
| GET | `/api/v1/accounts/{id}/ideas/job/{job_id}` | — | Poll job status |
| GET | `/api/v1/accounts/{id}/ideas` | `page=1&per_page=20&sort=opportunity_score&order=desc&content_type=reel&status=draft&min_score=60` | List ideas with pagination, filtering, sorting |
| POST | `/api/v1/accounts/{id}/ideas/{idea_id}/improve` | — | Improve idea with feedback |
| POST | `/api/v1/accounts/{id}/ideas/{idea_id}/variations` | — | Generate 3–5 variations (creates new ideas with parent_idea_id) |
| POST | `/api/v1/accounts/{id}/ideas/{idea_id}/duplicate` | — | Duplicate idea |
| PATCH | `/api/v1/accounts/{id}/ideas/{idea_id}` | — | Update content_type, status (hide/unhide) |
| DELETE | `/api/v1/accounts/{id}/ideas/{idea_id}` | — | Soft-delete (sets status=deleted) |

### Script & Caption
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/accounts/{id}/ideas/{idea_id}/script` | Generate script (configurable scenes) |
| POST | `/api/v1/accounts/{id}/ideas/{idea_id}/caption` | Generate caption |

### Collections
| Method | Endpoint | Query Params | Description |
|--------|----------|--------------|-------------|
| GET | `/api/v1/accounts/{id}/collections` | `page=1&per_page=50` | List collections with pagination |
| POST | `/api/v1/accounts/{id}/collections` | — | Create collection |
| DELETE | `/api/v1/accounts/{id}/collections/{collection_id}` | — | Delete collection |
| POST | `/api/v1/accounts/{id}/ideas/{idea_id}/save` | — | Save idea to collection(s) |
| DELETE | `/api/v1/accounts/{id}/ideas/{idea_id}/save` | `collection_id=X` | Remove idea from collection |

### Content Planner
| Method | Endpoint | Query Params | Description |
|--------|----------|--------------|-------------|
| GET | `/api/v1/accounts/{id}/planner` | `start_date=2024-05-20&end_date=2024-05-26` | Get scheduled items for date range |
| POST | `/api/v1/accounts/{id}/planner` | — | Schedule idea (checks for conflicts) |
| PUT | `/api/v1/accounts/{id}/planner/{item_id}` | — | Update schedule |
| DELETE | `/api/v1/accounts/{id}/planner/{item_id}` | — | Remove from planner |

### AI Assistant
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/accounts/{id}/assistant/chat` | Send message, get response (rate limited: 20 req/min) |

### Rate Limits
| Endpoint Group | Limit | Window |
|----------------|-------|--------|
| `/ideas/generate` | 3 jobs | 1 hour |
| `/ideas/{id}/script` | 10 requests | 1 hour |
| `/ideas/{id}/caption` | 10 requests | 1 hour |
| `/assistant/chat` | 20 requests | 1 minute |

### Error Response Schemas
```json
{
  "detail": "Human-readable error message",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "status": 429,
  "retry_after_seconds": 3600
}
```

Error codes: `RATE_LIMIT_EXCEEDED`, `PARTIAL_GENERATION`, `JOB_FAILED`, `CONFLICT_DETECTED`, `VALIDATION_ERROR`, `NOT_FOUND`

### Concurrency Rules
- Only 1 active generation job per account at a time
- New job request while one is active → returns 409 Conflict with `existing_job_id`
- Client can poll existing job or cancel it before starting new one

---

## Database Tables

### `ideas`
- `id` (UUID, PK)
- `account_id` (FK → accounts)
- `parent_idea_id` (UUID, FK → ideas, nullable) — links variations to parent
- `title` (text)
- `hook` (text)
- `rationale` (text)
- `content_type` (enum: reel, carousel, photo)
- `opportunity_score` (float)
- `expected_reach_min` (int)
- `expected_reach_max` (int)
- `expected_views_min` (int)
- `expected_views_max` (int)
- `expected_saves_min` (int)
- `expected_saves_max` (int)
- `expected_shares_min` (int)
- `expected_shares_max` (int)
- `difficulty` (enum: easy, medium, hard)
- `duration_seconds` (int)
- `best_time_to_post` (text)
- `trend_reference` (text)
- `tags` (jsonb)
- `status` (enum: draft, saved, scheduled, published, hidden, deleted)
- `generation_job_id` (UUID, FK → idea_generation_jobs, nullable)
- `created_at`, `updated_at`

### `idea_generation_jobs`
- `id` (UUID, PK)
- `account_id` (FK → accounts)
- `status` (enum: queued, processing, completed, failed, partial)
- `params` (jsonb) — stores generation params (optimize_for, content_type, tone, etc.)
- `total_requested` (int)
- `total_generated` (int) — may be < total_requested on partial failure
- `error_message` (text, nullable)
- `created_at`, `started_at`, `completed_at`

### `collections`
- `id` (UUID, PK)
- `account_id` (FK → accounts)
- `name` (text)
- `created_at`

### `collection_ideas`
- `collection_id` (FK → collections)
- `idea_id` (FK → ideas)
- `saved_at` (timestamp)

### `scheduled_items`
- `id` (UUID, PK)
- `account_id` (FK → accounts)
- `idea_id` (FK → ideas)
- `scheduled_date` (date)
- `scheduled_time` (time)
- `notes` (text, nullable)
- `status` (enum: scheduled, published, cancelled)
- UNIQUE constraint on `(account_id, scheduled_date, scheduled_time)` — prevents double-booking

### `idea_scripts`
- `id` (UUID, PK)
- `idea_id` (FK → ideas)
- `script_type` (enum: viral, natural, story)
- `tone` (text)
- `language` (text)
- `content` (text) — stores scenes as JSON array
- `scenes` (jsonb) — structured scene data: `[{scene_number, text, duration_seconds, visual_direction}]`
- `estimated_duration` (int)
- `created_at`

### `idea_captions`
- `id` (UUID, PK)
- `idea_id` (FK → ideas)
- `tone` (text)
- `language` (text)
- `content` (text)
- `character_count` (int)
- `hashtag_count` (int)
- `created_at`

---

## Implementation Phases

### Phase 0: Database & Models
- Create Alembic migration for all new tables
- Add `parent_idea_id` and `generation_job_id` to ideas table
- Add `idea_generation_jobs` table
- Add `scenes` jsonb column to `idea_scripts`
- Add UNIQUE constraint on `scheduled_items(account_id, scheduled_date, scheduled_time)`
- Create Pydantic models for all request/response types
- Test migrations roll forward and back cleanly

### Phase 1: Idea Generation
- Build Generate New Ideas modal UI
- Implement backend job queue for idea generation (RQ + sync fallback)
- Add progress polling endpoint
- Implement concurrent job detection (409 if job already active)
- Handle partial failures (return generated ideas + error message)
- Display generated ideas with pagination

### Phase 2: Idea Detail & Actions
- Build idea detail view with full metrics
- Implement Script Generator modal (configurable scenes)
- Implement Caption Generator modal
- Add "Add to Planner" calendar picker with conflict detection

### Phase 3: Collections & Planner
- Build collections UI (save to collection)
- Build Content Planner calendar view
- Implement scheduling endpoints with conflict prevention

### Phase 4: More Options & Management
- Implement duplicate, improve, variations endpoints
- Build More Options dropdown menu
- Add hide/delete functionality
- Add filtering and sorting on idea list

### Phase 5: AI Assistant
- Build floating chat UI
- Implement context-aware chat endpoint
- Add pre-filled suggestion chips
- Rate limit: 20 requests/minute

---

## Frontend Components

| Component | Location | Description |
|-----------|----------|-------------|
| `GenerateIdeasModal` | `components/GenerateIdeasModal.jsx` | Form for idea generation params |
| `GenerationProgress` | `components/GenerationProgress.jsx` | Loading state with progress steps |
| `IdeaCard` | `components/IdeaCard.jsx` | Idea thumbnail + score + tags |
| `IdeaDetailView` | `components/IdeaDetailView.jsx` | Full idea detail with metrics |
| `ScriptGenerator` | `components/ScriptGenerator.jsx` | Script preview + options |
| `CaptionGenerator` | `components/CaptionGenerator.jsx` | Caption preview + options |
| `ContentPlanner` | `components/ContentPlanner.jsx` | Calendar + scheduled items |
| `CollectionsManager` | `components/CollectionsManager.jsx` | Save to collections modal |
| `MoreOptionsMenu` | `components/MoreOptionsMenu.jsx` | Dropdown with actions |
| `AIAssistant` | `components/AIAssistant.jsx` | Floating chat panel |

---

## Success Metrics

- Idea generation completes in < 30 seconds
- Script/caption generation completes in < 10 seconds
- 80% of generated ideas have opportunity score > 60
- Users schedule at least 3 ideas per session
- AI Assistant handles 80% of common requests without escalation
