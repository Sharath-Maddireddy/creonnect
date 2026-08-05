# Implementation Plan: Enhanced Drivers, Creator Intelligence & Content Pillars

**Date:** 2025-07-23
**Status:** Draft
**Author:** Engineering Analysis

---

## Executive Summary

This plan addresses three critical gaps in the Account Analysis dashboard:
1. **Drivers section** shows too few items with minimal explanations
2. **Creator Intelligence** section is completely empty (N/A values)
3. **Content Pillars** lack scoring explanations

---

## Issue 1: Drivers Enhancement

### Current State
- **File**: `backend/app/analytics/account_health_engine.py:385-542`
- **Behavior**: Only generates LIMITING drivers when pillar scores < 50
- **Result**: High-performing accounts show 0-1 drivers maximum

### Root Cause
```python
# Line 411-424: Only triggers when content_quality < 50
if content_quality < 50.0:
    drivers.append(DeterministicDriver(...))
```

### Proposed Solution

#### 1.1 Add POSITIVE Drivers for High Scores
```python
# New function: _build_positive_drivers
def _build_positive_drivers(
    content_quality: float,
    engagement_quality: float,
    niche_fit: float,
    consistency: float,
    brand_safety: float,
) -> list[DeterministicDriver]:
    """Generate POSITIVE drivers for high-performing areas."""
    drivers = []
    
    if content_quality >= 80:
        drivers.append(DeterministicDriver(
            id="content_quality_strong",
            label="Strong content clarity and quality",
            type="POSITIVE",
            explanation=(
                f"Content signals are healthy (S1={content_metrics.get('mean_s1_0_50')}, "
                f"S2={content_metrics.get('mean_s2_0_50')}, "
                f"S3={content_metrics.get('mean_s3_0_50')}). "
                "Visual hooks and caption structures are effective."
            ),
        ))
    
    if engagement_quality >= 80:
        drivers.append(DeterministicDriver(
            id="engagement_quality_strong",
            label="Engagement exceeds benchmarks",
            type="POSITIVE",
            explanation=(
                f"Median engagement performance exceeds benchmark "
                f"(ratio={engagement_metrics.get('ratio_vs_account_avg', 'n/a')}). "
                "Audience is actively interacting with content."
            ),
        ))
    
    # ... similar for niche_fit, consistency, brand_safety
    return drivers
```

#### 1.2 Enhance Existing LIMITING Driver Explanations
```python
# Example: Enhanced explanation for content_quality_low
explanation=(
    f"Mean content signals are low "
    f"(S1={content_metrics.get('mean_s1_0_50')}, "
    f"S2={content_metrics.get('mean_s2_0_50')}, "
    f"S3={content_metrics.get('mean_s3_0_50')}).\n\n"
    f"What this means:\n"
    f"- S1 (Visual Quality): Your opening frames may lack visual appeal\n"
    f"- S2 (Caption): Captions may not hook readers effectively\n"
    f"- S3 (Clarity): Content message may be unclear to viewers\n\n"
    f"Recommended actions:\n"
    f"- Use stronger opening visuals in first 3 seconds\n"
    f"- Add clear hooks in caption first lines\n"
    f"- Ensure content theme is immediately clear"
),
```

