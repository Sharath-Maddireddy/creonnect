# PRD: Trend Recommendations — All 17 Screens

**Product**: Creonnect Creator Analytics  
**Feature**: Trend Recommendations (`/trends`)  
**Version**: 1.0  
**Status**: Ready for Engineering  
**Last Updated**: 2026-07-27

---

## Overview

This document specifies all 17 screens required for the Trend Recommendations feature. Each screen maps directly to the approved design mockup.

---

## Screen 1 — Suggestion Details (After Click)

### Purpose
A full-detail slide-over drawer that opens when a creator clicks on any idea card in the main feed. Shows the complete picture for one idea so the creator can decide their next action.

### Layout
- **Left column** (60%): Idea metadata
  - Thumbnail / format icon (large)
  - Momentum badge (🚀 Rising Potential)
  - Title (h2)
  - Tags row: content style + trend reference
  - Hook quote block (styled `"..."`)
  - Full description paragraph
  - Rationale section ("Why this idea?")
- **Right column** (40%): Scores & signals
  - Opportunity Score gauge (animated, 0–100)
  - Band label (Very High / High / Moderate)
  - Stats grid:
    - Expected Reach: `15K – 72K`
    - Engagement Rate: `3.6% – 5.6%`
    - Difficulty: `Easy`
    - Competition: `Low`
  - Suggested Hashtags chips (top 5)
  - Best Time to Post
  - Target Audience description
  - Content Type + Duration range
- **Bottom CTA bar**:
  - `Generate Script` (primary)
  - `Generate Caption` (ghost)
  - `Generate Thumbnail` (ghost)
  - `Save` (icon only)

### Interactions
- Opens as a slide-over from the right (300ms ease-out) — does not navigate away from feed
- Backdrop click closes the drawer
- ESC key closes
- "Back to Suggestions" arrow link at top-left closes
- All CTAs open the respective modal/component without closing drawer

### API
- `GET /api/v1/accounts/{account_id}/ideas/{idea_id}` — fetch full idea detail
- Fallback: use data already in card props if no DB-persisted idea ID

### States
- **Loading**: Skeleton shimmer for all fields
- **Error**: "Couldn't load idea details" with retry
- **No data**: Falls back to card props data

### Acceptance Criteria
- [ ] Drawer opens within 100ms of click
- [ ] All 4 action buttons functional
- [ ] Score gauge animates on open
- [ ] Mobile: full-screen modal instead of drawer

---

## Screen 2 — Script Generator

### Purpose
Full script editor with scene-by-scene timeline, tone controls, and AI improvement actions. Replaces the current basic text output.

### Layout
- **Header**: "← Back to Idea Details" | Idea title | `Save` button
- **Left panel** — Controls (30%):
  - Script type tabs: `Viral Script` / `Natural` / `Story`
  - Tone selector: Friendly / Professional / Funny / Educational / Luxury
  - Duration slider: 15s – 180s (shows: `32 sec`)
  - Language dropdown
  - Target Audience chip display
  - `Regenerate Script` button
  - `Copy Script` button
  - `Download .txt` button
- **Right panel** — Timeline editor (70%):
  - **HOOK** block: label + timestamp (`0:00 – 0:05`) + editable text area
  - **SCENE 1** block: label + timestamp + editable text area
  - **SCENE 2** block: label + timestamp + editable text area
  - **SCENE 3** block: label + timestamp + editable text area
  - **CTA** block: label + timestamp + editable text area
  - `+ Add Scene` button at bottom
  - Each block has a mini action row: `✨ AI Improve` | character count
- **Bottom improvement bar**:
  - `Improve Hook` | `Make More Educational` | `Shorter Script` | `Make It Funny`

### Interactions
- All text blocks are directly editable (contentEditable or textarea)
- "AI Improve" on a block: sends that block's text + tone to backend for improvement, replaces text with animation
- Bottom improvement buttons apply to full script
- Duration slider updates timestamp ranges in real-time
- Regenerate replaces full script with confirmation dialog
- Copy copies full formatted script to clipboard

