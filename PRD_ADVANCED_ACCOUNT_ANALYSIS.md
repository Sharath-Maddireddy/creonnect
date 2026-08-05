# PRD: Advanced Account Analysis Dashboard

**Author:** Engineering Team
**Status:** Draft
**Last Updated:** 2025-07-23
**Target:** Production
**Version:** 2.0

---

## 1. Executive Summary

This PRD defines advanced features for the Account Analysis dashboard that complement the existing Trend Recommendations system. While Trend Recommendations answers "What should I post?", this system answers "How am I performing?" and "How can I optimize?"

### 1.1 Vision

Transform the Account Analysis dashboard from a **static reporting tool** into an **intelligent growth platform** that provides predictive insights, optimization recommendations, and competitive intelligence.

### 1.2 Scope

**Included:**
- Predictive Performance Scoring
- Revenue Optimization Calculator
- Risk Assessment Dashboard
- Competitive Benchmarking
- Content Lifecycle Tracking
- Brand Readiness Enhancement
- Audience Deep Dive
- Growth Trajectory Simulation
- Monetization Tracking

**Excluded (Already in Trend Recommendations):**
- Content suggestions/recommendations
- Opportunity scoring for trends
- Reach estimation for content
- Content gap detection
- Daily content insights
- Best posting time derivation

---

## 2. Problem Statement

### 2.1 Current Limitations

| Gap | Impact | User Pain Point |
|-----|--------|-----------------|
| No predictive analytics | Reactive, not proactive | "I don't know if this post will perform well" |
| No competitive context | Isolated analysis | "I don't know how I compare to similar creators" |
| No revenue optimization | Undervalued partnerships | "I don't know what rate to charge" |
| No risk monitoring | Missed issues | "I didn't know my engagement was declining" |
| No growth projections | Unclear trajectory | "I don't know where I'll be in 6 months" |

### 2.2 User Research Insights

Based on creator interviews and support tickets:
- 78% of creators want to know "how they compare" to similar accounts
- 65% struggle with pricing brand partnerships
- 52% want predictive insights before posting
- 48% want early warnings about declining metrics
- 41% want revenue tracking and optimization

---

## 3. Goals and Objectives

| Goal | Success Metric | Target | Timeline |
|------|---------------|--------|----------|
| Enable predictive content decisions | Prediction accuracy | ±20% of actual | Q3 2025 |
| Optimize creator revenue | Revenue increase | +25% average | Q3 2025 |
| Proactive risk management | Issues caught early | 80% detection rate | Q3 2025 |
| Competitive intelligence | User engagement | 40% view benchmarks | Q4 2025 |
| Growth visibility | Projection accuracy | ±25% at 3 months | Q1 2026 |

---

## 4. User Stories

### 4.1 Predictive Analytics Stories

| ID | Story | Priority |
|----|-------|----------|
| US-P1 | As a creator, I want to predict post engagement BEFORE publishing so I can optimize my content | P0 |
| US-P2 | As a creator, I want to see confidence intervals for predictions so I understand uncertainty | P0 |
| US-P3 | As a creator, I want format-specific predictions so I know which type to create | P1 |
| US-P4 | As a creator, I want time-based predictions so I know when to post | P1 |

### 4.2 Revenue Optimization Stories

| ID | Story | Priority |
|----|-------|----------|
| US-R1 | As a creator, I want to know my recommended rate per post so I can price appropriately | P0 |
| US-R2 | As a creator, I want to see rate comparisons by content type so I can maximize earnings | P0 |
| US-R3 | As a creator, I want revenue projections based on deal volume so I can plan finances | P1 |
| US-R4 | As a creator, I want rate optimization tips so I can increase my rates over time | P1 |

### 4.3 Risk Assessment Stories

| ID | Story | Priority |
|----|-------|----------|
| US-K1 | As a creator, I want to see brand safety risks so I can protect partnerships | P0 |
| US-K2 | As a creator, I want engagement decline warnings so I can address issues early | P0 |
| US-K3 | As a creator, I want growth slowdown alerts so I can adjust strategy | P1 |
| US-K4 | As a brand manager, I want risk scores so I can assess creator suitability | P1 |

### 4.4 Competitive Intelligence Stories

| ID | Story | Priority |
|----|-------|----------|
| US-C1 | As a creator, I want to see how I compare to similar accounts so I understand my position | P0 |
| US-C2 | As a creator, I want percentile rankings so I know where I stand | P1 |
| US-C3 | As a creator, I want to see competitor strengths so I can learn from them | P2 |

### 4.5 Content Lifecycle Stories

| ID | Story | Priority |
|----|-------|----------|
| US-L1 | As a creator, I want to see how posts perform over time so I can optimize timing | P1 |
| US-L2 | As a creator, I want content type performance curves so I know when to judge results | P1 |
| US-L3 | As a creator, I want reshare timing recommendations so I can extend content life | P2 |

### 4.6 Brand Readiness Stories

| ID | Story | Priority |
|----|-------|----------|
| US-B1 | As a creator, I want a detailed brand readiness breakdown so I know what to improve | P0 |
| US-B2 | As a brand manager, I want component scores so I can assess specific qualities | P1 |
| US-B3 | As a creator, I want improvement roadmaps so I know how to increase my score | P1 |

### 4.7 Audience Intelligence Stories

| ID | Story | Priority |
|----|-------|----------|
| US-A1 | As a creator, I want to see audience loyalty segments so I understand my true fans | P2 |
| US-A2 | As a creator, I want engagement quality breakdown so I know who matters most | P2 |
| US-A3 | As a creator, I want audience overlap data so I can find collaboration opportunities | P3 |

### 4.8 Growth Projection Stories

