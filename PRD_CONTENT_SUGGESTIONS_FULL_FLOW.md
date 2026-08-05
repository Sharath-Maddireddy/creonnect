# PRD: Content Suggestions — Complete Flow

**Author:** Engineering Team
**Status:** Draft
**Last Updated:** 2026-07-26
**Target:** Production
**Design Reference:** Content Suggestions Complete Flow (12-step UI)

---

## 1. Overview

Content Suggestions is the flagship AI Studio feature that provides creators with personalized, AI-powered content ideas. This PRD defines the **complete end-to-end flow** from idea generation through content planning, covering every screen, button, and backend endpoint shown in the design.

### 1.1 Current State

- Basic trend recommendation cards with opportunity scores, reach estimates, and difficulty
- "Generate New Ideas" button exists but has no customization modal
- No script generation, no caption generation, no content planner integration
- "Ask AI Assistant" is keyword matching, not a real conversational AI
- No idea collections / saving system
- No "Generate Weekly Plan" feature
- No duplicate/improve/variation generation

### 1.2 Target State (12-Step Flow)

| Step | Screen | Description |
|------|--------|-------------|
| 1 | Content Suggestions (main) | Landing page with AI Weekly Opportunity banner, filter tabs, suggestion cards |
| 2 | Generate New Ideas (modal) | Customize optimization goal, content type, topic, audience, tone |
| 3 | AI Generation (progress) | Real-time progress steps while AI generates ideas |
| 4 | New Ideas Added | 20 new ideas appended to the list with "Load More" |
| 5 | Suggestion Card Detail | Full card view with hook, why this idea, reach/saves/shares estimates |
| 6 | Script Generator | AI-generated script with scene breakdown, type selector, tone, language |
| 7 | Caption Generator | AI-generated caption with hashtags, tips, tone, language |
| 8 | Content Planner (schedule) | Date/time picker to schedule the idea |
| 9 | Content Planner (calendar) | Weekly calendar view showing scheduled content |
| 10 | Save Idea (collections) | Save to Favorites, custom collections, or create new collection |
| 11 | More Options (menu) | Duplicate, Improve, Variations, Change Type, Schedule, Hide, Delete |
| 12 | AI Assistant (chat) | Conversational AI for custom idea requests |

---

## 2. Goals and Objectives

| Goal | Success Metric | Target |
|------|---------------|--------|
| Complete idea-to-plan flow | User can go from idea → script → caption → scheduled post | 100% of steps functional |
| Customizable generation | User can set optimization goal, content type, topic, audience, tone | All 5 controls functional |
| Real-time progress | Generation shows step-by-step progress, not a spinner | <30s average generation |
| Script quality | Generated scripts have scene breakdowns, CTA, duration estimate | All scripts include 5+ scenes |
| Caption quality | Generated captions include hashtags, hooks, engagement CTAs | All captions include 5+ hashtags |
| Calendar integration | Scheduled ideas appear in weekly calendar view | Real-time calendar sync |
| Idea collections | Users can save, organize, and retrieve ideas | Unlimited collections |
| Conflict-free scheduling | Planner detects and resolves time-slot conflicts | 3 resolution modes |
| Compounding error prevention | Bad ideas don't cascade to waste script/caption credits | Independent regeneration |

---

## 3. Functional Requirements

### 3.1 Step 1 — Content Suggestions Main Page

**Route:** `/trends`
**Component:** `TrendRecommendations.jsx`

#### 3.1.1 AI Weekly Opportunity Banner

| Element | Source | Description |
|---------|--------|-------------|
| Opportunity Score (circular gauge) | `opportunity_score` from trend analysis | 0-100 score with animated gauge |
| Opportunity Level label | Score → label mapping | "Very High" / "High" / "Medium" / "Low" |
| Insight bullets | `opportunity_bullets` from `TrendAnalysisResult` | 3-4 AI-generated bullet points |
| "Generate Weekly Plan →" button | Triggers Step 2 modal | Opens Generate New Ideas modal |

#### 3.1.2 Filter Tabs

```
All | Reels | Carousel | Photo | Trending | Educational | Personal Story | Brand Friendly | Beginner | Advanced
```

- Tabs filter the suggestion card grid by `content_style`, `trend_type`, `difficulty`, and `momentum`
- Active tab state persists during session

#### 3.1.3 Sort Dropdown

Options: `Opportunity | Reach | Momentum | Type`
- Cycles through sort modes on click
- Re-sorts the card grid in-place

#### 3.1.4 Suggestion Cards

Each card renders:
- Thumbnail placeholder (gradient based on trend type)
- Momentum badge (Rising/Peaking/Falling with icon)
- Title (`suggested_title`)
- Tags: content style, trend type
- Hook text (`hook`)
- "Why this idea?" expandable section (`rationale`)
- Opportunity Score (circular gauge, 0-100)
- Opportunity Level label
- Best Time to Post (`best_time`)
- Content Type (`content_style`)
- Difficulty badge (`difficulty`)
- Expected Reach range (`expected_reach_min` – `expected_reach_max`)
- Views estimate (derived from reach)
- Saves estimate (derived from engagement)
- Shares estimate (derived from engagement)
- Action buttons: "Generate Script", "Generate Caption", "Add to Planner", "..." (more)

#### 3.1.5 Right Sidebar

