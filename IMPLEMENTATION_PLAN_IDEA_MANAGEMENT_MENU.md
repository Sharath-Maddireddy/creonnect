# Implementation Plan: Idea Management Menu Completion

**Status:** Draft  
**Primary PRD:** `PRD_IDEA_MANAGEMENT_MENU_COMPLETION.md`

---

## 1. Delivery Order

1. Secure and normalize backend contracts.
2. Wire synchronous mutations: duplicate, type change, hide, delete.
3. Add shared async job feedback for improve, variations, and regenerate.
4. Refresh local UI state after every action.
5. Add backend and frontend tests.

## 2. Backend Work

### 2.1 Secure Duplicate

Files: `backend/app/api/content_suggestion_routes.py`, backend route tests

- [ ] Filter duplicate source lookup by both `Idea.id` and `Idea.account_id`.
- [ ] Copy relevant generation metadata and return a complete idea summary.
- [ ] Test that one account cannot duplicate another account's idea.

### 2.2 Validate Updates

Files: `backend/app/domain/content_suggestion_models.py`, `backend/app/api/content_suggestion_routes.py`

- [ ] Replace the untyped PATCH payload with an `UpdateIdeaRequest` model.
- [ ] Permit content types only: `reel`, `carousel`, `photo`.
- [ ] Permit statuses only: `draft`, `generated`, `scheduled`, `hidden`.
- [ ] Reserve `deleted` for the DELETE endpoint.
- [ ] Return updated values for immediate UI state updates.

### 2.3 Hide and Delete

- [ ] Implement hide through PATCH with `status: hidden`.
- [ ] Exclude `hidden` and `deleted` ideas from active list queries.
- [ ] Preserve DELETE as soft delete.
- [ ] Reject hidden/deleted ideas from script, caption, schedule, improve, variation, and regenerate actions.

### 2.4 Async Job Status

Files: `backend/app/services/content_suggestion_jobs.py`, `backend/app/api/content_suggestion_routes.py`

- [ ] Provide one status endpoint for improve, variation, and regenerate jobs.
- [ ] Return `queued`, `processing`, `completed`, or `failed` plus result/error payloads.
- [ ] Include resulting idea or variation IDs on success.
- [ ] Confirm the RQ worker consumes `content-suggestions` in local and deployment environments.

## 3. Frontend Work

### 3.1 Menu UX

Files: `frontend/src/components/MoreOptionsMenu.jsx`, `frontend/src/pages/TrendRecommendations.jsx`

- [ ] Add action-specific loading labels.
- [ ] Add a reusable delete confirmation dialog.
- [ ] Add a content-type picker.
- [ ] Add success/error toast or inline notices.
- [ ] Prevent menu/action clicks from triggering card-detail navigation.

### 3.2 Wire Actions

- [ ] `duplicate`: call POST; refresh or append new idea.
- [ ] `improve`: start job; poll; refresh idea on completion.
- [ ] `variations`: start job; poll; show variants.
- [ ] `regenerate`: start job; poll; refresh in place.
- [ ] `type`: open picker; PATCH type; update card label.
- [ ] `schedule`: retain existing planner handoff with persisted title.
- [ ] `hide`: PATCH status; remove card; offer Undo.
- [ ] `delete`: confirm; DELETE; remove card after `204`.

### 3.3 Shared Helpers

- [ ] Create `mutateIdea()` for PATCH and DELETE handling.
- [ ] Create cancellable `pollIdeaJob()` with timeout, success, and failure handling.
- [ ] Continue using `ensureIdeaForRecommendation()` before menu actions.
- [ ] Refetch persisted data after mutations to prevent stale quick-idea mappings.

## 4. Tests

### Backend

- [ ] Duplicate is account-scoped and creates a new row.
- [ ] PATCH rejects invalid content types/statuses.
- [ ] Hide excludes active listings.
- [ ] Delete soft-deletes and blocks downstream generation.
- [ ] Job-status endpoint reports every terminal state.

### Frontend

- [ ] Each menu action calls the expected endpoint.
- [ ] Delete requires confirmation.
- [ ] Hide removes a card and Undo restores it.
- [ ] Change type updates the displayed label.
- [ ] Async actions show processing, success, and failure states.

## 5. Manual QA

- [ ] Start backend, Redis, RQ worker, and Vite frontend.
- [ ] Exercise all eight actions on a persisted idea.
- [ ] Verify no management request uses a `trend-*` ID.
- [ ] Refresh after every mutation and verify stored state.
- [ ] Test desktop, mobile, failed network, and failed job cases.

## 6. Rollout

- [ ] Ship backend contracts before exposing the additional frontend actions.
- [ ] Feature-flag the completed menu if trend recommendations are disabled.
- [ ] Emit events for duplicate, hidden, deleted, type changed, and job outcomes.
- [ ] Monitor queue failures and action error rates after release.