| ID | Story | Priority |
|----|-------|----------|
| US-G1 | As a creator, I want growth projections so I can set realistic goals | P2 |
| US-G2 | As a creator, I want scenario modeling so I understand impact of changes | P2 |
| US-G3 | As a creator, I want key lever identification so I know what to focus on | P2 |

### 4.9 Monetization Stories

| ID | Story | Priority |
|----|-------|----------|
| US-M1 | As a creator, I want revenue tracking so I can monitor earnings | P2 |
| US-M2 | As a creator, I want deal performance analysis so I can optimize partnerships | P2 |
| US-M3 | As a creator, I want rate benchmarking so I know if I'm undercharging | P2 |

---

## 5. Functional Requirements

### 5.1 Predictive Performance Score

#### 5.1.1 Description
ML-powered prediction of post performance before publishing based on historical patterns and content attributes.

#### 5.1.2 Input Parameters
```python
{
    "content_type": "REEL | CAROUSEL | IMAGE",
    "posting_time": "ISO datetime",
    "caption_length": int,
    "hashtag_count": int,
    "visual_quality_score": float,  # From S1-S3
    "topic_cluster": str,  # Identified theme
    "audio_name": str | None  # For Reels
}
```

#### 5.1.3 Output Schema
```python
class PerformancePrediction(BaseModel):
    engagement_rate_range: tuple[float, float]  # (min, max)
    confidence_level: float  # 0.0 - 1.0
    expected_reach_range: tuple[int, int]
    virality_probability: float  # 0.0 - 1.0
    format_recommendation: str  # Recommended format
    optimal_posting_window: str  # e.g., "Tuesday 7PM-9PM"
    key_factors: list[str]  # Top 3 factors influencing prediction
```

#### 5.1.4 ML Model Requirements
- **Training Data**: Minimum 10,000 posts with performance metrics
- **Features**: 15-20 engineered features from post attributes
- **Model Type**: Gradient Boosted Trees (XGBoost/LightGBM)
- **Update Frequency**: Weekly retraining
- **Accuracy Target**: ±20% of actual engagement rate

#### 5.1.5 UI Display
```
┌─────────────────────────────────────────────────────────────┐
│ 📊 Predicted Performance                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Engagement Rate     4.2% - 5.8%                          │
│   ████████████████████░░░░░░░░░░  85% confidence           │
│                                                             │
│   Expected Reach      12,000 - 18,000                       │
│   ████████████████████████████░░  High confidence           │
│                                                             │
│   Virality Chance     12%                                  │
│   ████████░░░░░░░░░░░░░░░░░░░░░░  Above average            │
│                                                             │
│   ⚡ Optimal: Tuesday 7PM                                   │
│   📱 Best format: Reel (65% success rate)                   │
│                                                             │
│   KEY FACTORS                                               │
│   1. Reels outperform static by 2.1x in your niche         │
│   2. 7PM posts get 40% more reach than 12PM                 │
│   3. Educational content saves 3x more than lifestyle       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 5.2 Revenue Optimization Calculator

#### 5.2.1 Description
Dynamic rate calculator that suggests optimal pricing based on performance metrics, niche, and market benchmarks.

#### 5.2.2 Calculation Logic
```python
def calculate_recommended_rate(
    engagement_rate: float,
    follower_count: int,
    niche: str,
    brand_safety_score: float,
    content_quality_score: float,
    save_rate: float,
    share_rate: float,
) -> RateRecommendation:
    
    # Base rate from engagement rate
    base_rate = engagement_rate * 10000  # $X per 1% ER
    
    # Follower count multiplier
    follower_multiplier = min(2.0, follower_count / 50000)
    
    # Niche multiplier (from market data)
    niche_multipliers = {
        "fashion": 1.2,
        "beauty": 1.15,
        "tech": 1.1,
        "lifestyle": 1.0,
        "food": 0.95,
        "fitness": 1.05,
    }
    niche_mult = niche_multipliers.get(niche.lower(), 1.0)
    
    # Quality premium
    quality_premium = 1.0
    if brand_safety_score >= 90:
        quality_premium += 0.15
    if content_quality_score >= 80:
        quality_premium += 0.10
    if save_rate >= 0.08:
        quality_premium += 0.10
    
    # Calculate final rate
    recommended_rate = base_rate * follower_multiplier * niche_mult * quality_premium
    
    # Calculate range (±20%)
    rate_min = recommended_rate * 0.8
    rate_max = recommended_rate * 1.2
    
    return RateRecommendation(
        base_rate=base_rate,
        recommended_rate=recommended_rate,
        rate_min=rate_min,
        rate_max=rate_max,
        breakdown=RateBreakdown(...)
    )
```

#### 5.2.3 Output Schema
```python
class RateRecommendation(BaseModel):
    base_rate: float
    recommended_rate: float
    rate_min: float
    rate_max: float
    cpm_estimate: float
    breakdown: RateBreakdown
    optimization_tips: list[str]
    revenue_projections: RevenueProjections

class RateBreakdown(BaseModel):
    engagement_component: float
    follower_component: float
    niche_component: float
    quality_premium: float
    total_adjustments: float

class RevenueProjections(BaseModel):
    monthly_deals_4: tuple[float, float]  # (min, max)
    monthly_deals_8: tuple[float, float]
    annual_potential: tuple[float, float]