| Section | Source | Fields |
|---------|--------|--------|
| Today's Insights | `daily_insights` | Audience Active Window, Best Content Type, Trending Audio count, Competition Level, Overall Opportunity |
| Analysis Pipeline | Derived | Niche Discovery, Trend Fetching, Recommendations (completion dots) |
| Niche Detected | `niche` | Primary Category, Sub-niches, Confidence % |
| Trending Topics | `global_trends` | Topic name, Audience Match %, Momentum sparkline |
| Content Gaps | `content_gaps` | Gap description, severity icon (warning/info/opportunity) |
| Ask AI Assistant | LLM | Chat input + suggested chips |

---

### 3.2 Step 2 — Generate New Ideas (Modal)

**Trigger:** "Generate New Ideas" button or "Generate Weekly Plan →"

#### 3.2.1 Modal UI

```
┌─────────────────────────────────────────┐
│  Generate New Ideas                  ✕  │
│  Tell us what you want AI to focus on   │
│                                         │
│  Optimize For                           │
│  [Maximum Reach] [Followers] [Engagement]│
│  [Brand Deals] [Saves] [Product Sales]  │
│                                         │
│  Content Type                           │
│  [● Reel] [Carousel] [Photo]            │
│                                         │
│  Topic (Optional)                       │
│  [e.g., Travel packing, Paris, Budget   │
│   travel]                               │
│                                         │
│  Audience                               │
│  [Everyone ▼]                           │
│                                         │
│  Tone of Voice                          │
│  [Professional] [Funny] [Storytelling]  │
│  [Luxury] [Educational]                 │
│                                         │
│        [ Generate 20 Ideas ✨ ]          │
└─────────────────────────────────────────┘
```

#### 3.2.2 Controls

| Control | Type | Options | Default |
|---------|------|---------|---------|
| Optimize For | Multi-select chips | Maximum Reach, Followers, Engagement, Brand Deals, Saves, Product Sales | Maximum Reach |
| Content Type | Radio chips | Reel, Carousel, Photo | Reel |
| Topic | Text input (optional) | Free text | Empty |
| Audience | Dropdown | Everyone, 18-24, 25-34, 35-44, 45+, Gen Z, Millennials | Everyone |
| Tone of Voice | Multi-select chips | Professional, Funny, Storytelling, Luxury, Educational | Professional |

#### 3.2.3 Backend Endpoint

**POST** `/api/v1/accounts/{account_id}/trends/generate-ideas`

```python
class GenerateIdeasRequest(BaseModel):
    optimization_goals: list[str]  # ["maximum_reach", "engagement", ...]
    content_type: str               # "reel" | "carousel" | "photo"
    topic: str | None               # optional topic focus
    audience: str                   # "everyone" | "18-24" | ...
    tone_of_voice: list[str]        # ["professional", "storytelling", ...]
    count: int = 20                 # number of ideas to generate (1-10, default 5)

class GenerateIdeasResponse(BaseModel):
    job_id: str                     # for polling progress
    status: str                     # "queued" | "processing" | "completed"
    estimated_seconds: int          # estimated time to completion
```

---

### 3.3 Step 3 — AI Generation Progress

**Trigger:** After submitting Generate New Ideas form

#### 3.3.1 Progress UI

```
┌─────────────────────────────────────────┐
│  Generating Ideas...               ✕    │
│  This may take a few seconds           │
│                                         │
│  [Animated spinner/pulse]               │
│                                         │
│  ✓ Analysing your recent content        │
│  ✓ Researching trending topics          │
│  ✓ Analysing your audience              │
│  ✓ Checking competitors                 │
│  ○ Generating high-potential ideas...   │
│                                         │
│  ⚠ Please don't close this window       │
└─────────────────────────────────────────┘
```

#### 3.3.2 Progress Steps

| Step | Backend Operation | Duration |
|------|------------------|----------|
| 1. Analysing recent content | Load posts, compute engagement metrics | 2-5s |
| 2. Researching trending topics | Fetch global trends for niche | 3-8s |
| 3. Analysing audience | Load audience demographics, activity patterns | 2-4s |
| 4. Checking competitors | Compare with similar creators | 2-5s |
| 5. Generating ideas | LLM call with full context | 5-15s |

#### 3.3.3 Backend: Progress Polling

**GET** `/api/v1/accounts/{account_id}/trends/generate-ideas/{job_id}/status`

```python
class IdeaGenerationProgress(BaseModel):
    job_id: str
    status: str  # "queued" | "processing" | "completed" | "failed"
    current_step: int       # 0-4
    total_steps: int        # 5
    step_label: str         # "Analysing your recent content"
    percent_complete: float # 0.0 - 1.0
```

**Frontend:** Poll every 1-2 seconds until `status == "completed"`.

---

### 3.4 Step 4 — Paginated Ideas List

**Trigger:** Generation completes, or page load

#### 3.4.1 Behavior

- 20 new `TrendRecommendation` objects appended to the existing list
- New cards appear with a subtle entrance animation
- "Load 20 More Ideas" button at the bottom of the grid
- Total idea count displayed (e.g., "20 new ideas added")

#### 3.4.2 Backend Endpoint

**GET** `/api/v1/accounts/{account_id}/trends/ideas?page=1&per_page=20&sort=created_at&order=desc`

```python
class PaginatedIdeasResponse(BaseModel):
    data: list[TrendRecommendation]
    meta: PaginationMeta

class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total_count: int
    total_pages: int
    has_next: bool
    has_prev: bool
```

**Pagination Rules:**
- `per_page`: 20 default, 50 max (server-enforced cap)
- `sort` options: `created_at`, `updated_at`, `engagement_score`
- If `page > total_pages`, return empty `data` array with `200 OK` (not 404)
- Optional filters: `platform`, `status`, `content_type`

---

### 3.5 Step 5 — Suggestion Card Detail

**Trigger:** Click on a suggestion card