### API
- `POST /api/v1/accounts/{account_id}/trends/generate-script` — generate initial script
- `POST /api/v1/accounts/{account_id}/ideas/{idea_id}/improve-script-block` — improve single scene block
- `POST /api/v1/accounts/{account_id}/ideas/{idea_id}/script/regenerate` — full regenerate

### States
- **Generating**: Skeleton timeline with pulsing animation + spinner
- **Error**: Inline error per block with retry icon
- **Saved**: Toast "Script saved ✓"

### Acceptance Criteria
- [ ] Each scene block is editable in-place
- [ ] Duration changes update all timestamps
- [ ] "Improve Hook" changes only the Hook block
- [ ] Full script copy includes all blocks formatted with timestamps
- [ ] Regenerate shows confirmation before overwriting

---

## Screen 3 — Caption Generator

### Purpose
Editable caption workspace with hashtag management, tone selector, platform switching, and multiple variants side-by-side.

### Layout
- **Header**: "← Back to Idea Details" | `Regenerate` button
- **Left panel** — Generated Caption (65%):
  - Caption score: animated gauge `88 / 100` + band label (e.g. "Great")
  - Platform tabs: Instagram / TikTok / LinkedIn
  - Editable caption textarea (styled, not plain `<textarea>`)
  - Hashtag chips row: each chip is removable (✕) + `+ Add` chip at end
  - Stats row: Words count | Characters count | Tone detected | Length badge
  - Action buttons: `Copy Caption` | `Copy Hashtags` | `Generate Variants (3)`
- **Right panel** — Controls (35%):
  - Tone selector: Friendly (active) / Professional / Luxury / Funny / Inspiring
  - Language dropdown
  - Max Hashtags slider (12/30 shown)
  - Include Hashtags toggle
  - Caption length: Short / Medium / Long toggle
  - Platform-specific tips card (scrollable)

### Interactions
- Caption text is directly editable — character count updates live
- Clicking a hashtag chip removes it; typing in `+ Add` adds a new one
- Switching platform tab adjusts character limit indicator and tip card
- `Generate Variants` opens a 3-column variant picker beneath the main caption
- Tone change triggers re-generation with confirmation if caption has been edited

### API
- `POST /api/v1/accounts/{account_id}/trends/generate-caption` — generate captions
- `POST /api/v1/accounts/{account_id}/ideas/{idea_id}/caption/variants` — get 3 variants

### States
- **Generating**: Full-area skeleton shimmer
- **Edited**: "Unsaved changes" dot on Save button
- **Copy success**: "Copied!" toast 2s then auto-dismiss

### Acceptance Criteria
- [ ] Caption textarea is fully editable
- [ ] Hashtag chips individually removable
- [ ] Character count updates on every keystroke
- [ ] Platform switch updates limit indicator
- [ ] Variants shown as selectable alternatives

---

## Screen 4 — Thumbnail Generator

### Purpose
Generates 4 thumbnail visual concept options the creator can select, download, or use as a creative brief.

### Layout
- **Header**: "← Back to Idea Details" | `Regenerate` button
- **Top**: "Choose your preferred thumbnail" instructional text
- **2×2 grid** of thumbnail concept cards:
  - Each card: visual preview image (AI-generated) + label text (e.g. "Option 1", "Option 2")
  - Labels shown: "BRIDAL TRIAL LOOK", "Before vs After Bridal Makeup", "My Bridal Makeup Trial", "The Final Look Reveal ✨"
  - Active selection: highlighted border (purple glow)
- **Bottom action bar**:
  - `Download` (ghost) — downloads selected thumbnail concept
  - `Download Prompt` (ghost) — downloads the AI image generation prompt
  - `Use This Thumbnail` (primary) — confirms selection and links to idea