```

#### 5.2.4 UI Display
```
┌─────────────────────────────────────────────────────────────┐
│ 💰 Rate Recommendation                                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   RECOMMENDED RATE                                          │
│   ┌─────────────────────────────────────┐                   │
│   │         $550 - $700 / post          │                   │
│   │              (sweet spot)            │                   │
│   └─────────────────────────────────────┘                   │
│                                                             │
│   RATE BREAKDOWN                                            │
│   • Base rate (from ER):           $450                     │
│   • Follower multiplier:           +$90 (1.2x)             │
│   • Fashion niche premium:         +$54 (1.12x)            │
│   • Brand safety bonus:            +$68 (1.15x)            │
│   • Content quality bonus:         +$45 (1.10x)            │
│   • Save rate bonus:               +$45 (1.10x)            │
│                                                             │
│   💡 OPTIMIZATION TIPS                                      │
│   • Your Reels command 40% higher rates than static         │
│   • Increasing saves from 8% → 12% adds ~$100/post         │
│   • Tuesday-Thursday posts increase brand appeal            │
│                                                             │
│   📊 REVENUE PROJECTIONS (Annual)                           │
│   • Conservative (4 deals/mo):   $26,400 - $33,600         │
│   • Moderate (8 deals/mo):       $52,800 - $67,200         │
│   • Aggressive (12 deals/mo):    $79,200 - $100,800        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 5.3 Risk Assessment Dashboard

#### 5.3.1 Description
Proactive monitoring system that identifies and alerts on declining metrics, brand safety issues, and growth risks.

#### 5.3.2 Risk Categories
```python
class RiskCategory(str, Enum):
    BRAND_SAFETY = "brand_safety"
    ENGAGEMENT_DECLINE = "engagement_decline"
    GROWTH_SLOWDOWN = "growth_slowdown"
    CONTENT_PERFORMANCE = "content_performance"
    AUDIENCE_QUALITY = "audience_quality"

class RiskLevel(str, Enum):
    LOW = "low"        # Green - no action needed
    MEDIUM = "medium"  # Yellow - monitor closely
    HIGH = "high"      # Orange - action recommended
    CRITICAL = "critical"  # Red - immediate action required
```

#### 5.3.3 Detection Rules
```python
RISK_RULES = {
    "engagement_decline": {
        "metric": "engagement_rate",
        "window": "30_days",
        "threshold": -0.15,  # 15% decline
        "level": RiskLevel.MEDIUM,
    },
    "save_rate_drop": {
        "metric": "save_rate",
        "window": "30_days",
        "threshold": -0.20,  # 20% decline
        "level": RiskLevel.MEDIUM,
    },
    "follower_growth_slow": {
        "metric": "follower_growth_rate",
        "window": "30_days",
        "threshold": -0.50,  # 50% slowdown
        "level": RiskLevel.MEDIUM,
    },
    "brand_safety_flags": {
        "metric": "flagged_posts_count",
        "window": "90_days",
        "threshold": 2,  # 2+ flagged posts
        "level": RiskLevel.HIGH,
    },
    "low_engagement_posts": {
        "metric": "posts_below_avg_er",
        "window": "30_days",
        "threshold": 0.40,  # 40%+ posts below average
        "level": RiskLevel.MEDIUM,
    },
}
```

#### 5.3.4 Output Schema
```python
class RiskAssessment(BaseModel):
    overall_risk_level: RiskLevel
    risks: list[Risk]
    historical_trend: list[RiskSnapshot]  # Last 90 days
    recommended_actions: list[Action]

class Risk(BaseModel):
    id: str
    category: RiskCategory
    level: RiskLevel
    title: str
    description: str
    metric_affected: str
    current_value: float
    previous_value: float
    change_percentage: float
    detected_at: datetime
    recommended_actions: list[str]

class RiskSnapshot(BaseModel):
    date: date
    overall_level: RiskLevel
    risk_count: int
    category_scores: dict[RiskCategory, float]
```

#### 5.3.5 UI Display
```
┌─────────────────────────────────────────────────────────────┐
│ ⚠️ Risk Assessment                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   OVERALL STATUS: 🟡 MEDIUM RISK (3 issues detected)        │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ RISK TREND (Last 90 days)                           │   │
│   │                                                     │   │
│   │   Low    ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▂▂▂▂▂▃▃▃▃▄▄▄▄       │   │
│   │   Medium ▏                    ▕▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁   │   │
│   │   High   ▏                    ▏                     │   │
│   │         ─────────────────────────────────────────   │   │
│   │         Jan    Feb    Mar    Apr    May    Jun      │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   ACTIVE RISKS                                              │
│                                                             │
│   🟡 Engagement Rate Declining                              │
│      Current: 3.2% | Was: 4.1% (-22% in 30 days)           │
│      Action: Review top-performing posts, increase hooks    │
│                                                             │
│   🟡 Save Rate Drop                                         │
│      Current: 6.5% | Was: 8.2% (-21% in 30 days)           │
│      Action: Create more save-worthy educational content    │
│                                                             │
│   🟢 Brand Safety                                           │
│      Status: Good (0 flagged posts in 90 days)              │
│                                                             │
│   🟢 Growth Rate                                            │
│      Status: Stable (+2.1% month-over-month)                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 5.4 Competitive Benchmarking

#### 5.4.1 Description
Compare creator performance against similar accounts in their niche and follower range.

#### 5.4.2 Segmentation Logic
```python
def identify_competitor_segment(
    follower_count: int,
    niche: str,
    content_mix: dict[str, float],
) -> CompetitorSegment:
    
    # Follower range bucket
    if follower_count < 10000:
        follower_bucket = "micro"  # 1K-10K
    elif follower_count < 50000:
        follower_bucket = "small"  # 10K-50K
    elif follower_count < 100000:
        follower_bucket = "mid"  # 50K-100K
    elif follower_count < 500000:
        follower_bucket = "large"  # 100K-500K
    else:
        follower_bucket = "macro"  # 500K+
    
    return CompetitorSegment(
        follower_bucket=follower_bucket,
        niche=niche,
        content_primary_type=max(content_mix, key=content_mix.get),
    )