#### 3.5.1 Detail View Layout

```
┌─────────────────────────────────────────┐
│  ← Back to Suggestions                  │
│                                         │
│  [Thumbnail]     Opportunity Score: 92  │
│                  ●━━━━━━━━━━━● 92/100   │
│                  Very High              │
│                                         │
│  🎬 Reel  ✈ Travel  🏷 Budget Travel    │
│                                         │
│  How I travelled Vietnam for ₹20,000    │
│                                         │
│  Hook:                                  │
│  "Everyone told me Vietnam was          │
│   expensive... here's how I did it      │
│   for less than ₹20,000"               │
│                                         │
│  Why this idea?                         │
│  Your audience loves travel content.    │
│  Your last travel reel got 3x more      │
│  reach and 2x more saves than your      │
│  average. Budget travel is currently     │
│  trending and has high search volume.   │
│                                         │
│  ─── Key Metrics ─────────────────────  │
│  Best Time to Post    Content Type      │
│  Thursday, 8:30 PM    Reel              │
│                                         │
│  What to Expect                         │
│  ┌────────┬────────┬────────┬────────┐  │
│  │ Reach  │ Views  │ Saves  │ Shares │  │
│  │ 42K-58K│ 28K-40K│1.2K-   │ 800-   │  │
│  │        │        │ 1.8K   │ 1.2K   │  │
│  └────────┴────────┴────────┴────────┘  │
│                                         │
│  [Generate Script] [Generate Caption]   │
│  [Add to Planner]  [...]                │
└─────────────────────────────────────────┘
```

#### 3.5.2 Metrics Computation

| Metric | Formula | Source |
|--------|---------|--------|
| Reach | `expected_reach_min` – `expected_reach_max` | `_estimate_reach_range()` |
| Views | `reach × 0.65` (typical view/reach ratio) | Derived |
| Saves | `views × save_rate` from historical posts | `post.derived_metrics.save_rate` |
| Shares | `views × share_rate` from historical posts | `post.derived_metrics.share_rate` |

---

### 3.6 Step 6 — Script Generator

**Trigger:** "Generate Script" button on card detail or card action

#### 3.6.1 Script Generator UI

```
┌─────────────────────────────────────────┐
│  ← Back to Idea Details                 │
│                                         │
│  Script Generator                       │
│  AI creates script for your idea        │
│                                         │
│  ┌── Script Preview ──────────────────┐ │
│  │ Hook:                               │ │
│  │ "Everyone told me Vietnam was       │ │
│  │  expensive..."                      │ │
│  │                                     │ │
│  │ Scene 1 (0-3s):                     │ │
│  │ Show your flight ticket → "₹20,000" │ │
│  │                                     │ │
│  │ Scene 2 (3-8s):                     │ │
│  │ Street food montage — clean &       │ │
│  │ affordable                          │ │
│  │                                     │ │
│  │ Scene 3 (8-14s):                    │ │
│  │ Hidden food — best meals under ₹100 │ │
│  │                                     │ │
│  │ Scene 4 (14-22s):                   │ │
│  │ Places to visit — free & low cost   │ │
│  │                                     │ │
│  │ Scene 5 (22-28s):                   │ │
│  │ Total breakdown & tips              │ │
│  │                                     │ │
│  │ CTA: "Save this for your trip 🗺"   │ │
│  └─────────────────────────────────────┘ │
│                                         │
│  Estimated Duration: 28s                │
│                                         │
│  ┌── Script Type ──┐  ┌── Settings ──┐ │
│  │ ○ Viral Script  │  │ Tone: [▼]    │ │
│  │ ○ Natural Script│  │ Lang: [▼]    │ │
│  │ ○ Story Script  │  │              │ │
│  └─────────────────┘  └──────────────┘ │
│                                         │
│           [ Copy Script 📋 ]            │
└─────────────────────────────────────────┘
```

#### 3.6.2 Script Types

| Type | Style | Scene Structure |
|------|-------|-----------------|
| Viral Script | Punchy, fast-paced, hook-first | Hook → Problem → Solution → Proof → CTA |
| Natural Script | Conversational, authentic | Hook → Story → Details → Takeaway → CTA |
| Story Script | Narrative, emotional arc | Hook → Setup → Conflict → Resolution → CTA |

#### 3.6.3 Backend Endpoint

**POST** `/api/v1/accounts/{account_id}/trends/generate-script`

```python
class GenerateScriptRequest(BaseModel):
    idea_id: str                     # reference to the idea
    trend_reference: str             # trend topic_name
    suggestion_title: str            # the idea title
    hook: str | None                 # existing hook to build on
    script_type: str                 # "viral" | "natural" | "story"
    tone: str                        # "friendly" | "professional" | "funny" | ...
    language: str                    # "en" | "hi" | "es" | ...
    duration_seconds: int = 60       # target duration

class Scene(BaseModel):
    scene_number: int
    time_range: str                  # "0-3s"
    description: str
    visual_notes: str | None

class GenerateScriptResponse(BaseModel):
    hook: str
    scenes: list[Scene]
    cta: str
    estimated_duration_sec: int
    full_script: str                 # formatted text version
    idea_id: str                     # lineage tracking
```

**Lineage:** If `idea_id` is provided, the UI shows breadcrumb: "Script generated from: [idea title]".

#### 3.6.4 LLM Prompt Structure

```
System: You are a professional short-form video scriptwriter...
User: Write a {script_type} script for: {suggestion_title}
Hook: {hook}
Tone: {tone}
Language: {language}
Format: Return TOON with hook, scenes (number, time_range, description, visual_notes), cta, estimated_duration_sec
```

