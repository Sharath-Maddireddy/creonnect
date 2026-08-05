# PRD: Enhanced Drivers, Creator Intelligence & Content Pillars

**Author:** Engineering Team
**Status:** Draft
**Last Updated:** 2025-07-23
**Target:** Production

---

## 1. Overview

This PRD defines enhancements to the Account Analysis dashboard focusing on three critical areas:
1. **Drivers Section** - More drivers with detailed explanations
2. **Creator Intelligence** - Fix empty state and populate all fields
3. **Content Pillars** - Add scoring explanations and context

### 1.1 Problem Statement

Current dashboard issues:
- **Drivers**: Only 0-1 drivers shown, minimal explanations, no POSITIVE drivers for high-performing areas
- **Creator Intelligence**: AUDIENCE HYPOTHESIS, SPONSORSHIP POTENTIAL, STRENGTHS, IMPROVEMENT AREAS all show "N/A"
- **Content Pillars**: Only name and percentage shown, no explanation of why pillars perform well/poorly

### 1.2 Target Users

| User | Primary Need |
|---|---|
| **Creator** | Understand what's working and what needs improvement |
| **Brand Manager** | Assess creator strengths and sponsorship potential |
| **Agency** | Quick overview of account health with actionable insights |

---

## 2. Goals and Objectives

| Goal | Success Metric | Target |
|---|---|---|
| Increase driver coverage | Average drivers per account | 4-6 drivers |
| Fix Creator Intelligence | Fields populated percentage | 90%+ |
| Add pillar explanations | Pillars with explanations | 100% |
| Maintain performance | Dashboard load time | <2s |

---

## 3. User Stories

### 3.1 Driver Stories

| ID | Story | Priority |
|---|---|---|
| US-D1 | As a creator, I want to see POSITIVE drivers for my strengths so I know what to continue doing | P0 |
| US-D2 | As a creator, I want detailed explanations for each driver so I understand the context | P0 |
| US-D3 | As a creator, I want to see pillar-specific drivers so I know which areas need attention | P1 |
| US-D4 | As a brand manager, I want to see drivers related to brand safety and engagement so I can assess suitability | P1 |

### 3.2 Creator Intelligence Stories

| ID | Story | Priority |
|---|---|---|
| US-CI1 | As a creator, I want to see my audience hypothesis so I understand who my content resonates with | P0 |
| US-CI2 | As a creator, I want to see my sponsorship potential so I know my marketability | P0 |
| US-CI3 | As a creator, I want to see my strengths and improvement areas so I have a clear action plan | P0 |
| US-CI4 | As a brand manager, I want to see creator persona and content style so I can assess brand fit | P1 |

### 3.3 Content Pillar Stories

| ID | Story | Priority |
|---|---|---|
| US-CP1 | As a creator, I want to see why a pillar performs well so I can replicate success | P0 |
| US-CP2 | As a creator, I want to see pillar-level engagement rates so I can compare performance | P1 |
| US-CP3 | As a creator, I want to see top posts per pillar so I can identify successful patterns | P1 |

---

## 4. Functional Requirements

### 4.1 Drivers Section Enhancement

#### 4.1.1 POSITIVE Drivers
- **Trigger**: Pillar score >= 70
- **Types**: Content quality, engagement quality, niche fit, consistency, brand safety
- **Format**: Same as LIMITING drivers but with green indicator

#### 4.1.2 Enhanced Explanations
- **Length**: 3-5 sentences
- **Components**:
  1. Current score and band
  2. What the score means
  3. Specific metrics contributing to the score
  4. Actionable recommendations

#### 4.1.3 Pillar-Specific Drivers
- **Trigger**: Significant variance between pillar scores
- **Output**: Highlight strongest and weakest pillars

### 4.2 Creator Intelligence Fix

#### 4.2.1 Required Fields
| Field | Source | Fallback |
|-------|--------|----------|
| creator_persona | LLM | Heuristic from category + niche |
| content_style_summary | LLM | Heuristic from media types + top words |
| audience_hypothesis | LLM | Heuristic from category + engagement patterns |
| creator_strengths | LLM | High-scoring pillars + engagement signals |
| improvement_areas | LLM | Low-scoring pillars + engagement gaps |
| sponsorship_potential | LLM | Weighted score from brand safety + engagement + consistency |

#### 4.2.2 Error Handling
- Log LLM failures with full stack trace
- Always return fallback data (never None)
- Frontend shows "Estimated" badge for heuristic data

### 4.3 Content Pillars Enhancement

#### 4.3.1 Extended Model
```python
class ContentPillar:
    name: str
    engagement_percentage: float
    post_count: int
    avg_engagement_rate: float | None
    avg_reach: float | None
    explanation: str
    top_post_ids: list[str]
    trend: str | None  # "improving", "stable", "declining"
```

#### 4.3.2 Explanation Components
1. Percentage of total content
2. Post count
3. Performance assessment (exceptional/solid/underperforming)
4. Average engagement rate comparison
5. Average reach context

---

## 5. Data Requirements

### 5.1 Input Data

