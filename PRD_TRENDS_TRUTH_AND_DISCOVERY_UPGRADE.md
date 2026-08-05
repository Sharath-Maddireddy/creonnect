# PRD: Trends Truth & Discovery Upgrade

**Author:** Engineering Team  
**Status:** Draft  
**Last Updated:** 2026-07-28  
**Related Docs:** `PRD_TREND_RECOMMENDATIONS.md`, `PRD_CONTENT_SUGGESTIONS_FULL_FLOW.md`

---

## 1. Overview

This PRD defines the next product and engineering upgrade for the Trends page so that the UI shows backend-backed data instead of guessed placeholders wherever possible, while also adding high-value discovery features that creators expect:

- search by username/handle
- real weekly opportunity score and summary
- backend-driven recommendation filters
- real trending topics detail
- real trending audio detail
- backend-backed reasoning and confidence details

This scope explicitly excludes rebuilding the "Ask AI Assistant" module for now.

---

## 2. Problem Statement

The current Trends experience mixes real backend data with frontend-derived or placeholder values. This creates three product problems:

1. trust risk  
   Users cannot tell which metrics are real and which are inferred in the UI.

2. discovery friction  
   Users still have to think in internal account IDs instead of natural usernames/handles.

3. incomplete decision support  
   Users can see that something is trending, but not enough structured detail about why it matters, which audio is involved, or how confident the system is.

---

## 3. Goals

### 3.1 Product Goals

- Make the Trends page materially more truthful and explainable.
- Reduce friction by allowing creator search via username or `@handle`.
- Upgrade sidebar and detail surfaces from summary-only to decision-support tools.
- Keep current successful generation workflows intact.

### 3.2 Success Criteria

- 0 intentionally fake numeric metrics shown in primary trends UI without explicit labeling.
- Users can search a creator using username or `@username`.
- Weekly Opportunity banner uses a true backend score and summary payload.
- Filter tabs return backend-consistent results rather than text heuristics.
- Trending Topics and Trending Audio surfaces show structured detail, not only counts or placeholder match values.
- Reasoning modal uses backend confidence and explanation fields end-to-end.

---

## 4. Non-Goals

- Rebuilding Ask AI Assistant
- Replacing the entire trend generation pipeline
- Changing script/caption/save/schedule workflows that already function
- Building a full social listening platform outside the trends page

---

## 5. Current State Audit

### 5.1 Safe / Real Today

These are already backend-backed enough to keep:

- niche primary category
- niche sub-niches
- niche confidence score
- global trends list
- trend type
- momentum
- trend descriptions
- recommendation title
- rationale
- expected impact
- trend reference
- hook
- content style
- best time, when present
- difficulty, when present
- expected reach, when present
- content gaps
- daily insights fields
- generated ideas
- script, caption, save, schedule, thumbnail, improve, regenerate flows

### 5.2 Not Fully Truthful Today

These should be rebuilt, relabeled, or removed:

- weekly opportunity banner score
- weekly opportunity idea count
- fallback opportunity bullets
- fallback recommendation card score
- fallback audience match values
- heuristic filters for carousel / personal story / brand friendly / beginner / advanced
- trending audio shown only as count
- reasoning modal confidence block
- rich trending topics detail relying on fallback values

---

## 6. Scope

This PRD covers six feature tracks.

### Track A — Username Search

Allow users to search and load trend data using:

- internal account ID
- plain username
- `@username`

### Track B — True Weekly Opportunity Banner

Replace inferred banner values with backend-computed:

- weekly opportunity score
- weekly opportunity label
- recommendation count
- summary bullets
- summary explanation

### Track C — Backend-Driven Filters

Replace frontend text-heuristic filtering with backend classifications attached to recommendations and/or trends.

### Track D — Trending Topics Detail

Provide a proper detailed dataset for trending topics, including match, growth, competition, and explanation.

### Track E — Trending Audio Detail

Move from only showing `trending_audio_count` to exposing actual audio trend objects.

### Track F — Reasoning / Confidence Truthfulness

Replace hardcoded reasoning confidence UI with backend-provided fields.

---

## 7. Functional Requirements

## 7.1 Track A — Username Search

### User Story

As a user, I want to search by username or `@handle` so I do not need to know the internal account ID.

### Requirements

1. Search input must accept:
   - `creator123`
   - `@creator123`
   - existing account IDs

2. System must normalize input:
   - trim whitespace
   - strip leading `@`
   - lowercase for matching where appropriate

3. Backend must resolve search input to a canonical account record.

4. If multiple matches exist, backend must return a disambiguation response shape or a deterministic best match.