---

### 3.7 Step 7 — Caption Generator

**Trigger:** "Generate Caption" button

#### 3.7.1 Caption Generator UI

```
┌─────────────────────────────────────────┐
│  ← Back to Idea Details    [Regenerate] │
│                                         │
│  Caption Generator                      │
│  Create engaging caption with hashtags  │
│                                         │
│  ┌── Generated Caption ──────────────┐ │
│  │ Vietnam on a budget is TOTALLY     │ │
│  │ possible! 🇻🇳                      │ │
│  │                                    │ │
│  │ Here's how I explored more, spent  │ │
│  │ less and made the best memories    │ │
│  │ for under ₹20,000 ✨              │ │
│  │                                    │ │
│  │ Which tip would you try first?     │ │
│  │ Comment below! 👇                  │ │
│  │                                    │ │
│  │ #vietnamtravel #vietnamtrip        │ │
│  │ #budgettravel #backpacking         │ │
│  │ #vietnamreels #traveltips          │ │
│  │ #wanderlust #exploremore           │ │
│  │ #travelgram #reallife              │ │
│  └────────────────────────────────────┘ │
│                                         │
│  Characters: 382  Hashtags: 12          │
│                                         │
│  ┌── Caption Tips ──┐  ┌── Settings ─┐ │
│  │ ✓ Open with a    │  │ Tone: [▼]   │ │
│  │   strong hook    │  │ Lang: [▼]   │ │
│  │ ✓ Add question to│  │             │ │
│  │   increase       │  │             │ │
│  │   engagement     │  │             │ │
│  │ ✓ Use emoji to   │  │             │ │
│  │   increase       │  │             │ │
│  │   engagement     │  │             │ │
│  │ ✓ Add trending   │  │             │ │
│  │   hashtags       │  │             │ │
│  └──────────────────┘  └─────────────┘ │
│                                         │
│           [ Copy Caption 📋 ]           │
└─────────────────────────────────────────┘
```

#### 3.7.2 Backend Endpoint

**POST** `/api/v1/accounts/{account_id}/trends/generate-caption`

```python
class GenerateCaptionRequest(BaseModel):
    idea_id: str                     # reference to the idea
    script_id: str | None            # optional, enriches caption with script context
    trend_reference: str
    suggestion_title: str
    hook: str | None
    platforms: list[str]             # ["instagram", "linkedin"]
    tone: str
    language: str
    include_hashtags: bool = True
    max_hashtags: int = 10

class GenerateCaptionResponse(BaseModel):
    captions: list[GeneratedCaption]  # one per platform
    idea_id: str                      # lineage tracking

class GeneratedCaption(BaseModel):
    platform: str
    caption_text: str
    hashtags: list[str]
    character_count: int
    hashtag_count: int
    tips_applied: list[str]  # ["Open with a strong hook", "Add question", ...]
```

**Lineage:** If `idea_id` is provided, UI shows: "Caption generated from: [idea title]".

---

### 3.8 Step 8 — Schedule to Planner (with Conflict Resolution)

**Trigger:** "Add to Planner" button

#### 3.8.1 Scheduler UI

```
┌─────────────────────────────────────────┐
│  ← Back                                 │
│                                         │
│  How I travelled Vietnam for ₹20,000    │
│  🎬 Reel  ✈ Travel  🏷 Budget Travel    │
│                                         │
│  Opportunity Score: 92/100 Very High    │
│                                         │
│  Select Date & Time                     │
│  ┌── May 2024 ──────────────────────┐  │
│  │ Mon Tue Wed Thu Fri Sat Sun      │  │
│  │  5   6   7   8   9  10  11      │  │
│  │ 12  13  14  15  16  17  18      │  │
│  │ 19  20  21 [22] 23  24  25      │  │
│  │ 26  27  28  29  30  31          │  │
│  └─────────────────────────────────┘  │
│                                         │
│  Time: [08] : [30] PM                  │
│                                         │
│  Add Notes (Optional)                   │
│  [Add notes or reminders for this      │
│   post...]                              │
│                                         │
│  [Cancel]              [Add to Planner] │
└─────────────────────────────────────────┘
```

#### 3.8.2 Backend Endpoint

**POST** `/api/v1/accounts/{account_id}/planner/schedule`

```python
class ScheduleIdeaRequest(BaseModel):
    idea_id: str
    scheduled_date: str               # "2026-01-22"
    scheduled_time: str               # "14:00:00"
    platform: str                     # "instagram" | "tiktok" | "linkedin"
    conflict_resolution: str = "reject"  # "reject" | "warn" | "force"
    notes: str | None = None
```

**Response — No Conflict:**
```python
HTTP 201 Created
{
    "status": "scheduled",
    "scheduled_item": {
        "id": "abc123",
        "idea_id": "idea_456",
        "platform": "instagram",
        "scheduled_at": "2026-01-22T14:00:00Z"
    }
}
```

**Response — Conflict (warn mode):**
```python
HTTP 409 Conflict
{
    "status": "conflict",
    "conflicting_items": [
        {
            "id": "xyz789",
            "scheduled_time": "14:30:00",
            "platform": "tiktok",
            "idea_title": "Behind the scenes: our roasting process"
        }
    ],
    "suggestion": "Next available slot: 16:00 on 2026-01-22",
    "available_slots": ["16:00", "17:00", "17:30"]
}
```

#### 3.8.3 Conflict Resolution Modes

| Mode | Behavior | Frontend UX |
|------|----------|-------------|
| `reject` (default) | Returns 409, does not schedule | Conflict dialog with available slots |
| `warn` | Returns conflict payload, still schedules with `conflict_acknowledged: true` | Soft warning banner |
| `force` | Schedules immediately, bumps conflicting items forward by +30 min | Toast: "1 item was rescheduled to accommodate this" |

