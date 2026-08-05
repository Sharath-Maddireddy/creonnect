# Implementation Checklist: Trends Truth & Discovery Upgrade

**Author:** Engineering Team  
**Status:** Draft  
**Last Updated:** 2026-07-28  
**Primary PRD:** `PRD_TRENDS_TRUTH_AND_DISCOVERY_UPGRADE.md`

---

## 1. Purpose

This document translates the Trends Truth & Discovery PRD into a build-ready implementation plan. It is designed for engineering execution and QA handoff.

This checklist covers:

- backend API work
- domain model changes
- frontend UI updates
- rollout order
- validation and QA checkpoints

This checklist does not include Ask AI Assistant rebuild work.

---

## 2. Recommended Delivery Order

Build in this order:

1. username search
2. weekly opportunity payload
3. reasoning modal truth cleanup
4. backend-driven filters
5. trending topics detail endpoint
6. trending audio detail endpoint

Reason:

- search and trust fixes unlock immediate UX value
- reasoning and banner cleanup remove misleading UI quickly
- filters/topics/audio depend on clearer backend contracts

---

## 3. Track A — Username Search

## Goal

Allow a user to search by:

- account ID
- username
- `@username`

## Backend Tasks

- [ ] Add resolver response model(s) in [backend/app/domain/trend_models.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/trend_models.py) or a dedicated account resolver model file
- [ ] Add `GET /api/v1/accounts/resolve?query=...` in [backend/app/api/trend_routes.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/api/trend_routes.py) or a dedicated account lookup route file
- [ ] Implement normalization:
  - [ ] trim
  - [ ] strip `@`
  - [ ] lowercase for username matching
- [ ] Implement lookup strategy:
  - [ ] exact account ID match
  - [ ] exact username match
  - [ ] optional fallback using account analysis / creator metadata tables if available
- [ ] Return deterministic `resolved=false` payload for not found cases
- [ ] Log ambiguous match cases

## Likely Backend Data Sources to Inspect

- [backend/app/infra/models.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/infra/models.py)
- account analysis result store / creator metadata tables
- any existing user/account profile persistence already used by dashboard/trends flows

## Frontend Tasks

- [ ] Update input placeholder in [frontend/src/pages/TrendRecommendations.jsx](C:/Users/ASUS/Documents/augment-projects/creonnect/frontend/src/pages/TrendRecommendations.jsx)
  - from: `Search creator account ID…`
  - to: `Search by creator username, @handle, or account ID…`
- [ ] Update `handleSearch()` to call resolver first
- [ ] On resolve success:
  - [ ] set canonical `accountId`
  - [ ] continue existing trends fetch flow
- [ ] On resolve failure:
  - [ ] show friendly inline error state
- [ ] Preserve existing support for direct account ID search

## QA Checklist

- [ ] searching `morgbullard_id` works
- [ ] searching `@morgbullard_id` works
- [ ] searching unknown creator shows not-found state
- [ ] existing direct account-id flow still works

---

## 4. Track B — True Weekly Opportunity Banner

## Goal

Replace inferred banner values with a real backend payload.

## Backend Tasks

- [ ] Add `WeeklyOpportunity` model in [backend/app/domain/trend_models.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/trend_models.py)
- [ ] Extend `TrendAnalysisResult` to include optional `weekly_opportunity`
- [ ] Compute and return:
  - [ ] `score`
  - [ ] `label`
  - [ ] `idea_count`
  - [ ] `summary_reason`
  - [ ] `bullets`
- [ ] Decide scoring inputs, likely from:
  - [ ] trend momentum distribution
  - [ ] audience match strength
  - [ ] content gap opportunity
  - [ ] recent creator fit / post timing / recommendation scores
- [ ] Add tests covering:
  - [ ] payload present
  - [ ] score range 0-100
  - [ ] label mapping
  - [ ] no crash when some inputs are missing

## Likely Backend Files

- [backend/app/domain/trend_models.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/trend_models.py)
- [backend/app/services/creator_trend_service.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/services/creator_trend_service.py)
- [backend/app/analytics/trend_recommendation_engine.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/analytics/trend_recommendation_engine.py)
- [backend/app/api/trend_routes.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/api/trend_routes.py)

## Frontend Tasks

- [ ] Update `OpportunityBanner` in [frontend/src/pages/TrendRecommendations.jsx](C:/Users/ASUS/Documents/augment-projects/creonnect/frontend/src/pages/TrendRecommendations.jsx)
- [ ] Stop using `niche.confidence_score` as banner score
- [ ] Stop deriving idea count from sub-niche count
- [ ] Stop generating fallback bullets in the primary banner path
- [ ] Use `weekly_opportunity.score`
- [ ] Use `weekly_opportunity.label`
- [ ] Use `weekly_opportunity.idea_count`
- [ ] Use `weekly_opportunity.summary_reason`
- [ ] Use `weekly_opportunity.bullets`
- [ ] If payload absent:
  - [ ] show neutral fallback copy
  - [ ] do not show fake score

## QA Checklist

- [ ] banner score matches backend field
- [ ] label matches backend field
- [ ] bullets match backend payload
- [ ] missing payload does not show invented metrics

