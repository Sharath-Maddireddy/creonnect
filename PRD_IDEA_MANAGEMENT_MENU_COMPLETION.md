# PRD: Idea Management Menu Completion

**Status:** Draft  
**Last Updated:** 2026-07-29  
**Surface:** Content Suggestions -> Recommended Content Angles -> More Options

---

## 1. Problem

The More Options menu presents eight creator actions, but only Improve, Generate Variations, Regenerate, and Schedule are wired from the UI. Duplicate, Change Content Type, Hide, and Delete appear actionable without completing a backend request. Queue-backed actions also close immediately without showing their resulting state.

## 2. Goal

Every visible menu action must either perform a durable, account-scoped backend mutation or be removed from the menu.

## 3. User Stories

- As a creator, I can duplicate an idea and receive a separate editable draft.
- As a creator, I can change an idea between Reel, Carousel, and Photo without losing its content.
- As a creator, I can hide an idea from recommendations without deleting it.
- As a creator, I can delete an idea and no longer see it in active lists.
- As a creator, I can improve, regenerate, or create variations and see job progress and the final result.
- As a creator, I receive confirmation or an actionable error for every menu action.

## 4. Scope

| Action | Expected behavior | Durable data |
|---|---|---|
| Duplicate Idea | Creates an account-scoped draft copied from the source idea. | New `ideas` row with `parent_idea_id` |
| Improve This Idea | Starts AI improvement and refreshes the affected idea when complete. | Existing idea plus job/result state |
| Generate Variations | Starts AI variation generation and presents generated variants. | `ideas.variations` plus job/result state |
| Regenerate | Starts AI regeneration and refreshes the affected idea when complete. | Existing idea plus job/result state |
| Change Content Type | Lets creator choose `reel`, `carousel`, or `photo`; persists selection. | `ideas.content_type` |
| Schedule for Later | Opens existing planner and persists a scheduled item. | `scheduled_items` row |
| Hide This Idea | Removes it from active suggestion views, with an undo option. | `ideas.status = hidden` |
| Delete Idea | Requires confirmation and soft-deletes the idea. | `ideas.status = deleted` |

### Out of Scope

- Publishing to Instagram or other platforms.
- Restoring deleted ideas after a retention window.
- Bulk management actions.
- Editing an idea's title, hook, or description from this menu.

## 5. Functional Requirements

### 5.1 Preconditions

- Every action operates only on a persisted idea ID, never a synthetic `trend-*` display ID.
- The idea must belong to the current `account_id`.
- Hidden and deleted ideas are excluded from normal active idea listings.

### 5.2 Feedback

- Duplicate, change type, hide, and delete show a success message and refresh the current list.
- Delete uses a confirmation dialog with a destructive primary action.
- Hide offers Undo for 10 seconds; Undo restores `draft`.
- Async actions retain visible progress until the job succeeds or fails.
- Failures display a retryable error.

### 5.3 State Rules

| Status | Active suggestions | Saved/history views |
|---|---:|---:|
| `draft` / `generated` / `scheduled` | Yes | Yes |
| `hidden` | No | Yes, hidden filter only |
| `deleted` | No | No, except admin/audit tooling |

### 5.4 Content Type Change

- Supported values: `reel`, `carousel`, `photo`.
- The chooser preselects the current value.
- The backend validates allowed values and rejects arbitrary strings.
- Existing scripts/captions remain stored but are labeled as generated for the previous type until regenerated.

## 6. API Contract

| Action | Method and path | Required work |
|---|---|---|
| Duplicate | `POST /api/v1/accounts/{account_id}/ideas/{idea_id}/duplicate` | Wire frontend; enforce source account scope |
| Improve | `POST /api/v1/accounts/{account_id}/ideas/{idea_id}/improve` | Wire job polling and result refresh |
| Variations | `POST /api/v1/accounts/{account_id}/ideas/{idea_id}/variations` | Wire job polling and result display |
| Regenerate | `POST /api/v1/accounts/{account_id}/ideas/{idea_id}/regenerate` | Wire job polling and result refresh |
| Change type / hide / undo | `PATCH /api/v1/accounts/{account_id}/ideas/{idea_id}` | Add validated request model |
| Delete | `DELETE /api/v1/accounts/{account_id}/ideas/{idea_id}` | Wire confirmation and removal |
| Schedule | `POST /api/v1/accounts/{account_id}/planner/schedule` | Existing planner integration |

## 7. Success Metrics

- 100% of visible More Options actions make a verified frontend-to-backend request.
- No synthetic trend IDs reach idea-management APIs.
- At least 95% of successful action responses update the UI without a full page reload.
- All destructive actions require explicit confirmation.

## 8. Acceptance Criteria

- Each action has loading, success, and error states.
- Duplicate creates a new item with `(Copy)` in the title and preserves the original.
- Change Content Type persists after a refresh.
- Hidden ideas leave the active feed and can be restored through Undo.
- Deleted ideas cannot be used for script or caption generation.
- Improve, Variations, and Regenerate visibly finish or fail.
- Cross-account requests return `404` or `403` and never mutate another account's idea.