**Conflict definition:** Same platform + scheduled within 30 minutes of another item.

#### 3.8.4 Unschedule

**DELETE** `/api/v1/accounts/{account_id}/planner/schedule/{scheduled_item_id}`

```python
HTTP 204 No Content
```

---

### 3.9 Step 9 — Content Planner (Calendar View)

**Trigger:** Navigate to planner or click "View in Planner"

#### 3.9.1 Calendar UI

```
┌─────────────────────────────────────────┐
│  Content Planner                        │
│  [Week View ▼]  ← May 20 – May 26 →    │
│  Ideas for This Week                    │
│                                         │
│  Mon 20    Tue 21    Wed 22    Thu 23   │
│  ────────  ────────  ────────  ──────── │
│            Budget    Packing   How I     │
│            Travel    Tips      travelled │
│            Reel      Carousel  Vietnam   │
│            Score:90  Score:88  Score:78  │
│                                         │
│  Fri 24    Sat 25    Sun 26             │
│  ────────  ────────  ────────           │
│                                [+ Add]  │
│                                         │
│  ← Filters                              │
└─────────────────────────────────────────┘
```

#### 3.9.2 Backend Endpoint

**GET** `/api/v1/accounts/{account_id}/planner?week_start=2026-01-20&platform=instagram`

```python
class PlannerResponse(BaseModel):
    week_start: str
    days: list[DaySchedule]

class DaySchedule(BaseModel):
    date: str
    items: list[ScheduledItem]

class ScheduledItem(BaseModel):
    id: str
    idea_id: str
    idea_title: str
    platform: str
    scheduled_at: str
    status: str  # "scheduled" | "posted" | "skipped"
```

---

### 3.10 Step 10 — Save to Collections (Full CRUD)

**Trigger:** "Save Idea" button on card

#### 3.10.1 Collections UI

```
┌─────────────────────────────────────────┐
│  Save Idea                              │
│  Add this idea to a collection          │
│                                         │
│  [✓] Favorites                          │
│  [ ] Next Month Ideas                   │
│  [ ] Brand Collaboration Ideas          │
│                                         │
│  + Create New Collection                │
│                                         │
│          [ Save Idea ]                  │
└─────────────────────────────────────────┘
```

#### 3.10.2 Backend Endpoints

**List collections:**
```
GET /api/v1/accounts/{account_id}/collections
→ 200 OK
[{ "id": "...", "name": "Favorites", "idea_count": 12 }, ...]
```

**Create collection:**
```
POST /api/v1/accounts/{account_id}/collections
{ "name": "Holiday Campaign Q4", "description": "..." }
→ 201 Created
{ "id": "...", "name": "Holiday Campaign Q4", "description": "...", "created_at": "..." }
```

**Add idea to collection:**
```
POST /api/v1/accounts/{account_id}/collections/{collection_id}/ideas
{ "idea_id": "abc123" }
→ 201 Created
→ 409 Conflict (already in collection)
```

**Remove idea from collection:**
```
DELETE /api/v1/accounts/{account_id}/collections/{collection_id}/ideas/{idea_id}
→ 204 No Content
→ 404 Not Found
```

**List collections containing an idea (convenience):**
```
GET /api/v1/accounts/{account_id}/ideas/{idea_id}/collections
→ 200 OK
[{ "collection_id": "...", "name": "Holiday Campaign Q4" }, ...]
```

---

### 3.11 Step 11 — More Options (Improve / Variations / Regenerate)

**Trigger:** "..." button on card

#### 3.11.1 Menu Items

| Action | Icon | Description | Backend |
|--------|------|-------------|---------|
| Duplicate Idea | 📋 | Clone into a new draft | `POST /ideas/{id}/duplicate` |
| Improve This Idea | ✨ | LLM refines the idea | `POST /ideas/{id}/improve` |
| Generate Variations | 🔄 | Create 3 variations | `POST /ideas/{id}/variations` |
| Regenerate | 🔁 | Full regeneration from scratch | `POST /ideas/{id}/regenerate` |
| Change Content Type | 🎬 | Switch Reel↔Carousel↔Photo | `PUT /ideas/{id}/type` |
| Schedule for Later | 📅 | Opens Step 8 scheduler | — |
| Hide This Idea | 👁 | Remove from view | `DELETE /ideas/{id}/hide` |
| Delete Idea | 🗑 | Permanently delete | `DELETE /ideas/{id}` |

#### 3.11.2 Backend Endpoints

**Improve (targeted refinement):**
```
POST /api/v1/accounts/{account_id}/ideas/{idea_id}/improve
{
    "feedback": "Make the hook punchier",
    "aspect": "hook"                    # "hook" | "title" | "rationale" | "full"
}
→ 202 Accepted
{ "job_id": "job_imp_123", "status": "processing" }
```

**Variations (alternative angles):**
```
POST /api/v1/accounts/{account_id}/ideas/{idea_id}/variations
{
    "count": 3                          # 1-5 variations
}
→ 202 Accepted
{ "job_id": "job_var_456", "status": "processing" }
```

**Regenerate (full replacement):**
```
POST /api/v1/accounts/{account_id}/ideas/{idea_id}/regenerate
{
    "aspect": "full"                    # always full for regenerate
}
→ 202 Accepted
{ "job_id": "job_reg_789", "status": "processing" }
```

**Key difference:** `improve` keeps the current idea and tweaks based on feedback. `regenerate` creates an entirely new idea with a different seed. Neither cascades to existing scripts/captions.