```

#### 5.4.3 Benchmark Metrics
```python
class BenchmarkMetrics(BaseModel):
    engagement_rate: PercentileRank
    content_quality: PercentileRank
    posting_frequency: PercentileRank
    brand_safety: PercentileRank
    save_rate: PercentileRank
    share_rate: PercentileRank
    follower_growth: PercentileRank

class PercentileRank(BaseModel):
    value: float
    percentile: float  # 0-100
    segment_average: float
    segment_count: int  # Number of accounts in segment
```

#### 5.4.4 Output Schema
```python
class CompetitiveBenchmark(BaseModel):
    segment: CompetitorSegment
    metrics: BenchmarkMetrics
    overall_percentile: float
    growth_percentile: float
    strengths_vs_peers: list[str]
    opportunities_vs_peers: list[str]
    comparable_accounts: list[ComparableAccount]  # Anonymous or opt-in

class ComparableAccount(BaseModel):
    anonymized_id: str
    follower_range: str
    engagement_rate: float
    content_quality: float
    overlap_percentage: float | None  # If available
```

#### 5.4.5 UI Display
```
┌─────────────────────────────────────────────────────────────┐
│ 🏆 Competitive Benchmark                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   SEGMENT: Fashion creators, 10K-50K followers              │
│   Sample size: 2,847 accounts                               │
│                                                             │
│   YOUR RANKING                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Overall Position:  Top 15% (85th percentile)        │   │
│   │ Growth Rank:       Top 22% (78th percentile)        │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   METRIC COMPARISON                                         │
│                                                             │
│   Engagement Rate                                            │
│   You: 4.8%  ████████████████████░░░░░  Avg: 3.2%          │
│                                                             │
│   Content Quality                                            │
│   You: 85    ████████████████████████░  Avg: 72            │
│                                                             │
│   Posting Frequency                                          │
│   You: 4/wk  ████████████░░░░░░░░░░░░  Avg: 5/wk          │
│                                                             │
│   Brand Safety                                               │
│   You: 100   ████████████████████████░  Avg: 88            │
│                                                             │
│   💪 STRENGTHS VS PEERS                                      │
│   • Content quality beats 78% of similar creators           │
│   • Brand safety is in top 10%                              │
│   • Save rate (11%) exceeds segment average (7%)            │
│                                                             │
│   🎯 OPPORTUNITIES                                          │
│   • Posting frequency below average (4 vs 5/week)           │
│   • Could increase share rate (currently 1.2% vs 1.8%)     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 5.5 Content Lifecycle Tracker

#### 5.5.1 Description
Track post performance over time to understand content decay patterns and optimal timing.

#### 5.5.2 Data Collection
```python
class PostSnapshot(BaseModel):
    post_id: str
    timestamp: datetime
    reach: int
    impressions: int
    likes: int
    comments: int
    saves: int
    shares: int
    engagement_rate: float

# Snapshot frequency:
# - Hourly for first 24 hours
# - Every 6 hours for days 2-7
# - Daily for days 8-30
# - Weekly for days 31-90
```

#### 5.5.3 Performance Curve Analysis
```python
class PerformanceCurve(BaseModel):
    post_id: str
    content_type: str
    peak_time_hours: float  # Hours to reach peak
    peak_reach: int
    decay_rate: float  # Percentage decline per day after peak
    reshare_potential: float  # Score 0-100 for reshare value
    long_tail_score: float  # How well it performs after 7 days

class ContentTypeCurve(BaseModel):
    content_type: str
    average_peak_time: float
    average_decay_rate: float
    typical_lifespan_days: float
    reshare_window_hours: tuple[float, float]  # Optimal reshare timing
```

#### 5.5.4 Output Schema
```python
class ContentLifecycle(BaseModel):
    post_curves: list[PerformanceCurve]
    content_type_benchmarks: list[ContentTypeCurve]
    timing_insights: list[TimingInsight]
    reshare_recommendations: list[ReshareRecommendation]

class TimingInsight(BaseModel):
    insight_type: str  # "peak_timing", "decay_pattern", "reshare_window"
    title: str
    description: str
    actionable_recommendation: str

class ReshareRecommendation(BaseModel):
    post_id: str
    original_post_date: date
    optimal_reshare_time: datetime
    expected_additional_reach: int
    confidence: float
```