### Interactions
- Click any thumbnail to select it (single-select)
- `Regenerate` replaces all 4 options
- `Download` downloads the selected image
- `Download Prompt` copies/downloads the text prompt that was used to create it

### API
- `POST /api/v1/accounts/{account_id}/ideas/{idea_id}/generate-thumbnails` — returns 4 concept objects with image URLs + prompts
- `GET` on each image URL streams the generated image

### States
- **Generating**: 4 skeleton cards with shimmer + "Generating thumbnails…" caption
- **Error**: "Couldn't generate thumbnails" with retry per card
- **None selected**: `Use This Thumbnail` button disabled

### Acceptance Criteria
- [ ] 4 options always shown (re-request if < 4 returned)
- [ ] Selection highlighted with visible border
- [ ] Download works for the selected option
- [ ] Regenerate replaces all 4 without confirmation

---

## Screen 5 — Save Idea (Collections Modal)

### Purpose
Allows creators to save an idea to one or more named collections (folders).

### Layout
- **Modal** (centred, 480px wide):
  - Header: "Save Idea" + close ✕
  - `🔍` Search collections input
  - Collection list (scrollable):
    - Each row: checkbox + collection icon + collection name + idea count badge
    - Collections shown: Favorites ⭐, Travel Ideas ✈️, Brand Collaboration Ideas 🤝, Next Month Ideas 📅, Educational Content 📚, Beauty Content 💄
    - Active collection highlighted in purple
  - `+ Create New Collection` button at top-right of header
  - **Bottom**: `Save Idea` primary button (full width)

### Interactions
- Multi-select: multiple collections can be checked simultaneously
- Search filters list in real-time
- `+ Create New Collection`: inline input appears in list for naming + confirm
- `Save Idea`: saves to all checked collections → success toast → modal closes

### API
- `GET /api/v1/accounts/{account_id}/collections` — list collections
- `POST /api/v1/accounts/{account_id}/collections` — create collection
- `POST /api/v1/accounts/{account_id}/ideas/{idea_id}/save` — save to collections

### States
- **Loading collections**: skeleton list rows
- **Empty (no collections)**: "Create your first collection" prompt
- **Saving**: spinner on button
- **Success**: "Saved to [n] collections ✓" toast

### Acceptance Criteria
- [ ] Multi-select works (multiple checkboxes)
- [ ] Search filters the list live
- [ ] New collection creates and auto-checks in same action
- [ ] Success toast auto-dismisses in 3s

---

## Screen 6 — Weekly Planner (Calendar + Drag-and-Drop)

### Purpose
7-day calendar view where the creator can see, add, and rearrange scheduled ideas. AI pre-fills an optimal week.

### Layout
- **Header row**:
  - "← Back to Planner" | month/year nav (`< May 2024 >`) | `Today` button
- **Left sidebar** — "Ideas to Plan" queue:
  - List of unscheduled idea cards (compact): title + content type icon
  - Drag handle on each
- **Main calendar** — 7 columns (Mon–Sun):
  - Day header: day abbreviation + date number
  - Time slots (implicit, not shown as rows)
  - Scheduled idea chips inside date cells: colour-coded by platform (🔴 Reel, 🔵 Carousel, 📸 Photo, 🟢 Story)
  - `+ Add Idea` button at bottom of each column
- **Top-right**: `Generate Optimal Week` CTA button (purple/primary)

### Interactions
- Drag ideas from sidebar → drop onto a date column
- Drag existing chips between columns to reschedule
- Click a chip → opens ContentPlanner modal for editing
- `+ Add Idea` → opens idea picker drawer
- `Generate Optimal Week` → AI fills in the 7 days → shows confirmation before applying
- Week nav arrows scroll forward/backward by 7 days