5. Frontend placeholder text must change from "Search creator account ID…" to wording that includes username/handle support.

### API

Preferred new endpoint:

`GET /api/v1/accounts/resolve?query={value}`

Response example:

```json
{
  "query": "@morgbullard_id",
  "resolved": true,
  "account_id": "morgbullard_id",
  "username": "morgbullard_id",
  "display_name": "Morg Bullard"
}
```

Failure example:

```json
{
  "query": "@unknown_creator",
  "resolved": false,
  "reason": "not_found"
}
```

---

## 7.2 Track B — True Weekly Opportunity Banner

### User Story

As a user, I want the top opportunity card to reflect a real weekly opportunity signal, not a repurposed niche confidence metric.

### Requirements

Backend must send a dedicated banner payload with:

- `weekly_opportunity_score` (0-100)
- `weekly_opportunity_label` (`Low`, `Medium`, `High`, `Very High`)
- `idea_count`
- `summary_bullets`
- `summary_reason`

Frontend must:

- stop deriving score from `niche.confidence_score`
- stop deriving idea count from sub-niche length
- stop inventing fallback bullets in primary mode
- gracefully show empty-state copy if banner payload is missing

### API Contract Addition

Add to trends payload:

```json
"weekly_opportunity": {
  "score": 84,
  "label": "Very High",
  "idea_count": 6,
  "summary_reason": "Strong match between recent outfit-formula performance and current rising saveable style trends.",
  "bullets": [
    "Repeatable outfit formula videos are outperforming one-off hauls.",
    "Seasonal comparison hooks are well-matched to your audience.",
    "Low-friction saveable styling content has strong reach potential."
  ]
}
```

---

## 7.3 Track C — Backend-Driven Filters

### User Story

As a user, I want filters to behave predictably so tabs only show items that truly belong there.

### Requirements

Each recommendation must expose explicit classification fields instead of relying on frontend text matching.

Required fields:

- `format_family`: `reel | carousel | photo`
- `angle_type`: `educational | personal_story | brand_friendly | trend_report | entertainment | other`
- `creator_level`: `beginner | intermediate | advanced`
- `is_trending`: boolean

Frontend tabs must map only to backend fields:

- Reels → `format_family = reel`
- Carousel → `format_family = carousel`
- Photo → `format_family = photo`
- Trending → `is_trending = true`
- Educational → `angle_type = educational`
- Personal Story → `angle_type = personal_story`
- Brand Friendly → `angle_type = brand_friendly`
- Beginner → `creator_level = beginner`
- Advanced → `creator_level = advanced`

### API Contract Addition

Add fields to each recommendation:

```json
{
  "format_family": "reel",
  "angle_type": "educational",
  "creator_level": "beginner",
  "is_trending": true
}
```

---

## 7.4 Track D — Trending Topics Detail

### User Story

As a user, I want to understand why a topic is worth acting on, not just see a name and a decorative match bar.

### Requirements

Backend must expose detailed topic rows with:

- topic name
- trend type
- momentum
- audience match %
- growth %
- competition level
- explanation
- example reference
- why it fits this creator

Frontend right rail and “View All” experiences must use only this data, with no random or positional fallback values.

### API

Preferred endpoint:

`GET /api/v1/accounts/{account_id}/trends/topics`

Response example:

```json
{
  "topics": [
    {
      "id": "topic_1",
      "topic_name": "Amazon capsule wardrobe under 100 dollars",
      "trend_type": "topic",
      "momentum": "rising",
      "audience_match_pct": 92,
      "growth_pct": 148,
      "competition_level": "Medium",
      "description": "Budget capsule wardrobe content is seeing rising saves and repeat-view behavior.",
      "why_it_fits": "Your audience already engages with affordable outfit formula content.",
      "example_reference": "Budget wardrobe comparison reels"
    }
  ],
  "total": 12
}
```

---

## 7.5 Track E — Trending Audio Detail

### User Story

As a user, I want to know which specific audios are relevant, not only how many exist.

### Requirements

Backend must provide a list of trending audio objects when available.

Required fields:

- audio name / title
- momentum
- usage growth %
- audience match %
- creator fit explanation
- content idea angle
- optional example reference

The Trends page must continue to support `trending_audio_count`, but may additionally show:

- top 3 relevant audios
- why each fits this creator

### API

Preferred endpoint:

`GET /api/v1/accounts/{account_id}/trends/audio`

Response example:

