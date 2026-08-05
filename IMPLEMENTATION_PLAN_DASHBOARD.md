# AI Account Analysis Dashboard — Production Implementation Plan

## Goal
Make the `AccountHealthScore` response fully power the "Instagram Account AI Analysis" dashboard UI with real, accurate data — no stubs, no missing fields, no fake metrics.

---

## Phase 1: Wire Existing Code (Quick Wins)

These are fields where the code already exists but isn't connected. Lowest effort, highest impact.

### 1.1 Assign `content_type_performance` in response
**File:** `backend/app/analytics/account_health_engine.py:916-935`

`compute_content_type_performance(posts)` is fully implemented (line 1232) but never called in `compute_account_health_score`. Add one line to the return statement:

```python
content_type_performance=compute_content_type_performance(recent_posts),
```

**UI impact:** Enables the "Engagement Rate by Content Type" bar chart (Reels vs Carousel vs Image).

### 1.2 Populate `niche_benchmark` with real ratios
**File:** `backend/app/analytics/account_health_engine.py:931`

Currently returns `NicheBenchmark()` (all `None`). The `niche_avg_engagement_rate` parameter is already passed into `compute_account_health_score` but never used here. Add a helper:

```python
def _build_niche_benchmark(
    posts: list[SinglePostInsights],
    niche_avg_engagement_rate: float | None,
    follower_count: int | None,
) -> NicheBenchmark:
```

Compute:
- `engagement_rate_vs_niche` = median post ER / niche_avg_engagement_rate
- `reach_vs_niche` = stub until niche reach data is available (set `None`)
- `growth_vs_niche` = stub until niche growth data is available (set `None`)

**UI impact:** Enables the "You vs Niche Benchmark" comparison bars.

### 1.3 Compute `best_posting_time` from heatmap
**File:** `backend/app/analytics/account_health_engine.py:780-804`

`ai_summary.best_posting_time` is always `None`. After computing the heatmap, extract peak hours:

```python
def _compute_best_posting_time(heatmap: list[HeatmapData]) -> str | None:
    """Find the top 2-3 day/hour slots with highest intensity."""
    if not heatmap:
        return None
    sorted_slots = sorted(heatmap, key=lambda h: h.intensity, reverse=True)[:3]
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    slots = [f"{day_names[h.day_of_week]} {h.hour_of_day}:00" for h in sorted_slots]
    return ", ".join(slots)
```

Wire it into `_build_ai_summary` or compute separately and pass to `AISummary`.

**UI impact:** Enables "Best Posting Time: 6PM–10PM" in the AI Summary section.

---

## Phase 2: Handle Stubs Honestly

Ship fake data as real data erodes trust. Two options per stub — pick one.

### 2.1 `_build_audience_insights` (currently md5-hashed fake data)
**File:** `backend/app/analytics/account_health_engine.py:757-777`

**Option A (recommended):** Return `None` when data is unavailable. The frontend shows "Data unavailable" or hides the section.

```python
def _build_audience_insights(posts: list[SinglePostInsights]) -> AudienceInsights | None:
    """Return None when real audience data is unavailable from the API."""
    # Instagram Graph API does not expose viewer breakdown at account level.
    # Return None until real data source is integrated.
    return None
```

**Option B:** Keep the stub but add a flag so the frontend can label it:

Add to `AudienceInsights` model:
```python
is_estimated: bool = Field(default=False, description="True when values are synthetic estimates.")
```

Set `is_estimated=True` in the stub. Frontend shows "Estimated" badge.

### 2.2 `_stub_audience_demographics` (hardcoded country percentages)
**File:** `backend/app/analytics/account_health_engine.py:938-952`

Same approach — either return `None` or add `is_estimated: bool` to `AudienceDemographics`.

### 2.3 Comment sentiment (always 60/25/15)
**File:** `backend/app/analytics/account_health_engine.py:774-776`

These are hardcoded constants. If no real sentiment analysis is running, set all three to `None` in the `AudienceInsights` model rather than shipping fake percentages.

---

## Phase 3: Add Missing Fields

### 3.1 Add `growth_stage` to `AccountHealthScore`
**File:** `backend/app/domain/account_models.py`

Add to `AccountHealthScore`:
```python
growth_stage: str | None = Field(
    default=None,
    description="Human-readable growth stage derived from AHS band and trend direction.",
)
```

**File:** `backend/app/analytics/account_health_engine.py`

Derive from `ahs_band` + follower trend:
```python
def _derive_growth_stage(ahs_band: str, follower_trend: float | None) -> str:
    if ahs_band == "EXCEPTIONAL":
        return "Thriving"
    if ahs_band == "STRONG":
        return "Growing" if (follower_trend or 0) > 0 else "Stable"
    if ahs_band == "AVERAGE":
        return "Developing"
    return "Needs Attention"
```