---

## 5. Track C — Reasoning Modal Truth Cleanup

## Goal

Make reasoning/confidence UI fully backend-backed.

## Backend Tasks

- [ ] Extend reasoning response from `GET /api/v1/accounts/{account_id}/ideas/{idea_id}/reasoning`
- [ ] Add fields:
  - [ ] `ai_confidence_pct`
  - [ ] `percentile_rank`
  - [ ] `strongest_factor`
  - [ ] `weakest_factor`
  - [ ] `summary_explanation`
- [ ] Ensure values are computed, not hardcoded
- [ ] Update tests for reasoning response shape

## Likely Backend Files

- [backend/app/api/content_suggestion_routes.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/api/content_suggestion_routes.py)
- [backend/app/domain/content_suggestion_models.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/content_suggestion_models.py) if typed models are introduced for reasoning

## Frontend Tasks

- [ ] Update [frontend/src/components/AIReasoningModal.jsx](C:/Users/ASUS/Documents/augment-projects/creonnect/frontend/src/components/AIReasoningModal.jsx)
- [ ] Remove hardcoded:
  - [ ] confidence %
  - [ ] confidence bar width
  - [ ] confidence note
  - [ ] percentile derivation if not backed
- [ ] Render:
  - [ ] `ai_confidence_pct`
  - [ ] `percentile_rank`
  - [ ] `summary_explanation`
  - [ ] strongest/weakest factor labels where useful

## QA Checklist

- [ ] modal shows backend confidence
- [ ] no hardcoded “89%” remains
- [ ] no hardcoded “Perfect timing for this content” remains unless backend supplies equivalent text

---

## 6. Track D — Backend-Driven Filters

## Goal

Replace heuristic filter logic with backend classifications.

## Backend Tasks

- [ ] Extend recommendation model with:
  - [ ] `format_family`
  - [ ] `angle_type`
  - [ ] `creator_level`
  - [ ] `is_trending`
- [ ] Update recommendation generation logic to populate those fields
- [ ] Define deterministic mapping rules for generated recommendations
- [ ] Add tests for each filter classification

## Likely Backend Files

- [backend/app/domain/trend_models.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/trend_models.py)
- [backend/app/analytics/trend_recommendation_engine.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/analytics/trend_recommendation_engine.py)
- [backend/app/services/creator_trend_service.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/services/creator_trend_service.py)

## Frontend Tasks

- [ ] Replace `matchesFilter()` heuristic logic in [frontend/src/pages/TrendRecommendations.jsx](C:/Users/ASUS/Documents/augment-projects/creonnect/frontend/src/pages/TrendRecommendations.jsx)
- [ ] Map filter tabs directly to backend fields
- [ ] Keep “All” as pass-through
- [ ] Do not synthesize cards for empty tabs

## QA Checklist

- [ ] Reels only shows `format_family = reel`
- [ ] Carousel only shows `format_family = carousel`
- [ ] Personal Story only shows `angle_type = personal_story`
- [ ] Beginner only shows `creator_level = beginner`
- [ ] Advanced only shows `creator_level = advanced`

---

## 7. Track E — Trending Topics Detail Endpoint

## Goal

Provide a truthful detailed dataset for trending topics and remove placeholder metric fallbacks.

## Backend Tasks

- [ ] Add `TrendingTopicDetail` model
- [ ] Add endpoint: `GET /api/v1/accounts/{account_id}/trends/topics`
- [ ] Return fields:
  - [ ] `id`
  - [ ] `topic_name`
  - [ ] `trend_type`
  - [ ] `momentum`
  - [ ] `audience_match_pct`
  - [ ] `growth_pct`
  - [ ] `competition_level`
  - [ ] `description`
  - [ ] `why_it_fits`
  - [ ] `example_reference`
- [ ] Support `total`
- [ ] Optionally add pagination if topic volume can exceed current UI assumptions

## Likely Backend Files

- [backend/app/domain/trend_models.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/trend_models.py)
- [backend/app/api/trend_routes.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/api/trend_routes.py)
- [backend/app/services/creator_trend_service.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/services/creator_trend_service.py)
- [backend/app/analytics/global_trend_engine.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/analytics/global_trend_engine.py)

## Frontend Tasks

- [ ] Update right-rail trending topic preview in [frontend/src/pages/TrendRecommendations.jsx](C:/Users/ASUS/Documents/augment-projects/creonnect/frontend/src/pages/TrendRecommendations.jsx)
- [ ] Remove positional fallback audience match values
- [ ] Update [frontend/src/components/AllTrendingTopics.jsx](C:/Users/ASUS/Documents/augment-projects/creonnect/frontend/src/components/AllTrendingTopics.jsx)
- [ ] Remove random fallback values for:
  - [ ] audience match
  - [ ] growth %
  - [ ] description
  - [ ] competition
- [ ] Use endpoint payload directly

## QA Checklist

- [ ] topic list values match backend response
- [ ] no random values remain
- [ ] right rail and full view stay consistent

---

## 8. Track F — Trending Audio Detail Endpoint