### API
- `GET /api/v1/accounts/{account_id}/planner/calendar?week_start=2024-05-06` — get scheduled items
- `POST /api/v1/accounts/{account_id}/planner/schedule` — schedule an idea
- `PATCH /api/v1/accounts/{account_id}/planner/{schedule_id}` — move/reschedule
- `DELETE /api/v1/accounts/{account_id}/planner/{schedule_id}` — remove from calendar
- `POST /api/v1/accounts/{account_id}/trends/weekly-plan` — AI-generate optimal week

### States
- **Empty day**: dashed `+ Add Idea` placeholder
- **Conflict**: chip highlighted in orange
- **Generating plan**: shimmer over all 7 columns + "AI is planning your week…"

### Acceptance Criteria
- [ ] Drag-and-drop works within and between columns
- [ ] Dropped idea shows immediately (optimistic update)
- [ ] Conflict highlighted without blocking the action
- [ ] `Generate Optimal Week` requires confirmation before overwriting existing slots
- [ ] Week navigation persists scroll position

---

## Screen 7 — View All Trending Topics

### Purpose
Full dedicated view of all trending topics with rich metadata, filtering, and audience match scoring.

### Layout
- **Header**: "Trending Topics" + filter bar: `All Categories ▾` | `Sort by: Trending ▾`
- **Table / List** of topics:
  - Rank number (#1, #2…)
  - Thumbnail icon (gradient chip with emoji)
  - Topic name (bold)
  - Niche/category tag
  - Sparkline chart (7-day trend)
  - Momentum badge: `+320%` / `+260%` in green
  - Audience Match % tag
  - `Use This Topic →` button (right-aligned)
- **Pagination**: `Load More Topics` at bottom

### Interactions
- Clicking a topic row expands an inline detail panel (accordion) showing: description, why it's trending, sample posts using this topic
- `Use This Topic →` pre-fills the Generate Ideas modal with this topic
- Category filter and sort are independent
- Sparkline is interactive on hover (tooltip shows data point)

### API
- `GET /api/v1/accounts/{account_id}/trends?limit=20&offset=0` — paginated list
- Filter params: `category`, `sort_by` (`trending|audience_match|momentum`)

### States
- **Loading**: skeleton rows (5 rows)
- **Empty**: "No trends found for this category"
- **Error**: inline error with retry

### Acceptance Criteria
- [ ] All topics paginate with "Load More"
- [ ] Category + sort filters work independently
- [ ] `Use This Topic →` passes topic to Generate Ideas modal
- [ ] Sparklines render for each topic

---

## Screen 8 — View All Suggestions

### Purpose
Full paginated list of all AI suggestions with multi-sort, multi-filter, and bulk actions.

### Layout
- **Header**: "All Suggestions" + filter bar:
  - `All Types ▾` | `All Stories ▾` | `All Time ▾` | `Sort by: Opportunity ▾`
- **Suggestion list**: each row is a compact card:
  - Rank number
  - Thumbnail icon + platform icons
  - Title + tags (Storytelling, Brand, etc.)
  - Opportunity score `75 /100` + band label `High` + difficulty `Moderate`
  - Right-side: `Generate Script` | `Save` icon
- **Pagination**: `Load More Suggestions` at bottom

### Interactions
- Click a row title → opens Suggestion Details drawer (Screen 1)
- Click `Generate Script` → opens Script Generator modal
- Filter dropdowns: Type (Reel/Carousel/Photo/Story) | Platform | Time window | Sort
- Bulk select mode: checkbox appears on hover, "Select All" in header

### API
- `GET /api/v1/accounts/{account_id}/ideas?type=&sort_by=opportunity&limit=10&offset=0`

### States
- **Loading**: skeleton rows
- **Empty per filter**: "No [Type] ideas — try a different filter"

### Acceptance Criteria
- [ ] All 4 filter dropdowns functional and combinable
- [ ] Sort updates list without page reload
- [ ] Compact card shows all 5 data points
- [ ] Bulk select shows action bar at bottom of screen

---

## Screen 9 — Niche Details (Right Panel Expanded)

### Purpose
Expanded view of the creator's detected niche, audience profile, and confidence breakdown.

### Layout
- **Panel header**: "Niche Detected"
- **Primary niche**: large category name (e.g. "Food & Cooking")
- **Sub-niche tags**: pill tags (Home & decor, Self care, 2x+, Productivity)
- **Confidence bar**: "Confidence 93%" with progress bar
- **Why this niche?** section:
  - 2–3 sentence AI explanation of how the niche was detected
  - "You follow trends with lifestyle content. You have strong consistent trends on daily routines, self care…"
- **Content Style Score** row (implied from mockup)

### Interactions
- Expanding from the right panel card's "View Details" link
- Shows as a right-panel expansion (push layout) or modal
- "Refresh Niche Analysis" button at bottom

### API
- `GET /api/v1/accounts/{account_id}/niche` — returns niche object with all fields including `explanation`

### States
- **Loading**: skeleton text blocks
- **Low confidence** (< 50%): warning banner "Not enough posts to detect niche reliably"

### Acceptance Criteria
- [ ] Confidence % animated on mount
- [ ] Sub-niche tags are scrollable if > 5
- [ ] AI explanation paragraph present
- [ ] "Refresh" triggers a new niche analysis

---

## Screen 10 — AI Reasoning (Why This Score?)

### Purpose
Transparent breakdown of exactly how the AI computed the opportunity score for a given idea.

### Layout
- **Modal** (560px wide):
  - Header: "Why This Score?" + score gauge `75 / 100 High`
  - Subtitle: "Top 25% Ideas"
  - **Contributing Factors** list (each with label + score bar + value):
    - Niche Relevance: `82/100`
    - Competitive Score: `70/100`
    - Audience Match: `95/100`
    - Post Performance: `66/100`
    - Best Timing: `64/100`
  - **AI Confidence** bar at bottom: `89%` + label "Perfect timing for this content"

### Interactions
- Opened from "Why this score?" link/button on idea card or Suggestion Details
- Each factor bar animates from 0 on modal open (stagger 50ms apart)
- Hovering a factor shows tooltip with 1-sentence explanation

### API
- `GET /api/v1/accounts/{account_id}/ideas/{idea_id}/reasoning` — returns factor breakdown
- Or embedded in the idea detail response as a `reasoning` object

### States
- **Loading**: skeleton bars
- **No reasoning available**: "Score computed deterministically — detailed reasoning not available for this idea"

### Acceptance Criteria
- [ ] All factor bars animate in with stagger
- [ ] Tooltips show on hover
- [ ] Total score matches what's shown on the card
- [ ] AI confidence % shown at bottom

---

## Screen 11 — Idea Variations

### Purpose
5 angle-specific variations of the same idea so creators can pick the tone that matches their brand.

### Layout
- **Modal** (large, 900px):
  - Header: "Script Variations" + subtitle "Explore different angles" + close ✕
  - **Horizontal tab row**: Storytelling (active) | Funny | Luxury | Educational | Minimal
  - **5-column card grid** (all 5 visible simultaneously, or tabs on mobile):
    - Each column: variation type label + short preview of the hook text
    - Active tab card: highlighted with purple border
  - **Bottom CTA**: `Generate More Variations` (ghost) | `Use This Variation →` (primary)

### Interactions
- Tab click highlights that variation and moves `Use This Variation →` to act on it
- Cards can be scrolled horizontally on mobile
- `Generate More Variations` adds 5 more tabs (max 10)
- `Use This Variation →` replaces the parent idea card with this variation's content

### API
- `POST /api/v1/accounts/{account_id}/ideas/{idea_id}/variations` — body: `{ count: 5, styles: ["storytelling","funny","luxury","educational","minimal"] }`
- Response: array of variation objects with `style`, `title`, `hook`, `description`

### States
- **Loading**: 5 skeleton cards with shimmer
- **Error**: "Couldn't generate variations" with retry
- **Applied**: parent card updates with animation + toast "Variation applied ✓"

### Acceptance Criteria
- [ ] All 5 variations shown simultaneously (desktop)
- [ ] Tab selection highlights that column
- [ ] `Use This Variation →` updates the parent card
- [ ] Mobile: tabs with single-card view

---

## Screen 12 — Publish / Schedule

### Purpose
Multi-platform scheduling interface where creators confirm publish time, platform, and settings before adding to calendar.

### Layout
- **Modal** or right-panel drawer:
  - **Platform section** — platform pills with checkboxes:
    - `📸 Instagram` ✅ checked + "Publish Now" sub-option
    - `🎵 TikTok` ✅ checked + "Publish Later" sub-option
    - `▶️ YouTube Shorts` ✅ checked + "Shorts"
    - `📘 Facebook` unchecked
  - **Date/Time picker** (shows: `May 3, 2024 / 06:30 PM`)
  - **Save as Draft** toggle
  - `Schedule Post` primary button (full width, purple)

### Interactions
- Checking/unchecking a platform adds/removes from the scheduled batch
- "Publish Now" radio vs. "Publish Later" toggles the date/time picker visibility
- Date picker: calendar popup on click
- Time picker: dropdowns or scrollable time selector
- `Save as Draft`: schedules but marks as draft (no auto-publish)
- `Schedule Post`: confirms all, closes modal, shows calendar with new items

### API
- `POST /api/v1/accounts/{account_id}/planner/schedule` — body: `{ idea_id, platforms: [], scheduled_at, save_as_draft }`
- Extend ContentPlanner with YouTube + Facebook platforms

### States
- **No platform selected**: `Schedule Post` disabled with tooltip "Select at least one platform"
- **Scheduling**: spinner on button
- **Success**: drawer closes + toast "Scheduled for May 3 at 6:30 PM"
- **Conflict**: warning banner with conflict details (existing post at same time)

### Acceptance Criteria
- [ ] YouTube Shorts + Facebook added as platform options
- [ ] At least 1 platform required to enable schedule
- [ ] "Publish Now" skips date/time picker
- [ ] Success triggers calendar refresh

---

## Screen 13 — History & Activity

### Purpose
Chronological log of all AI-generated scripts, captions, and scheduled posts for the creator.

### Layout
- **Header**: "History & Activity"
- **Filter tabs**: All | Generated | Scheduled | Published
- **Activity list** (each row):
  - Thumbnail icon (gradient)
  - Title (bold) — e.g. "My Bridal Makeup Trial Real Time"
  - Sub-label: action + timestamp — e.g. "Generated Script • Today, 10:35 AM"
  - Status chip (right): `Completed` (green) | `Scheduled` (blue) | `Failed` (red)
- Empty state (when no history)

### Interactions
- Click a row → opens Suggestion Details for that idea
- Filter tabs filter the list type
- "Scheduled" items show countdown: "In 2 days"
- "Failed" items show retry button inline

### API
- `GET /api/v1/accounts/{account_id}/activity?type=all&limit=20&offset=0`
- Response: `[{ idea_id, action, title, status, created_at, scheduled_at? }]`

### States
- **Loading**: 5 skeleton rows
- **Empty (all)**: illustration + "No activity yet — generate your first idea"
- **Empty (filtered)**: "No [type] items"

### Acceptance Criteria
- [ ] All 4 filter tabs functional
- [ ] Status chips colour-coded correctly
- [ ] Failed items have inline retry
- [ ] Timestamps shown as relative ("Today, 10:35 AM") with absolute on hover

---

## Screen 14 — Empty State

### Purpose
First-load state when no suggestions have been generated yet (new account or cleared data).

### Layout
- **Centered vertical layout** (full main content area):
  - Illustrated icon (rocket or sparkles — purple gradient)
  - Heading: "No suggestions yet!"
  - Sub-text: "Generate personalised content ideas based on your niche and audience"
  - `Generate New Ideas ✨` primary button (centered, purple)

### Interactions
- `Generate New Ideas →` opens the Generate Ideas modal
- Entire area is non-interactive otherwise

### States
- This IS the state — no sub-states

### Acceptance Criteria
- [ ] Shown when `data === null && !loading && !error`
- [ ] Button opens Generate Ideas modal
- [ ] Illustration is custom (not a generic icon)

---

## Screen 15 — Loading State

### Purpose
Progress-aware loading screen shown while AI is generating ideas (can take 1–3 minutes with reasoning model).

### Layout
- **Full-area overlay** (covers main content, not modal):
  - Top: "Generating ideas for you..." heading
  - Animated step list with status icons:
    - ✅ `Analysing your audience`
    - ✅ `Finding trending topics`
    - ⏳ `Scanning competitor content` (active — pulsing)
    - ○ `Creating content ideas` (pending)
    - ○ `Ranking by opportunity` (pending)
  - Footer: "This may take a few seconds..." (update to "1–3 minutes" for reasoning model)

### Interactions
- Steps update in real-time via polling (`GET .../generate-ideas/{job_id}/status`)
- Current step pulses with animated ring
- Completed steps show green checkmark
- No user actions available during loading

### States
- Steps advance as backend reports `current_step` and `step_label`
- If polling fails: shows retry button after 30s of no update

### Acceptance Criteria
- [ ] Steps update from backend `current_step` field (not faked)
- [ ] Active step has visible pulse animation
- [ ] Completed steps show ✅ immediately
- [ ] Timeout after 6 minutes shows error state

---

## Screen 16 — Error State

### Purpose
Shown when idea generation, trend fetching, or any major action fails.

### Layout
- **Centered card** (not full-page):
  - Warning triangle icon (animated shake on appear)
  - Heading: "Oops! Something went wrong."
  - Sub-text: "We couldn't generate ideas right now. Please try again."
  - Two buttons: `Try Again` (primary) | `Go Back` (ghost)

### Interactions
- `Try Again` retries the last failed operation
- `Go Back` returns to the main feed (previous state)
- Error details shown in expandable "Show details" section (collapsed by default)

### States
- This IS the error state
- Show details section: shows raw error message (for debugging)

### Acceptance Criteria
- [ ] `Try Again` re-runs exact same request that failed
- [ ] `Go Back` restores previous feed state without refetch
- [ ] Error message in "Show details" is human-readable (not a raw stack trace)
- [ ] Icon has brief shake animation on mount

---

## Screen 17 — Notifications (In-App)

### Purpose
In-app notification bell feed showing alerts for completed AI jobs, new trends, and scheduled post reminders.

### Layout
- **Right-side panel** (slide-in from top-right or dropdown from bell icon):
  - Header: "Notifications" + "Mark all as read" link
  - Notification list (each row):
    - Icon (based on type)
    - Title (bold): e.g. "Weekly plan is ready"
    - Sub-text: e.g. "Tap to view your plan in calendar"
    - Timestamp (relative): "2m ago"
    - Unread dot (blue) on left edge
  - Notification types shown:
    - 📅 "Weekly plan is ready — Tap to view your plan in calendar" (2m ago)
    - 🔥 "3 new trending topics detected" (15m ago)
    - 📈 "Your post performed 15% better than predicted" (30m ago)
    - ✅ "Idea scheduled for tomorrow, 6:30 PM" (30m ago)
  - `View All Notifications →` link at bottom

### Interactions
- Bell icon in top-right of page header shows unread badge count
- Clicking a notification marks as read + navigates to relevant section
- "Mark all as read" clears all unread dots
- Clicking outside closes the panel

### API
- `GET /api/v1/accounts/{account_id}/notifications?limit=10`
- `PATCH /api/v1/accounts/{account_id}/notifications/read-all`
- `PATCH /api/v1/accounts/{account_id}/notifications/{id}/read`

### Notification Types
| Type | Trigger | Action on click |
|---|---|---|
| `weekly_plan_ready` | Weekly plan generation completes | Open Weekly Planner |
| `trends_detected` | New trends fetched | Open View All Trends |
| `post_performance` | Post outperforms prediction | Open that post in Analytics |
| `idea_scheduled` | Idea added to calendar | Open Calendar |
| `generation_complete` | Idea generation job finishes | Open generated ideas section |

### States
- **No notifications**: "You're all caught up 🎉"
- **Loading**: 4 skeleton rows

### Acceptance Criteria
- [ ] Bell badge count matches unread notification count
- [ ] Clicking a notification marks it read + navigates correctly
- [ ] "Mark all as read" zeroes the badge
- [ ] Panel closes on outside click

---

## Component & File Plan

| Screen | New File(s) Needed | Modifies |
|---|---|---|
| 1 — Suggestion Details | `IdeaDetailDrawer.jsx` | `TrendRecommendations.jsx` |
| 2 — Script Generator | Extend `ScriptGenerator.jsx` | — |
| 3 — Caption Generator | Extend `CaptionGenerator.jsx` | — |
| 4 — Thumbnail Generator | `ThumbnailGenerator.jsx` | `TrendRecommendations.jsx` |
| 5 — Save Idea | Extend `SaveIdeaModal.jsx` | — |
| 6 — Weekly Planner | `WeeklyPlanner.jsx` | `CalendarView.jsx`, `ContentPlanner.jsx` |
| 7 — View All Trending | `AllTrendingTopics.jsx` | `TrendRecommendations.jsx` |
| 8 — View All Suggestions | `AllSuggestions.jsx` | `TrendRecommendations.jsx` |
| 9 — Niche Details | `NicheDetailPanel.jsx` | `TrendRecommendations.jsx` |
| 10 — AI Reasoning | `AIReasoningModal.jsx` | `SuggestionCard` in `TrendRecommendations.jsx` |
| 11 — Idea Variations | Extend `MoreOptionsMenu.jsx` → `IdeaVariationsModal.jsx` | `TrendRecommendations.jsx` |
| 12 — Publish/Schedule | Extend `ContentPlanner.jsx` | — |
| 13 — History & Activity | `HistoryActivity.jsx` | `TrendRecommendations.jsx` |
| 14 — Empty State | Inline in `TrendRecommendations.jsx` | `TrendRecommendations.jsx` |
| 15 — Loading State | Extend `GenerationProgress.jsx` | — |
| 16 — Error State | `ErrorState.jsx` (shared) | `TrendRecommendations.jsx` |
| 17 — Notifications | `NotificationsPanel.jsx` | Top-level layout / header |

---

## Build Phases

### Phase 1 — Core User Loop (Week 1–2)
1. Screen 6 — Weekly Planner
2. Screen 1 — Suggestion Details Drawer
3. Screen 10 — AI Reasoning

### Phase 2 — AI Generation Polish (Week 2–3)
4. Screen 2 — Script Generator (timeline + improvements)
5. Screen 3 — Caption Generator (inline edit + hashtag chips)
6. Screen 11 — Idea Variations
7. Screen 15 — Loading State (real step tracking)

### Phase 3 — Discovery & Management (Week 3–4)
8. Screen 4 — Thumbnail Generator
9. Screen 7 — View All Trending Topics
10. Screen 12 — Publish/Schedule (add YouTube)
11. Screen 13 — History & Activity

### Phase 4 — Polish & Notifications (Week 4–5)
12. Screen 5 — Save Idea (polish)
13. Screen 8 — View All Suggestions
14. Screen 9 — Niche Details
15. Screen 17 — Notifications
16. Screen 14 — Empty State (illustrated)
17. Screen 16 — Error State (animated)