### 3.2 Add `top_posts` to `AccountHealthScore`
**File:** `backend/app/domain/account_models.py`

New model:
```python
class TopPostSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    media_id: str | None = None
    caption_preview: str | None = None
    media_type: str | None = None
    published_at: str | None = None
    engagement_rate: float | None = None
    reach: float | None = None
```

Add to `AccountHealthScore`:
```python
top_posts: list[TopPostSummary] | None = None
```

**File:** `backend/app/analytics/account_health_engine.py`

New helper:
```python
def _extract_top_posts(posts: list[SinglePostInsights], limit: int = 5) -> list[TopPostSummary]:
    """Return top N posts sorted by engagement rate."""
    scored = []
    for post in posts:
        er = _safe_float(getattr(post.derived_metrics, "engagement_rate", None))
        if er is not None:
            scored.append((post, er))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [
        TopPostSummary(
            media_id=p.media_id,
            caption_preview=(p.caption_text or "")[:100],
            media_type=p.media_type,
            published_at=p.published_at.isoformat() if isinstance(p.published_at, datetime) else None,
            engagement_rate=er,
            reach=_safe_float(getattr(p.core_metrics, "reach", None)),
        )
        for p, er in scored[:limit]
    ]
```

### 3.3 Fix `est_rate_per_post` range
**File:** `backend/app/domain/account_models.py`

Add min/max fields to `BrandReadiness`:
```python
est_rate_per_post_min: float | None = Field(default=None, ge=0.0)
est_rate_per_post_max: float | None = Field(default=None, ge=0.0)
```

**File:** `backend/app/analytics/account_health_engine.py`

In `_calculate_brand_readiness`, compute range as ±20% of the base estimate.

---

## Phase 4: Testing

### 4.1 Unit tests for new helpers
**File:** `backend/app/tests/test_account_health_dashboard.py` (new)

| Test | What it validates |
|---|---|
| `test_build_niche_benchmark_with_data` | Ratios computed correctly |
| `test_build_niche_benchmark_no_niche_avg` | Returns `None` fields gracefully |
| `test_compute_best_posting_time` | Extracts peak hours from heatmap |
| `test_compute_best_posting_time_empty` | Returns `None` on empty heatmap |
| `test_extract_top_posts` | Sorts by ER, caps at limit |
| `test_extract_top_posts_empty` | Returns empty list |
| `test_derive_growth_stage` | Maps band + trend to stage label |
| `test_content_type_performance_wired` | `content_type_performance` is not `None` in response |
| `test_audience_insights_stub_flag` | `is_estimated` is `True` when stubbed |
| `test_compute_account_health_score_full` | End-to-end: all non-None fields present |

### 4.2 Regression tests
Run existing tests to ensure no breakage:
```bash
pytest backend/app/tests/test_account_analysis_ingestion.py
pytest backend/app/tests/test_account_analysis_result_store.py
pytest backend/app/tests/test_account_analysis_enqueue_rate_limit.py
```

---

## Phase 5: Frontend Alignment

After backend changes, the frontend needs to:

1. **Check `is_estimated`** on `audience_insights` and `audience_demographics` — show "Estimated" badge or hide section
2. **Handle `None` gracefully** for `niche_benchmark`, `audience_insights`, `audience_demographics` — show "Data unavailable" state
3. **Render `growth_stage`** from the new field instead of deriving client-side
4. **Render `top_posts`** in the "Top Performing Posts" section
5. **Render `best_posting_time`** from `ai_summary.best_posting_time`
6. **Render `content_type_performance`** bar chart from the now-populated field

---

## Execution Order

| Step | Description | Files | Est. Effort |
|---|---|---|---|
| 1 | Wire `content_type_performance` | `account_health_engine.py` | 1 line |
| 2 | Populate `niche_benchmark` | `account_health_engine.py` | ~30 lines |
| 3 | Compute `best_posting_time` | `account_health_engine.py` | ~20 lines |
| 4 | Add `growth_stage` field + derivation | `account_models.py`, `account_health_engine.py` | ~25 lines |
| 5 | Add `top_posts` field + helper | `account_models.py`, `account_health_engine.py` | ~40 lines |
| 6 | Add `est_rate_per_post` range | `account_models.py`, `account_health_engine.py` | ~15 lines |
| 7 | Handle stubs (add `is_estimated` or return `None`) | `account_models.py`, `account_health_engine.py` | ~20 lines |
| 8 | Add unit tests | `test_account_health_dashboard.py` | ~150 lines |
| 9 | Run regression tests | — | command |
| 10 | Frontend alignment | `Dashboard.jsx` or equivalent | varies |

**Total backend effort:** ~300 lines of code + tests.