---

### 3.12 Step 12 — AI Assistant (Chat)

**Trigger:** "Ask AI Assistant" panel in sidebar

#### 3.12.1 Chat UI

```
┌─────────────────────────────────────────┐
│  AI Assistant ✨              [Close]   │
│                                         │
│  Hi Lucy! What kind of ideas are you    │
│  looking for today?                     │
│                                         │
│            [Give me 10 ideas for        │
│             travel reels]        →      │
│                                         │
│  🤖 Sure! Here are 10 travel reel       │
│  ideas for you...                       │
│                                         │
│  [Ask anything...              ] [Send] │
└─────────────────────────────────────────┘
```

#### 3.12.2 Suggested Prompts

- "Give me 10 ideas for travel reels"
- "How to make content without showing face"
- "Educational carousel ideas for my niche"
- "What's trending in my category this week"

#### 3.12.3 Backend Endpoint

**POST** `/api/v1/accounts/{account_id}/trends/ai-assistant`

```python
class AssistantRequest(BaseModel):
    message: str
    context: dict | None  # optional: current trend, niche, etc.

class AssistantResponse(BaseModel):
    reply: str
    suggested_ideas: list[TrendRecommendation] | None  # if applicable
```

#### 3.12.4 LLM Prompt Structure

```
System: You are a creative content assistant for {niche} creators.
        You help generate content ideas, hooks, scripts, and captions.
        Be specific, actionable, and reference current trends.
User: {message}
Context: Creator niche={niche}, recent content={content_style},
         trending topics={trends[:5]}
```

---

## 4. Backend Architecture

### 4.1 New Files

| File | Purpose |
|------|---------|
| `backend/app/services/script_generator.py` | Script generation logic |
| `backend/app/services/caption_generator.py` | Caption generation logic |
| `backend/app/services/content_planner.py` | Calendar/scheduling + conflict resolution |
| `backend/app/services/idea_collections.py` | Collections CRUD |
| `backend/app/services/ai_assistant.py` | Conversational AI service |
| `backend/app/services/idea_generation.py` | Custom idea generation with preferences |
| `backend/app/services/job_queue.py` | Async job queue for AI generation |
| `backend/app/api/script_routes.py` | Script API endpoints |
| `backend/app/api/caption_routes.py` | Caption API endpoints |
| `backend/app/api/planner_routes.py` | Planner API endpoints |
| `backend/app/api/collection_routes.py` | Collections API endpoints |
| `backend/app/api/assistant_routes.py` | AI Assistant API endpoints |
| `backend/app/domain/planner_models.py` | Pydantic models for planner |
| `backend/app/domain/collection_models.py` | Pydantic models for collections |
| `alembic/versions/xxxx_create_content_suggestions_tables.py` | DB migration |

### 4.2 Database Schema

```sql
-- Ideas table — stores all AI-generated content as JSONB for prompt-version flexibility
CREATE TABLE ideas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id VARCHAR(120) NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    platform TEXT,                      -- instagram, tiktok, linkedin
    hook TEXT,
    script JSONB,                      -- { hook, body: [...], cta }
    captions JSONB,                    -- [{ platform, text, hashtags: [...] }]
    variations JSONB DEFAULT '[]',     -- alternative hooks/angles
    engagement_score FLOAT,
    generation_metadata JSONB,         -- { model, prompt_version, tokens_used }
    status TEXT DEFAULT 'draft',       -- draft | generated | scheduled | published
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Collections
CREATE TABLE collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id VARCHAR(120) NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Collection ↔ Idea junction
CREATE TABLE collection_ideas (
    collection_id UUID REFERENCES collections(id) ON DELETE CASCADE,
    idea_id UUID REFERENCES ideas(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (collection_id, idea_id)
);

-- Scheduled items for the content planner
CREATE TABLE scheduled_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id VARCHAR(120) NOT NULL,
    idea_id UUID NOT NULL REFERENCES ideas(id),
    platform TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    conflict_acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (platform, scheduled_at)
);

-- Idea generation jobs (for async generation)
CREATE TABLE idea_generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id VARCHAR(120) NOT NULL,
    status VARCHAR(50) DEFAULT 'queued',    -- queued | processing | completed | failed
    current_step INT DEFAULT 0,
    total_steps INT DEFAULT 5,
    step_label VARCHAR(255),
    percent_complete FLOAT DEFAULT 0.0,
    optimization_goals JSONB,
    content_type VARCHAR(50),
    topic VARCHAR(255),
    audience VARCHAR(100),
    tone_of_voice JSONB,
    result_count INT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
```

**Key architectural decision:** JSONB for AI outputs (`script`, `captions`, `variations`). Scripts and captions will change shape as prompts evolve. Migrations should be prompt-version-aware, not schema-aware.

### 4.3 API Route Summary