#### 5.5.5 UI Display
```
┌─────────────────────────────────────────────────────────────┐
│ 📈 Content Lifecycle                                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   POST PERFORMANCE CURVES                                   │
│                                                             │
│   Reach                                                     │
│   │    ╭────╮                                               │
│   │   ╱      ╲                                              │
│   │  ╱        ╲─────────                                    │
│   │ ╱              Reels (peak 6-12h)                       │
│   │╱             ╱╲                                         │
│   │             ╱  ╲───── Carousels (peak 24-48h)           │
│   │            ╱       ╲                                    │
│   └────────────────────────────────────────────────────────  │
│   0h   6h   12h   24h   48h   72h   7d   14d   30d         │
│                                                             │
│   CONTENT TYPE BENCHMARKS                                   │
│                                                             │
│   Reels                                                     │
│   • Peak time: 6-12 hours post-publish                      │
│   • Decay rate: -15% per day after peak                     │
│   • Lifespan: 3-5 days                                      │
│   • Reshare window: 14-21 days                              │
│                                                             │
│   Carousels                                                 │
│   • Peak time: 24-48 hours post-publish                     │
│   • Decay rate: -8% per day after peak                      │
│   • Lifespan: 7-14 days                                     │
│   • Reshare window: 7-14 days                               │
│                                                             │
│   🎯 ACTIONABLE INSIGHTS                                    │
│   • Don't judge Reel performance before 24 hours            │
│   • Your Carousels have 2x longer lifespan than Reels       │
│   • Consider resharing top Carousel at day 7                │
│                                                             │
│   📋 RESHARE RECOMMENDATIONS                                │
│   • "5 Summer Outfit Ideas" - reshare Wed 7PM               │
│     Expected additional reach: +8,500                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 5.6 Brand Readiness Enhancement

#### 5.6.1 Description
Detailed breakdown of brand partnership readiness with component scores and improvement roadmap.

#### 5.6.2 Component Scores
```python
class BrandReadinessBreakdown(BaseModel):
    overall_score: float  # 0-100
    overall_label: str  # "Highly Marketable", "Marketable", etc.
    
    # Component scores
    content_quality_score: float
    brand_safety_score: float
    engagement_score: float
    consistency_score: float
    niche_clarity_score: float
    audience_quality_score: float
    
    # Market positioning
    percentile_rank: float
    comparable_brands: list[str]  # Brands likely to partner
    
    # Improvement roadmap
    improvement_opportunities: list[ImprovementOpportunity]
    estimated_score_increase: float  # If all improvements implemented

class ImprovementOpportunity(BaseModel):
    area: str
    current_score: float
    potential_increase: float
    difficulty: str  # "easy", "medium", "hard"
    estimated_timeframe: str
    specific_actions: list[str]
```

#### 5.6.3 Scoring Logic
```python
def calculate_brand_readiness(
    pillar_scores: dict[str, float],
    engagement_signals: dict[str, float],
    audience_data: dict[str, Any],
    consistency_metrics: dict[str, float],
) -> BrandReadinessBreakdown:
    
    # Component calculations
    content_quality = pillar_scores.get("content_quality", 0)
    brand_safety = pillar_scores.get("brand_safety", 0)
    engagement = calculate_engagement_score(engagement_signals)
    consistency = pillar_scores.get("consistency", 0)
    niche_clarity = calculate_niche_clarity(pillar_scores, engagement_signals)
    audience_quality = calculate_audience_quality(audience_data)
    
    # Weighted overall score
    weights = {
        "content_quality": 0.20,
        "brand_safety": 0.25,
        "engagement": 0.25,
        "consistency": 0.15,
        "niche_clarity": 0.10,
        "audience_quality": 0.05,
    }
    
    overall = sum([
        content_quality * weights["content_quality"],
        brand_safety * weights["brand_safety"],
        engagement * weights["engagement"],
        consistency * weights["consistency"],
        niche_clarity * weights["niche_clarity"],
        audience_quality * weights["audience_quality"],
    ])
    
    return BrandReadinessBreakdown(
        overall_score=overall,
        overall_label=get_label(overall),
        content_quality_score=content_quality,
        brand_safety_score=brand_safety,
        engagement_score=engagement,
        consistency_score=consistency,
        niche_clarity_score=niche_clarity,
        audience_quality_score=audience_quality,
        improvement_opportunities=identify_improvements(...),
    )
```

#### 5.6.4 UI Display
```
┌─────────────────────────────────────────────────────────────┐
│ 🤝 Brand Readiness Score                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   OVERALL SCORE: 82/100                                     │
│   ┌─────────────────────────────────────┐                   │
│   │  ████████████████████████░░░░░░░░   │                   │
│   │        Highly Marketable            │                   │
│   └─────────────────────────────────────┘                   │
│   Rank: Top 20% in your segment                             │
│                                                             │
│   COMPONENT SCORES                                          │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Content Quality   85/100  ████████████████████░░░░  │   │
│   │ Brand Safety     100/100  ████████████████████████  │   │
│   │ Engagement        78/100  █████████████████░░░░░░░  │   │
│   │ Consistency       72/100  ████████████████░░░░░░░░  │   │
│   │ Niche Clarity     65/100  ██████████████░░░░░░░░░░  │   │
│   │ Audience Quality  70/100  ███████████████░░░░░░░░░  │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   🎯 IMPROVEMENT ROADMAP                                    │
│                                                             │
│   1. Clarify Niche Focus (+10 points)                       │
│      Difficulty: Medium | Timeframe: 2-4 weeks              │
│      Actions:                                               │
│      • Define 2-3 core content themes                       │
│      • Reduce off-niche posts from 30% to 10%               │
│      • Use consistent hashtags                              │
│                                                             │
│   2. Increase Posting Consistency (+5 points)               │
│      Difficulty: Easy | Timeframe: 1-2 weeks                │
│      Actions:                                               │
│      • Post 5x/week instead of 4x                           │
│      • Maintain consistent posting times                    │
│                                                             │
│   📊 BRANDS LIKELY TO PARTNER                               │
│   • Zara, H&M, ASOS, Forever 21, Fashion Nova              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 5.7 Audience Deep Dive

#### 5.7.1 Description
Advanced analysis of audience composition, loyalty, and engagement quality.

#### 5.7.2 Audience Segments
```python
class AudienceSegment(BaseModel):
    segment_name: str
    percentage: float
    characteristics: list[str]
    engagement_pattern: str
    value_to_creator: str  # "high", "medium", "low"

# Segments:
# - Super Fans: Engage with 50%+ posts
# - Loyal Viewers: Watch 3+ posts regularly
# - Casual Viewers: Occasional engagement
# - New Audience: First-time viewers
# - Spam/Bot: Suspicious activity patterns
```