## Goal

Move from count-only audio insight to structured audio trend data.

## Backend Tasks

- [ ] Add `TrendingAudioDetail` model
- [ ] Add endpoint: `GET /api/v1/accounts/{account_id}/trends/audio`
- [ ] Return fields:
  - [ ] `id`
  - [ ] `audio_name`
  - [ ] `momentum`
  - [ ] `growth_pct`
  - [ ] `audience_match_pct`
  - [ ] `fit_reason`
  - [ ] `suggested_angle`
  - [ ] `example_reference`
- [ ] Maintain `trending_audio_count` in daily insights for lightweight summary
- [ ] If exact audio IDs are not available, ensure naming/labeling stays honest as “audio trends”

## Likely Backend Files

- [backend/app/domain/trend_models.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/trend_models.py)
- [backend/app/api/trend_routes.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/api/trend_routes.py)
- [backend/app/analytics/global_trend_engine.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/analytics/global_trend_engine.py)
- [backend/app/services/creator_trend_service.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/services/creator_trend_service.py)

## Frontend Tasks

- [ ] Add audio detail UI on Trends page or sidebar
- [ ] Keep current count display as summary
- [ ] Add a small “top audio trends” surface if payload available
- [ ] Do not imply platform-native track IDs if backend only provides named audio trends

## QA Checklist

- [ ] audio count still works
- [ ] audio detail list renders when endpoint returns data
- [ ] copy stays honest when only named audio trends are available

---

## 9. Cross-Cutting Cleanup Tasks

- [ ] Remove or stop using old preview-only helper copy that still references “Generate New Ideas” where no longer appropriate on quick-card flows
- [ ] Audit Trends page for any remaining fake numeric fallbacks
- [ ] Audit `AllTrendingTopics.jsx` for all random fallback usage
- [ ] Audit `AIReasoningModal.jsx` for all hardcoded reasoning values
- [ ] Ensure all newly added backend fields are optional during rollout to avoid breaking older stored payloads

---

## 10. Testing Checklist

## Backend

- [ ] unit tests for account resolution
- [ ] unit tests for weekly opportunity payload generation
- [ ] unit tests for recommendation classification fields
- [ ] unit tests for trending topic detail payload
- [ ] unit tests for trending audio detail payload
- [ ] unit tests for reasoning response extensions
- [ ] route tests for all new endpoints

## Frontend

- [ ] search by username
- [ ] search by `@username`
- [ ] weekly opportunity banner renders true payload
- [ ] filters work from backend fields
- [ ] topic detail view contains no random fallback values
- [ ] reasoning modal contains no hardcoded confidence values
- [ ] audio section gracefully hides if no audio detail payload exists

## Manual Smoke Tests

- [ ] load trends for known creator
- [ ] generate script from quick card
- [ ] generate caption from quick card
- [ ] save/schedule from quick card
- [ ] open reasoning modal from a full generated idea
- [ ] open trending topics view

---

## 11. Suggested File-Level Ownership

## Backend

- API routes:
  - [backend/app/api/trend_routes.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/api/trend_routes.py)
  - [backend/app/api/content_suggestion_routes.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/api/content_suggestion_routes.py)

- Domain models:
  - [backend/app/domain/trend_models.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/trend_models.py)
  - [backend/app/domain/content_suggestion_models.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/domain/content_suggestion_models.py)

- Services / engines:
  - [backend/app/services/creator_trend_service.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/services/creator_trend_service.py)
  - [backend/app/analytics/trend_recommendation_engine.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/analytics/trend_recommendation_engine.py)
  - [backend/app/analytics/global_trend_engine.py](C:/Users/ASUS/Documents/augment-projects/creonnect/backend/app/analytics/global_trend_engine.py)

## Frontend

- main page:
  - [frontend/src/pages/TrendRecommendations.jsx](C:/Users/ASUS/Documents/augment-projects/creonnect/frontend/src/pages/TrendRecommendations.jsx)

- supporting components:
  - [frontend/src/components/AllTrendingTopics.jsx](C:/Users/ASUS/Documents/augment-projects/creonnect/frontend/src/components/AllTrendingTopics.jsx)
  - [frontend/src/components/AIReasoningModal.jsx](C:/Users/ASUS/Documents/augment-projects/creonnect/frontend/src/components/AIReasoningModal.jsx)

---

## 12. Milestone Definition

## Milestone 1

- username search shipped
- weekly opportunity payload shipped
- reasoning modal truth cleanup shipped

## Milestone 2

- backend-driven filters shipped
- trending topics detail endpoint shipped

## Milestone 3

- trending audio detail shipped
- final truth audit completed

---

## 13. Done Definition

This implementation is complete when:

- [ ] user can search using username or `@handle`
- [ ] Trends banner no longer shows inferred fake score/count
- [ ] recommendation filters are backend-driven
- [ ] AllTrendingTopics no longer uses random fallback metrics
- [ ] reasoning modal shows backend confidence/explanation only
- [ ] audio trends are represented as structured data beyond count when available
- [ ] no primary trends metric relies on positional, random, or hardcoded numeric fallback behavior