| Method | Endpoint | Step | Description |
|--------|----------|------|-------------|
| POST | `/accounts/{id}/trends/generate-ideas` | 2 | Start idea generation job |
| GET | `/accounts/{id}/trends/generate-ideas/{job_id}/status` | 3 | Poll generation progress |
| GET | `/accounts/{id}/trends/ideas?page=N&per_page=20` | 4 | Paginated idea list |
| POST | `/accounts/{id}/trends/generate-script` | 6 | Generate script for idea |
| POST | `/accounts/{id}/trends/generate-caption` | 7 | Generate caption for idea |
| POST | `/accounts/{id}/planner/schedule` | 8 | Schedule idea to planner |
| DELETE | `/accounts/{id}/planner/schedule/{item_id}` | 8 | Unschedule item |
| GET | `/accounts/{id}/planner?week_start=DATE` | 9 | Get weekly calendar |
| GET | `/accounts/{id}/collections` | 10 | List collections |
| POST | `/accounts/{id}/collections` | 10 | Create collection |
| POST | `/accounts/{id}/collections/{cid}/ideas` | 10 | Save idea to collection |
| DELETE | `/accounts/{id}/collections/{cid}/ideas/{iid}` | 10 | Remove idea from collection |
| GET | `/accounts/{id}/ideas/{iid}/collections` | 10 | List collections for idea |
| POST | `/accounts/{id}/ideas/{iid}/improve` | 11 | Improve an idea |
| POST | `/accounts/{id}/ideas/{iid}/variations` | 11 | Generate variations |
| POST | `/accounts/{id}/ideas/{iid}/regenerate` | 11 | Full regeneration |
| POST | `/accounts/{id}/trends/ai-assistant` | 12 | Chat with AI assistant |

---

## 5. Frontend Architecture

### 5.1 New Components

| Component | File | Step |
|-----------|------|------|
| `GenerateIdeasModal` | `frontend/src/components/GenerateIdeasModal.jsx` | 2 |
| `GenerationProgress` | `frontend/src/components/GenerationProgress.jsx` | 3 |
| `ScriptGenerator` | `frontend/src/components/ScriptGenerator.jsx` | 6 |
| `CaptionGenerator` | `frontend/src/components/CaptionGenerator.jsx` | 7 |
| `ContentPlanner` | `frontend/src/components/ContentPlanner.jsx` | 8, 9 |
| `CalendarView` | `frontend/src/components/CalendarView.jsx` | 9 |
| `SaveIdeaModal` | `frontend/src/components/SaveIdeaModal.jsx` | 10 |
| `MoreOptionsMenu` | `frontend/src/components/MoreOptionsMenu.jsx` | 11 |
| `AIAssistantChat` | `frontend/src/components/AIAssistantChat.jsx` | 12 |

### 5.2 Component States

Each component covers four states: loading, empty, error, and success.

| Component | Loading | Empty | Error | Success |
|-----------|---------|-------|-------|---------|
| GenerateIdeasModal | Spinner + input disabled | — (modal) | Inline error banner | Animated checkmark → auto-close |
| GenerationProgress | Progress bar + estimated time | — | Red failure + "Try Again" | Fade-in reveal of content |
| ScriptGenerator | Skeleton loader | "No script yet. Generate one." | Error card with retry | Formatted script + copy button |
| CaptionGenerator | Pulse animation | "No captions yet." | Platform-specific error | Caption cards + copy + icons |
| ContentPlanner | Ghost slots | "Nothing scheduled." + CTA | Conflict modal with slots | Toast + calendar refresh |
| CalendarView | Skeleton grid | Empty week + illustration | "Couldn't load. Retry?" | Interactive calendar |
| SaveIdeaModal | Disabled button | "No collections. Create one." | Inline error | "Saved to [collection]" + dismiss |
| MoreOptionsMenu | Disabled during gen | — | Per-action tooltip | Subtle animation |

### 5.3 State Management

```javascript
// TrendRecommendations.jsx state additions
const [showGenerateModal, setShowGenerateModal] = useState(false)
const [generationJob, setGenerationJob] = useState(null)
const [showScriptGenerator, setShowScriptGenerator] = useState(null)
const [showCaptionGenerator, setShowCaptionGenerator] = useState(null)
const [showScheduler, setShowScheduler] = useState(null)
const [savedIdeas, setSavedIdeas] = useState([])
const [collections, setCollections] = useState([])
const [showCollections, setShowCollections] = useState(false)
const [assistantMessages, setAssistantMessages] = useState([])
```

---

## 6. Compounding Error Mitigation

**Problem:** Bad idea → bad script → bad caption → wasted generation credits.

**Solutions:**