#### 1.3 Add Pillar-Specific Drivers
```python
# New: Generate drivers based on pillar score variations
def _build_pillar_drivers(pillars: dict) -> list[DeterministicDriver]:
    """Generate drivers based on pillar score analysis."""
    drivers = []
    scores = [p.score for p in pillars.values()]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    # Highlight biggest strength
    if pillars:
        best_pillar = max(pillars.items(), key=lambda x: x[1].score)
        if best_pillar[1].score >= 70:
            drivers.append(DeterministicDriver(
                id=f"pillar_strength_{best_pillar[0]}",
                label=f"{best_pillar[0].replace('_', ' ').title()} is a key strength",
                type="POSITIVE",
                explanation=(
                    f"Your {best_pillar[0].replace('_', ' ')} score of "
                    f"{best_pillar[1].score}/100 is in the "
                    f"{best_pillar[1].band} band. "
                    f"{chr(10).join(best_pillar[1].notes) if best_pillar[1].notes else 'This is performing well.'}"
                ),
            ))
    
    # Highlight biggest weakness
    if pillars:
        worst_pillar = min(pillars.items(), key=lambda x: x[1].score)
        if worst_pillar[1].score < 50:
            drivers.append(DeterministicDriver(
                id=f"pillar_weakness_{worst_pillar[0]}",
                label=f"{worst_pillar[0].replace('_', ' ').title()} needs attention",
                type="LIMITING",
                explanation=(
                    f"Your {worst_pillar[0].replace('_', ' ')} score of "
                    f"{worst_pillar[1].score}/100 is in the "
                    f"{worst_pillar[1].band} band. "
                    f"This is dragging down your overall account health. "
                    f"{chr(10).join(worst_pillar[1].notes) if worst_pillar[1].notes else 'Focus on improving this area.'}"
                ),
            ))
    
    return drivers
```

### Files to Modify
1. `backend/app/analytics/account_health_engine.py` - Add new driver generation functions
2. `backend/app/domain/account_models.py` - No changes needed (DeterministicDriver model is sufficient)

---

## Issue 2: Creator Intelligence Fix

### Current State
- **File**: `backend/app/services/account_ai_intelligence.py:249-346`
- **Problem**: LLM call fails silently, fallback generates minimal data
- **Frontend**: Shows "N/A" for AUDIENCE HYPOTHESIS, SPONSORSHIP POTENTIAL, STRENGTHS, IMPROVEMENT AREAS

### Root Cause Analysis

The `generate_creator_intelligence` function has two paths:
1. **LLM path** (lines 286-332): Calls external LLM API
2. **Fallback path** (lines 276-284): Heuristic-based inference

**Likely failure points:**
- LLM API timeout or authentication failure
- LLM response parsing error (TOON format)
- Missing input data (posts, username, etc.)

### Proposed Solution

#### 2.1 Enhance Heuristic Fallback
```python
def _infer_audience_hypothesis(
    posts: list[SinglePostInsights],
    creator_dominant_category: str | None,
    niche_tags: list[str] | None,
    follower_count: int | None,
) -> str | None:
    """Generate audience hypothesis from available data."""
    parts = []
    
    if creator_dominant_category:
        parts.append(f"Likely interested in {creator_dominant_category.lower()}")
    
    if niche_tags:
        parts.append(f"following topics like {', '.join(niche_tags[:3])}")
    
    # Analyze engagement patterns
    high_engagement_posts = [p for p in posts if (p.derived_metrics.engagement_rate or 0) > 0.05]
    if high_engagement_posts:
        avg_likes = sum(p.core_metrics.likes or 0 for p in high_engagement_posts) / len(high_engagement_posts)
        if avg_likes > 1000:
            parts.append("with active, engaged community")
    
    if follower_count:
        if follower_count < 10000:
            parts.append("primarily micro-audience")
        elif follower_count < 100000:
            parts.append("mid-tier audience")
        else:
            parts.append("established audience base")
    
    return ". ".join(parts) + "." if parts else None


def _infer_sponsorship_potential(
    brand_safety: float,
    engagement_quality: float,
    consistency: float,
) -> str:
    """Determine sponsorship potential from scores."""
    score = (brand_safety * 0.4) + (engagement_quality * 0.35) + (consistency * 0.25)
    
    if score >= 80:
        return "HIGH"
    elif score >= 60:
        return "MEDIUM"
    return "LOW"


def _infer_strengths(
    pillars: dict,
    engagement_signals: dict,
) -> list[str]:
    """Extract strengths from pillar scores and engagement signals."""
    strengths = []
    
    for pillar_name, pillar_data in pillars.items():
        if pillar_data.score >= 70:
            label = pillar_name.replace('_', ' ').title()
            strengths.append(f"Strong {label} ({pillar_data.score}/100)")
    
    # Add engagement-based strengths
    if engagement_signals.get('audience_trust_index', 0) >= 70:
        strengths.append("High audience trust index")
    if engagement_signals.get('consistency_score', 0) >= 70:
        strengths.append("Consistent posting performance")
    
    return strengths[:5]


def _infer_improvement_areas(
    pillars: dict,
    engagement_signals: dict,
) -> list[str]:
    """Extract improvement areas from low scores."""
    areas = []
    
    for pillar_name, pillar_data in pillars.items():
        if pillar_data.score < 50:
            label = pillar_name.replace('_', ' ').title()
            areas.append(f"Improve {label} (currently {pillar_data.score}/100)")
    
    # Add engagement-based improvements
    if engagement_signals.get('avg_save_rate', 0) < 0.02:
        areas.append("Increase save-worthy content")
    if engagement_signals.get('avg_share_rate', 0) < 0.01:
        areas.append("Create more shareable content")
    
    return areas[:5]
```