```json
{
  "audio_tracks": [
    {
      "id": "audio_1",
      "audio_name": "Soft glam transition sound",
      "momentum": "rising",
      "growth_pct": 121,
      "audience_match_pct": 87,
      "fit_reason": "Pairs well with transformation and look-reveal content.",
      "suggested_angle": "Use this audio with a 3-look outfit transition reel.",
      "example_reference": "Beauty and fashion transition reels"
    }
  ],
  "count": 4
}
```

### Note

If exact third-party audio identifiers are unavailable, phase 1 may use named audio trends from the trend intelligence layer, but the UI must label them as “audio trends” and not imply direct platform-native audio IDs.

---

## 7.6 Track F — Reasoning / Confidence Truthfulness

### User Story

As a user, I want to understand why the system scored an idea highly and how confident it is in that assessment.

### Requirements

Backend reasoning payload must provide:

- `opportunity_score`
- factor breakdown
- `ai_confidence_pct`
- `percentile_rank` or equivalent comparative label
- `strongest_factor`
- `weakest_factor`
- `summary_explanation`

Frontend must remove hardcoded confidence values and notes.

### API Contract Addition

Extend existing reasoning response:

```json
{
  "idea_id": "123",
  "opportunity_score": 88,
  "ai_confidence_pct": 91,
  "percentile_rank": 12,
  "strongest_factor": "audience_match",
  "weakest_factor": "competition_score",
  "summary_explanation": "Strong audience fit and timely topic momentum outweigh moderate competition.",
  "factors": [
    { "key": "niche_relevance", "value": 90, "tooltip": "High alignment with your niche" }
  ]
}
```

---

## 8. UX Requirements

### 8.1 Search

- Input placeholder: `Search by creator username, @handle, or account ID…`
- If resolution fails, show friendly not-found state.
- If resolution succeeds, preserve resolved username in the UI where helpful.

### 8.2 Banner

- Rename or relabel components only if they reflect the actual backend semantics.
- If banner payload is unavailable, show neutral copy instead of inferred numbers.

### 8.3 Filters

- A filter with zero results must still be truthful; no synthetic cards should be injected.

### 8.4 Trending Topics / Audio

- Decorative visuals are acceptable, but no numeric fallback values may be shown as real.

### 8.5 Reasoning

- Confidence and explanations must map 1:1 to backend payload fields.

---

## 9. Data Model Changes

### 9.1 TrendAnalysisResult additions

Add optional field:

```json
"weekly_opportunity": {
  "score": 0,
  "label": "",
  "idea_count": 0,
  "summary_reason": "",
  "bullets": []
}
```

### 9.2 TrendRecommendation additions

- `format_family`
- `angle_type`
- `creator_level`
- `is_trending`

### 9.3 New supporting response models

- `ResolvedAccount`
- `WeeklyOpportunity`
- `TrendingTopicDetail`
- `TrendingAudioDetail`
- `IdeaReasoningExtended`

---

## 10. Rollout Plan

### Phase 1

- username search
- true weekly opportunity payload
- remove fake banner score/count
- reasoning modal cleanup

### Phase 2

- backend-driven recommendation filters
- trending topics detail endpoint

### Phase 3

- trending audio detail endpoint
- optional richer topic/audio surfaces in UI

---

## 11. Risks

### Risk 1 — Username ambiguity

Some sources may contain duplicate usernames or stale mappings.

Mitigation:

- use canonical resolver endpoint
- log ambiguous matches
- support deterministic best match or explicit disambiguation later

### Risk 2 — Weak audio data source

We may not have stable track-level audio coverage immediately.

Mitigation:

- phase 1 can expose named audio trends
- label honestly as “audio trends” until native-level IDs are available

### Risk 3 — Empty filters after truthification

When heuristic fallback is removed, some tabs may become sparse.

Mitigation:

- expose explicit backend classification
- do not fake results

### Risk 4 — User trust drop during transition

Removing inflated or inferred values may make the UI feel less “full.”

Mitigation:

- prefer empty but honest states
- add explanation copy where data is still being rolled out

---

## 12. Acceptance Criteria

This project is complete when:

- a user can search with username or `@handle`
- Trends page no longer shows fake weekly opportunity score/count
- primary filter tabs are driven by backend classification fields
- Trending Topics view shows real match/growth/competition/explanation fields
- Trending Audio section can show actual audio trend objects when available
- reasoning modal uses backend confidence/explanation values only
- no primary trends metric relies on random, positional, or hardcoded numeric fallbacks

---

## 13. Recommended Implementation Order

1. username search
2. weekly opportunity payload
3. reasoning modal truth cleanup
4. backend-driven filters
5. trending topics detail endpoint
6. trending audio detail endpoint

This order improves trust first, then expands discovery depth.