1. **Independent steps.** Generating a script does not auto-generate captions. User reviews and approves each stage.
2. **No cascading regeneration.** Regenerating a script does not affect existing captions (they're tied to the previous script version via `script_id`).
3. **Targeted improvement.** The `aspect` parameter in `/ideas/{id}/improve` ensures only the specified field changes.
4. **Variations are separate.** The `variations` JSONB field holds alternatives without mutating the primary idea. Users browse and promote one via `POST /ideas/{id}/promote-variation`.
5. **Regenerate is full replacement.** `POST /ideas/{id}/regenerate` creates a new idea from scratch — does not cascade to existing scripts/captions.

---

## 7. Error States & UX

Every AI generation endpoint standardizes on these error codes:

| Status | Meaning | Frontend UX |
|--------|---------|-------------|
| `202 Accepted` | Generation started | Show progress bar with `job_id` for polling |
| `200 OK` (status: complete) | Generation finished | Render the result |
| `200 OK` (status: processing) | Still generating | Update progress bar, poll every 2s |
| `200 OK` (status: failed, error: content_policy) | Content filtered | "This content didn't pass guidelines. Try a different topic or tone." |
| `200 OK` (status: failed, error: empty_result) | No results | "No ideas generated. Try broadening or rephrasing." |
| `504 Gateway Timeout` | AI took >60s | "Taking longer than expected. We'll notify you." → push to background |
| `429 Too Many Requests` | Rate limit hit | "Generation limit reached. Resets in X seconds." → countdown timer |
| `200 OK` with empty data | No matching results | "No ideas match these filters. Try broadening your search." |

**Empty state messaging:**
- Ideas list empty: "No ideas yet. Generate your first batch." with CTA
- Calendar empty: "Nothing scheduled this week. Browse ideas and plan some content."
- Collection empty: "This collection is empty. Save ideas from the ideas list."

---

## 8. Rate Limiting Strategy

### AI Generation Endpoints

Applies to: `/generate-ideas`, `/generate-script`, `/generate-caption`, `/ideas/{id}/improve`, `/ideas/{id}/variations`, `/ideas/{id}/regenerate`

| Tier | Limit | Window |
|------|-------|--------|
| Free | 10 requests | per hour |
| Pro | 20 requests | per hour |
| Enterprise | 50 requests | per hour |

**Response headers on all AI generation endpoints:**
```
X-RateLimit-Limit: 20
X-RateLimit-Remaining: 14
X-RateLimit-Reset: 2026-01-20T15:30:00Z
```

**Status polling endpoints (`GET .../status`) are NOT rate limited.**

### Standard REST Endpoints

Applies to: collections, planner, ideas list

| Limit | Window |
|-------|--------|
| 100 requests | per minute per user |

### Frontend Safeguards

- **2-second debounce** on improve/variations/regenerate buttons to prevent accidental double-clicks counting against quota
- **Countdown timer** displayed when rate limit is hit
- **Quota indicator** in settings/profile showing remaining generations

---

## 9. LLM Prompt Structure Guidelines

Generation pipeline uses a **chained-context approach**:

| Step | Input Context | Output | JSON Mode |
|------|--------------|--------|-----------|
| Generate Ideas | topic + tone + platform | hooks + descriptions + scores | Yes |
| Generate Script | idea hook + description + duration + style | structured script | Yes |
| Generate Caption | script summary + platform + hashtag prefs | platform captions | Yes |
| Improve | existing content + feedback + target aspect | refined version (target field only) | Yes |
| Variations | existing hook + description + count | N alternative hooks/angles | Yes |

**Key principle:** Each step receives context from prior steps for coherence, but the user can override or regenerate any step independently without forcing cascading regeneration.

---

## 10. Execution Order (Revised — 5 Phases)

The async job infrastructure is the critical path. Build it once, reuse it everywhere.

### Phase 1: Foundation

| Step | Description | Files |
|------|-------------|-------|
| 1 | Database migrations — `ideas`, `collections`, `collection_ideas`, `scheduled_items`, `idea_generation_jobs` | `alembic/versions/` |
| 2 | Background job queue setup (Celery, BullMQ, or equivalent) | `backend/app/services/job_queue.py` |
| 3 | `POST /generate-ideas` + `GET /generate-ideas/{job}/status` | `idea_generation.py`, `trend_routes.py` |
| 4 | `GET /trends/ideas` with pagination, sorting, filtering | `trend_routes.py` |

### Phase 2: Idea Refinement

| Step | Description | Files |
|------|-------------|-------|
| 5 | `POST /ideas/{id}/improve` + `POST /ideas/{id}/variations` + `POST /ideas/{id}/regenerate` | `idea_generation.py` |
| 6 | `GenerateIdeasModal` + `GenerationProgress` frontend components | `frontend/src/components/` |

### Phase 3: Script & Caption

| Step | Description | Files |
|------|-------------|-------|
| 7 | `POST /generate-script` (reuses job queue) | `script_generator.py`, `script_routes.py` |
| 8 | `POST /generate-caption` (reuses job queue) | `caption_generator.py`, `caption_routes.py` |
| 9 | `ScriptGenerator` + `CaptionGenerator` frontend | `frontend/src/components/` |

### Phase 4: Organization

| Step | Description | Files |
|------|-------------|-------|
| 10 | Collections: `POST/DELETE /collections/{id}/ideas`, `GET /ideas/{id}/collections` | `idea_collections.py`, `collection_routes.py` |
| 11 | Planner: `POST /planner/schedule`, `GET /planner?week_start=`, `DELETE /planner/schedule/{id}` | `content_planner.py`, `planner_routes.py` |
| 12 | `SaveIdeaModal` + `CalendarView` + `ContentPlanner` + `MoreOptionsMenu` + Enhanced `SuggestionCard` | `frontend/src/components/` |

### Phase 5: Polish

| Step | Description |
|------|-------------|
| 13 | Error state handling across all components |
| 14 | Rate limit UX (countdown timers, quota display, debounced buttons) |
| 15 | Empty state designs for all views |
| 16 | End-to-end integration testing: generate → improve → script → caption → schedule → collection |

---

## 11. LLM Cost Estimate

| Operation | Tokens (est.) | Calls per job | Cost per 1K tokens |
|-----------|---------------|---------------|-------------------|
| Idea generation (20 ideas) | 4,000 input + 6,000 output | 1 | $0.03 |
| Script generation | 1,500 input + 2,000 output | 1 | $0.01 |
| Caption generation | 1,000 input + 1,500 output | 1 | $0.008 |
| AI Assistant chat | 1,000 input + 1,000 output | 1 | $0.006 |
| Idea improvement | 1,000 input + 1,000 output | 1 | $0.006 |
| Variations (3) | 2,000 input + 3,000 output | 1 | $0.015 |

**Total per full user session (generate → script → caption → schedule):** ~$0.07

---

## 12. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Idea generation latency | <30s for 20 ideas |
| Script generation latency | <10s |
| Caption generation latency | <5s |
| Calendar load time | <500ms |
| Concurrent generation jobs | Max 1 per account |
| Backward compatibility | All existing API consumers unbroken |
| LLM cost control | Max 2 LLM calls per generation job |
| Pagination | 20 default, 50 max per page |
| Conflict detection window | 30 minutes same-platform |