#### 2.2 Update Fallback Result Builder
```python
# In generate_creator_intelligence function, update fallback_result:
fallback_result = CreatorIntelligence(
    creator_persona=_infer_persona(username, creator_dominant_category, niche_tags, follower_count),
    content_style_summary=_infer_content_style(posts),
    audience_hypothesis=_infer_audience_hypothesis(posts, creator_dominant_category, niche_tags, follower_count),
    creator_strengths=_infer_strengths(pillars, engagement_signals),
    improvement_areas=_infer_improvement_areas(pillars, engagement_signals),
    sponsorship_potential=_infer_sponsorship_potential(brand_safety, engagement_quality, consistency),
    notable_formats=_infer_notable_formats(posts),
    top_performing_themes=top_words[:5],
    brand_fit=BrandFitSignals(
        fit_categories=fit_categories,
        red_flags=red_flags,
    ),
)
```

#### 2.3 Add LLM Error Logging
```python
except Exception as exc:
    logger.warning(
        "[CreatorIntelligence] LLM generation failed for username=%s account_id=%s: %s",
        username,
        account_id,
        exc,
        exc_info=True  # Add stack trace for debugging
    )
```

### Files to Modify
1. `backend/app/services/account_ai_intelligence.py` - Enhance heuristic functions
2. `backend/app/services/account_analysis_jobs.py` - Pass required data to intelligence generator

---

## Issue 3: Content Pillars Explanations

### Current State
- **File**: `backend/app/domain/account_models.py:227-233`
- **Model**: Only has `name` and `engagement_percentage`
- **Frontend**: Shows name + percentage bar, no explanation

### Proposed Solution

#### 3.1 Extend ContentPillar Model
```python
class ContentPillar(BaseModel):
    """Content pillar with engagement share and explanation."""

    model_config = ConfigDict(extra="forbid")

    name: str
    engagement_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    post_count: int = Field(default=0, ge=0, description="Number of posts in this pillar")
    avg_engagement_rate: float | None = Field(default=None, description="Average engagement rate for posts in this pillar")
    avg_reach: float | None = Field(default=None, description="Average reach for posts in this pillar")
    explanation: str | None = Field(default=None, description="Human-readable explanation of this pillar's performance")
    top_post_ids: list[str] = Field(default_factory=list, description="Media IDs of top posts in this pillar")
    trend: str | None = Field(default=None, description="Performance trend: 'improving', 'stable', or 'declining'")
```