#### 5.7.3 Output Schema
```python
class AudienceDeepDive(BaseModel):
    segments: list[AudienceSegment]
    loyalty_metrics: LoyaltyMetrics
    engagement_quality: EngagementQuality
    audience_insights: list[AudienceInsight]
    collaboration_opportunities: list[CollaborationOpportunity]

class LoyaltyMetrics(BaseModel):
    super_fan_percentage: float
    return_viewer_percentage: float
    average_posts_before_follow: float
    audience_retention_rate: float  # % who still engage after 30 days

class EngagementQuality(BaseModel):
    high_value_engagers: float  # Save + Share + Comment
    passive_viewers: float  # View only
    like_only_engagers: float
    spam_signals: float

class CollaborationOpportunity(BaseModel):
    creator_anonymized_id: str
    overlap_percentage: float
    collaboration_type: str  # "high overlap + complementary", etc.
    potential_reach: int
```

#### 5.7.4 UI Display
```
┌─────────────────────────────────────────────────────────────┐
│ 👥 Audience Deep Dive                                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   AUDIENCE SEGMENTS                                         │
│                                                             │
│   🔥 Super Fans (12%)                                       │
│      Engage with 50%+ of your posts                         │
│      Average 8.2 interactions per month                     │
│      Value: HIGH - Drive algorithm, brand value             │
│                                                             │
│   💚 Loyal Viewers (22%)                                    │
│      Watch 3+ posts regularly                               │
│      Average 3.5 interactions per month                     │
│      Value: MEDIUM - Consistent engagement                  │
│                                                             │
│   👀 Casual Viewers (45%)                                   │
│      Occasional engagement                                  │
│      Average 0.8 interactions per month                     │
│      Value: MEDIUM - Reach potential                        │
│                                                             │
│   🆕 New Audience (18%)                                     │
│      First-time viewers                                     │
│      Conversion opportunity                                 │
│      Value: HIGH - Growth potential                         │
│                                                             │
│   ⚠️ Spam Signals (3%)                                      │
│      Suspicious activity patterns                           │
│      Value: LOW - Ignore                                    │
│                                                             │
│   ENGAGEMENT QUALITY                                        │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ High-Value (Save+Share+Comment):  28%  ████████░░  │   │
│   │ Passive Viewers (View only):      45%  ████████████ │   │
│   │ Like-Only:                        18%  █████░░░░░░  │   │
│   │ Spam/Bot:                          3%  █░░░░░░░░░░  │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   💡 INSIGHTS                                               │
│   • Your super fan rate (12%) beats 85% of creators         │
│   • Consider exclusive content for super fans               │
│   • 45% passive viewers = growth opportunity                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 5.8 Growth Trajectory Simulator

#### 5.8.1 Description
Model different growth scenarios based on current trajectory and potential interventions.

#### 5.8.2 Growth Model
```python
def simulate_growth(
    current_followers: int,
    current_growth_rate: float,
    engagement_rate: float,
    posting_frequency: int,
    content_quality_score: float,
    scenario: str,  # "conservative", "expected", "aggressive"
) -> GrowthProjection:
    
    # Base growth rate adjustments
    scenario_multipliers = {
        "conservative": 0.8,
        "expected": 1.0,
        "aggressive": 1.5,
    }
    
    # Factor in interventions
    interventions = {
        "increase_posting": 0.12,  # +12% growth
        "focus_reels": 0.08,  # +8% growth
        "collaborations": 0.15,  # +15% growth
        "viral_content": 0.25,  # +25% growth (uncertain)
    }
    
    # Calculate monthly growth
    base_monthly_growth = current_growth_rate * scenario_multipliers[scenario]
    
    projections = []
    followers = current_followers
    
    for month in range(1, 7):
        monthly_growth = base_monthly_growth
        followers = int(followers * (1 + monthly_growth))
        projections.append(MonthlyProjection(
            month=month,
            projected_followers=followers,
            growth_rate=monthly_growth,
        ))
    
    return GrowthProjection(
        starting_followers=current_followers,
        projections=projections,
        key_levers=identify_key_levers(...),
    )
```

#### 5.8.3 Output Schema
```python
class GrowthProjection(BaseModel):
    starting_followers: int
    projections: list[MonthlyProjection]
    scenarios: dict[str, list[MonthlyProjection]]
    key_levers: list[GrowthLever]

class MonthlyProjection(BaseModel):
    month: int
    projected_followers: int
    growth_rate: float

class GrowthLever(BaseModel):
    lever_name: str
    impact_percentage: float
    implementation_difficulty: str
    timeframe: str
    specific_actions: list[str]
```

#### 5.8.4 UI Display
```
┌─────────────────────────────────────────────────────────────┐
│ 🚀 Growth Simulator                                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   FOLLOWER GROWTH PROJECTIONS (Next 6 months)               │
│                                                             │
│   70K ┤                                            ╭─ Best  │
│       │                                      ╭────╯         │
│   60K ┤                                ╭────╯  ╭── Expected │
│       │                          ╭────╯  ╭────╯             │
│   50K ┤                    ╭────╯  ╭────╯    ╭── Conserv.  │
│       │              ╭────╯  ╭────╯─────────╯               │
│   48K ┤──────────────╯──────╯                               │
│       │                                                     │
│       └──────────────────────────────────────────────────   │
│        Now   1mo   2mo   3mo   4mo   5mo   6mo             │
│                                                             │
│   SCENARIO BREAKDOWN                                        │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Conservative: 48K → 52K (+8%)  Maintain current     │   │
│   │ Expected:     48K → 58K (+21%) Optimize strategies  │   │
│   │ Best Case:    48K → 68K (+42%) Viral + collabs      │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   🎯 KEY GROWTH LEVERS                                      │
│                                                             │
│   1. Increase Posting Frequency (+12%)                      │
│      Current: 4/week → Target: 6/week                       │
│      Difficulty: Easy | Timeframe: Immediate                │
│                                                             │
│   2. Focus on Reels (+8%)                                   │
│      Current: 60% Reels → Target: 80% Reels                │
│      Difficulty: Easy | Timeframe: 1-2 weeks                │
│                                                             │
│   3. Strategic Collaborations (+15%)                        │
│      Target: 2 collabs/month with similar creators          │
│      Difficulty: Medium | Timeframe: 2-4 weeks              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 5.9 Monetization Tracker