| Data | Source | Required |
|------|--------|----------|
| Pillar scores | AccountHealthScore.pillars | Yes |
| Engagement signals | AccountHealthScore.engagement_signals | Yes |
| Posts list | Instagram Graph API | Yes |
| Creator metadata | Account profile | No (for fallback) |

### 5.2 Output Schema

All new fields are optional for backward compatibility:
- Drivers: Existing `DeterministicDriver` model (no changes)
- Creator Intelligence: Existing `CreatorIntelligence` model (no changes)
- Content Pillars: Extended `ContentPillar` model with new optional fields

---

## 6. Non-Functional Requirements

### 6.1 Performance
- Driver generation: <50ms
- Creator Intelligence fallback: <100ms
- Content Pillar extraction: <200ms
- Total dashboard load: <2s

### 6.2 Backward Compatibility
- All new fields optional (default None/empty)
- Existing API consumers unaffected
- Frontend gracefully handles missing fields

### 6.3 Data Integrity
- No fabricated metrics labeled as real
- Heuristic data marked with "Estimated" badge
- LLM failures logged but don't break dashboard

---

## 7. UI/UX Requirements

### 7.1 Drivers Section

```
┌─────────────────────────────────────────────────────────────┐
│ Account Drivers                                    6 found  │
├─────────────────────────────────────────────────────────────┤
│ ✓ Strong content clarity and quality              POSITIVE │
│   Content signals are healthy (S1=8.2, S2=7.5, S3=8.0).   │
│   Visual hooks and caption structures are effective.        │
│                                                             │
│ ✓ Engagement exceeds benchmarks                   POSITIVE │
│   Median engagement performance exceeds benchmark           │
│   (ratio=1.35). Audience is actively interacting.           │
│                                                             │
│ ! Content misaligned with audience                LIMITING │
│   Average S4 audience relevance is low (mean S4=24/50).    │
│   Consider aligning topics more tightly with your niche.    │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Creator Intelligence Section

```
┌─────────────────────────────────────────────────────────────┐
│ Creator Intelligence                              AI profile│
├─────────────────────────────────────────────────────────────┤
│ AUDIENCE HYPOTHESIS                                            │
│ Likely interested in fashion, following topics like          │
│ outfit ideas, styling tips. Active, engaged community.       │
│                                                             │
│ SPONSORSHIP POTENTIAL                                        │
│ HIGH                                                         │
│                                                             │
│ STRENGTHS                                                    │
│ • Strong Content Quality (85/100)                            │
│ • High audience trust index                                  │
│ • Consistent posting performance                             │
│                                                             │
│ IMPROVEMENT AREAS                                            │
│ • Improve Niche Fit (currently 45/100)                       │
│ • Increase save-worthy content                               │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Content Pillars Section

```
┌─────────────────────────────────────────────────────────────┐
│ Content Pillars (by Engagement)                              │
├─────────────────────────────────────────────────────────────┤
│ outfit ideas                              28.5% ████████░░ │
│ 'outfit ideas' represents 28.5% of your content (9 posts).  │
│ This pillar performs exceptionally well with a 6.8% average  │
│ engagement rate. Average reach per post: 12,450.             │
│                                                             │
│ styling tips                              22.1% ██████░░░░ │
│ 'styling tips' represents 22.1% of your content (7 posts).  │
│ This pillar has solid performance with a 4.2% average       │
│ engagement rate. Average reach per post: 8,320.              │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Drivers per account | 0-1 | 4-6 | API response audit |
| Creator Intelligence fields populated | 20% | 90% | API response audit |
| Content Pillars with explanations | 0% | 100% | Frontend inspection |
| Dashboard load time | <2s | <2s | APM monitoring |
| User satisfaction | N/A | >4.0/5.0 | User survey |

---

## 9. Dependencies

| Dependency | Status | Risk |
|------------|--------|------|
| LLM API | Active | Medium - may fail, fallback handles |
| Instagram Graph API | Active | Low - data already available |
| Pillar scoring engine | Active | Low - deterministic |

---

## 10. Out of Scope

| Feature | Rationale |
|---------|-----------|
| Real-time driver updates | Not needed for v1 |
| Custom driver categories | Keep simple for now |
| Pillar trend analysis over time | Requires historical data |
| A/B testing different explanations | Future optimization |

---

## 11. Implementation Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1: Drivers | 2 days | POSITIVE drivers + enhanced explanations |
| Phase 2: Creator Intelligence | 2 days | Fix fallback + populate all fields |
| Phase 3: Content Pillars | 2 days | Extended model + explanations |
| Phase 4: Testing & Polish | 1 day | Unit tests + UI polish |
| **Total** | **7 days** | |

---

## 12. Open Questions

| # | Question | Owner | Status |
|---|----------|-------|--------|
| 1 | Should we limit drivers to 6-8 max? | Product | Open |
| 2 | Should pillar explanations be toggleable? | Design | Open |
| 3 | Should we add "Why this score?" expandable? | Design | Open |
| 4 | Should Creator Intelligence show "Estimated" badge? | Product | Open |