#### 3.2 Enhance _extract_content_pillars Function
```python
def _extract_content_pillars(posts: list[SinglePostInsights]) -> list[ContentPillar]:
    """Derive content pillars with detailed explanations."""
    pillar_data = defaultdict(lambda: {
        'count': 0,
        'engagement_rates': [],
        'reach_values': [],
        'post_ids': []
    })
    
    for post in posts:
        caption = post.caption_text or ""
        hashtags = _extract_hashtags_from_caption(caption)
        category = (post.post_category or "").strip().lower()
        
        # Determine primary pillar
        pillar_name = None
        if category and category not in {"unknown", ""}:
            pillar_name = category
        elif hashtags:
            pillar_name = hashtags[0]  # Use primary hashtag
        
        if pillar_name:
            pillar_data[pillar_name]['count'] += 1
            
            er = _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
            if er is not None:
                pillar_data[pillar_name]['engagement_rates'].append(er)
            
            reach = _safe_float(getattr(post.core_metrics, "reach", None))
            if reach is not None:
                pillar_data[pillar_name]['reach_values'].append(reach)
            
            if post.media_id:
                pillar_data[pillar_name]['post_ids'].append(post.media_id)
    
    total_posts = sum(d['count'] for d in pillar_data.values()) or 1
    
    pillars = []
    for name, data in sorted(pillar_data.items(), key=lambda x: x[1]['count'], reverse=True)[:6]:
        avg_er = sum(data['engagement_rates']) / len(data['engagement_rates']) if data['engagement_rates'] else None
        avg_reach = sum(data['reach_values']) / len(data['reach_values']) if data['reach_values'] else None
        
        # Generate explanation
        explanation = _generate_pillar_explanation(
            name=name,
            post_count=data['count'],
            total_posts=total_posts,
            avg_engagement_rate=avg_er,
            avg_reach=avg_reach,
        )
        
        pillars.append(ContentPillar(
            name=name,
            engagement_percentage=round((data['count'] / total_posts) * 100, 2),
            post_count=data['count'],
            avg_engagement_rate=round(avg_er, 4) if avg_er else None,
            avg_reach=round(avg_reach, 2) if avg_reach else None,
            explanation=explanation,
            top_post_ids=data['post_ids'][:3],
        ))
    
    return pillars


def _generate_pillar_explanation(
    name: str,
    post_count: int,
    total_posts: int,
    avg_engagement_rate: float | None,
    avg_reach: float | None,
) -> str:
    """Generate human-readable explanation for a content pillar."""
    percentage = round((post_count / total_posts) * 100, 1)
    
    parts = [f"'{name}' represents {percentage}% of your content ({post_count} posts)."]
    
    if avg_engagement_rate is not None:
        if avg_engagement_rate >= 0.06:
            parts.append(f"This pillar performs exceptionally well with a {avg_engagement_rate*100:.1f}% average engagement rate.")
        elif avg_engagement_rate >= 0.03:
            parts.append(f"This pillar has solid performance with a {avg_engagement_rate*100:.1f}% average engagement rate.")
        else:
            parts.append(f"This pillar underperforms with only a {avg_engagement_rate*100:.1f}% average engagement rate.")
    
    if avg_reach is not None:
        parts.append(f"Average reach per post: {avg_reach:,.0f}.")
    
    return " ".join(parts)
```

### Files to Modify
1. `backend/app/domain/account_models.py` - Extend ContentPillar model
2. `backend/app/analytics/account_health_engine.py` - Enhance pillar extraction

---

## Implementation Phases

### Phase 1: Quick Wins (1-2 days)
1. Add POSITIVE drivers for high scores
2. Enhance LIMITING driver explanations
3. Fix Creator Intelligence fallback generation

### Phase 2: Content Pillars (2-3 days)
1. Extend ContentPillar model
2. Enhance pillar extraction with explanations
3. Update frontend to display explanations

### Phase 3: Testing & Polish (1-2 days)
1. Add unit tests for new driver generation
2. Test Creator Intelligence with various edge cases
3. Frontend validation and UX polish

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Average drivers per account | 0-1 | 4-6 |
| Creator Intelligence fields populated | 20% | 90% |
| Content Pillars with explanations | 0% | 100% |
| Driver explanation length | 1-2 sentences | 3-5 sentences with actionable insights |

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM API still fails | High | Enhanced heuristic fallback ensures data availability |
| Too many drivers overwhelm users | Medium | Limit to 6-8 drivers max, prioritize by impact |
| Performance impact from enhanced explanations | Low | Explanations generated synchronously, minimal overhead |

---

## Open Questions

1. Should we limit the number of drivers displayed? (Recommended: 6-8 max)
2. Should content pillar explanations be toggleable in the UI?
3. Should we add a "Why this score?" expandable section for each pillar?