#### 5.9.1 Description
Track revenue, analyze deal performance, and optimize monetization strategy.

#### 5.9.2 Data Model
```python
class BrandDeal(BaseModel):
    deal_id: str
    brand_name: str
    deal_type: str  # "sponsored_reel", "sponsored_post", "story", "package"
    rate: float
    content_type: str
    posting_date: date
    performance_metrics: DealPerformance
    roi_score: float  # Revenue per 1000 impressions

class DealPerformance(BaseModel):
    reach: int
    impressions: int
    engagement_rate: float
    saves: int
    shares: int
    clicks: int  # If trackable
    cost_per_engagement: float
    cost_per_thousand_impressions: float

class MonetizationSummary(BaseModel):
    total_revenue: float
    revenue_by_type: dict[str, float]
    revenue_by_month: list[MonthlyRevenue]
    average_rate: float
    rate_benchmark: RateBenchmark
    optimization_tips: list[str]
    revenue_projection: RevenueProjection
```

#### 5.9.3 Output Schema
```python
class MonetizationDashboard(BaseModel):
    summary: MonetizationSummary
    deal_history: list[BrandDeal]
    performance_analysis: DealPerformanceAnalysis
    rate_optimization: RateOptimization
    revenue_projections: RevenueProjections

class RateBenchmark(BaseModel):
    your_rate: float
    market_average: float
    market_percentile: float
    rate_by_content_type: dict[str, float]

class RateOptimization(BaseModel):
    current_rate: float
    recommended_rate: float
    increase_potential: float
    specific_recommendations: list[str]
```

#### 5.9.4 UI Display
```
┌─────────────────────────────────────────────────────────────┐
│ 💰 Monetization Tracker                                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   REVENUE OVERVIEW (Last 90 days)                           │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Total Revenue:        $3,650                        │   │
│   │ Brand Deals:          $3,200 (4 deals)              │   │
│   │ Affiliate:            $450                          │   │
│   │ Average Rate:         $812/deal                     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   REVENUE BY CONTENT TYPE                                   │
│                                                             │
│   Sponsored Reels     $2,400  ████████████████████  75%    │
│   Sponsored Posts     $600    █████░░░░░░░░░░░░░░░  19%    │
│   Story Mentions      $200    ██░░░░░░░░░░░░░░░░░░   6%    │
│                                                             │
│   RATE BENCHMARKING                                         │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Your Rate:        $812/deal                         │   │
│   │ Market Average:   $650/deal                         │   │
│   │ Your Percentile:  72nd (above average)              │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   💡 OPTIMIZATION RECOMMENDATIONS                           │
│   • Focus on Reel sponsorships (40% higher rates)           │
│   • Your rate is 15% below potential - increase pricing     │
│   • Propose 3-month packages for 20% premium                │
│   • Increase saves to justify higher rates                  │
│                                                             │
│   📈 REVENUE PROJECTION (Next 90 days)                      │
│   • Current pace:     $3,650                                │
│   • Optimized pace:   $5,100 (+40%)                         │
│   • With rate increase: $6,200 (+70%)                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Data Requirements

### 6.1 Input Data

| Data | Source | Required | Freshness |
|------|--------|----------|-----------|
| Post performance metrics | Instagram API | Yes | Real-time |
| Historical post data | Our database | Yes | Daily |
| Audience demographics | Instagram API | No | Weekly |
| Brand deal data | Manual input / API | No | Real-time |
| Market rate benchmarks | Industry data | Yes | Quarterly |
| Competitor data | Instagram API (public) | No | Weekly |

### 6.2 New Database Tables

```sql
-- Post snapshots for lifecycle tracking
CREATE TABLE post_snapshots (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR(255) NOT NULL,
    snapshot_time TIMESTAMP NOT NULL,
    reach INTEGER,
    impressions INTEGER,
    likes INTEGER,
    comments INTEGER,
    saves INTEGER,
    shares INTEGER,
    engagement_rate FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Brand deals for monetization tracking
CREATE TABLE brand_deals (
    id SERIAL PRIMARY KEY,
    creator_id VARCHAR(255) NOT NULL,
    brand_name VARCHAR(255),
    deal_type VARCHAR(50),
    rate DECIMAL(10,2),
    content_type VARCHAR(50),
    posting_date DATE,
    reach INTEGER,
    impressions INTEGER,
    engagement_rate FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Risk assessment history
CREATE TABLE risk_assessments (
    id SERIAL PRIMARY KEY,
    creator_id VARCHAR(255) NOT NULL,
    assessment_date DATE NOT NULL,
    overall_risk_level VARCHAR(20),
    risk_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Competitive benchmarks (aggregated)
CREATE TABLE competitive_benchmarks (
    id SERIAL PRIMARY KEY,
    segment_key VARCHAR(255) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    percentile_25 FLOAT,
    percentile_50 FLOAT,
    percentile_75 FLOAT,
    sample_size INTEGER,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 6.3 New API Endpoints

```
POST /api/account-analysis/{id}/predict
GET  /api/account-analysis/{id}/revenue
POST /api/account-analysis/{id}/revenue
GET  /api/account-analysis/{id}/risks
GET  /api/account-analysis/{id}/competitors
GET  /api/account-analysis/{id}/lifecycle/{post_id}
GET  /api/account-analysis/{id}/brand-readiness-detail
GET  /api/account-analysis/{id}/audience-deep-dive
POST /api/account-analysis/{id}/growth-simulator
GET  /api/account-analysis/{id}/monetization
```

---

## 7. Non-Functional Requirements

### 7.1 Performance

| Endpoint | Response Time (p95) | Payload Size |
|----------|---------------------|--------------|
| /predict | <500ms | <5KB |
| /revenue | <300ms | <10KB |
| /risks | <400ms | <8KB |
| /competitors | <600ms | <15KB |
| /lifecycle/{post_id} | <500ms | <20KB |
| /brand-readiness-detail | <300ms | <8KB |
| /audience-deep-dive | <500ms | <12KB |
| /growth-simulator | <1s | <10KB |
| /monetization | <400ms | <15KB |

### 7.2 Scalability

- Support 10,000+ concurrent dashboard users
- Handle 1M+ post snapshots per day
- Process 100K+ predictions per hour
- Store 90 days of hourly snapshots per post

### 7.3 Reliability

- 99.9% uptime for all endpoints
- Graceful degradation if ML model unavailable
- Fallback to heuristic calculations if needed
- No data loss for snapshots (at-least-once delivery)

### 7.4 Security

- All data encrypted at rest and in transit
- Role-based access control for revenue data
- Anonymize competitor data unless explicitly shared
- GDPR compliance for audience data

---

## 8. UI/UX Requirements

### 8.1 Design Principles

1. **Progressive Disclosure**: Show summary first, details on demand
2. **Actionable Insights**: Every insight must have a clear action
3. **Visual Clarity**: Use charts and gauges for metrics
4. **Consistent Patterns**: Follow existing dashboard design system

### 8.2 Responsive Design

- Desktop-first (existing pattern)
- Tablet support (768px+)
- Mobile view for key metrics only

### 8.3 Accessibility

- WCAG 2.1 AA compliance
- Screen reader support for all charts
- Keyboard navigation
- Color-blind friendly palettes

---

## 9. Success Metrics

| Feature | Metric | Target | Measurement |
|---------|--------|--------|-------------|
| Predictive Score | Prediction accuracy | ±20% of actual | A/B testing |
| Revenue Calculator | Rate adoption | 40% update rates | Analytics |
| Risk Assessment | Early detection | 80% of issues | Historical analysis |
| Competitive Benchmark | User engagement | 40% view | Analytics |
| Content Lifecycle | Timing optimization | 25% adjust timing | User behavior |
| Brand Readiness | Score improvement | +10 points avg | Longitudinal study |
| Audience Deep Dive | Insight usage | 30% take action | Surveys |
| Growth Simulator | Projection accuracy | ±25% at 3 months | Validation |
| Monetization | Revenue increase | +25% average | Revenue tracking |

---

## 10. Dependencies

| Dependency | Status | Risk | Mitigation |
|------------|--------|------|------------|
| Instagram Graph API | Active | Medium | Rate limiting, caching |
| ML Model Training | Pending | High | Start with heuristic fallback |
| Market Rate Data | Partial | Medium | Partner with industry data providers |
| Competitor Data | Limited | High | Public data only, respect ToS |
| Historical Data | Available | Low | Already in database |

---

## 11. Out of Scope

| Feature | Rationale | Future Phase |
|---------|-----------|--------------|
| Real-time competitor tracking | Privacy concerns, API limits | Phase 4 |
| Cross-platform analytics | Focus on Instagram first | Phase 5 |
| Automated brand outreach | High complexity, legal review | Phase 5 |
| Revenue forecasting with ML | Need more historical data | Phase 4 |
| Audience purchase intent | Requires additional data sources | Phase 5 |

---

## 12. Implementation Timeline

### Phase 1: Foundation (Q3 2025) - 5 weeks
- Predictive Performance Score (ML model v1)
- Revenue Optimization Calculator
- Risk Assessment Dashboard

### Phase 2: Intelligence (Q4 2025) - 6 weeks
- Competitive Benchmarking
- Content Lifecycle Tracker
- Brand Readiness Enhancement

### Phase 3: Deep Analysis (Q1 2026) - 8 weeks
- Audience Deep Dive
- Growth Trajectory Simulator
- Monetization Tracker

### Phase 4: Network Effects (Q2 2026) - 6 weeks
- Audience Overlap Analysis
- Cross-creator insights
- Industry benchmarks

---

## 13. Open Questions

| # | Question | Owner | Status |
|---|----------|-------|--------|
| 1 | Should predictive scores be shown to brands? | Product | Open |
| 2 | How to handle competitors who opt out of benchmarking? | Legal | Open |
| 3 | Should revenue data be encrypted separately? | Security | Open |
| 4 | What confidence threshold for predictions? | ML | Open |
| 5 | How to source market rate data reliably? | Business | Open |

---

## 14. Appendix

### 14.1 Glossary

| Term | Definition |
|------|------------|
| ER | Engagement Rate |
| CPM | Cost Per Mille (1000 impressions) |
| Super Fan | User who engages with 50%+ of posts |
| Long Tail | Content performance after initial peak |
| Opportunity Score | 0-100 score predicting trend fit |

### 14.2 Related Documents

- PRD: AI Account Analysis Dashboard (v1)
- PRD: Trend Recommendations System
- Implementation Plan: Account Health Engine
- API Documentation: Account Analysis Endpoints

---

**Document Version History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-07-23 | Engineering | Initial draft |
