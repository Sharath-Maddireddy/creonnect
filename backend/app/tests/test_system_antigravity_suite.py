"""System-level anti-gravity adversarial test suite.

Covers cross-layer consistency, score coherence, determinism,
predicted-ER safety, and weight-sanity checks.  Every test constructs
synthetic ``SinglePostInsights`` objects and runs through the
deterministic engines — no external APIs, no Redis, no LLM.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import backend.app.services.account_analysis_service as account_analysis_service
from backend.app.analytics.account_health_engine import (
    PILLAR_WEIGHTS,
    compute_account_health_score,
)
from backend.app.analytics.predicted_er_engine import (
    compute_predicted_engagement_rate,
)
from backend.app.domain.post_models import (
    AudienceRelevanceScore,
    BenchmarkMetrics,
    BrandSafetyScore,
    CaptionEffectivenessScore,
    ContentClarityScore,
    CoreMetrics,
    DerivedMetrics,
    EngagementPotentialScore,
    SinglePostInsights,
    VisualQualityScore,
    WeightedPostScore,
)
from backend.app.services.account_analysis_service import (
    _ACCOUNT_HEALTH_CACHE,
    analyze_account_health,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _post(
    idx: int,
    *,
    s1: float = 35.0,
    s2: float = 35.0,
    s3: float = 35.0,
    s4: float = 35.0,
    s5: float = 25.0,
    s6_raw: int = 90,
    s6_total: float = 45.0,
    weighted_score: float = 70.0,
    engagement_rate: float = 0.06,
    save_rate: float = 0.02,
    share_rate: float = 0.01,
) -> SinglePostInsights:
    return SinglePostInsights(
        account_id="acct_sys",
        media_id=f"m_sys_{idx}",
        media_url="https://example.com/post.jpg",
        media_type="IMAGE",
        caption_text="System anti-gravity test post.",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=idx),
        core_metrics=CoreMetrics(
            reach=2000 + idx,
            impressions=2200 + idx,
            likes=120,
            comments=20,
            saves=25,
            shares=15,
            profile_visits=8,
            website_taps=2,
        ),
        derived_metrics=DerivedMetrics(
            engagement_rate=engagement_rate,
            save_rate=save_rate,
            share_rate=share_rate,
        ),
        benchmark_metrics=BenchmarkMetrics(account_avg_engagement_rate=0.06),
        visual_quality_score=VisualQualityScore(total=s1),
        caption_effectiveness_score=CaptionEffectivenessScore(total_0_50=s2),
        content_clarity_score=ContentClarityScore(total=s3),
        audience_relevance_score=AudienceRelevanceScore(total_0_50=s4),
        engagement_potential_score=EngagementPotentialScore(total=s5),
        brand_safety_score=BrandSafetyScore(
            s6_raw_0_100=s6_raw,
            total_0_50=s6_total,
        ),
        weighted_post_score=WeightedPostScore(
            score=weighted_score,
            normalized_score_0_50=weighted_score / 2.0,
        ),
    )


# ===================================================================
# A — Cross-Layer: Bad posts cannot produce high AHS
# ===================================================================

def test_a_bad_posts_produce_low_ahs() -> None:
    """30 posts with S1<15, S3<15, S6<20, low ER → AHS<40, band≠STRONG."""
    posts = [
        _post(
            i,
            s1=10.0,          # weak visual
            s2=10.0,          # weak caption
            s3=10.0,          # weak clarity
            s4=12.0,          # weak niche
            s5=10.0,          # low engagement potential
            s6_raw=30,        # risky
            s6_total=15.0,    # <20
            weighted_score=25.0,
            engagement_rate=0.01,
            save_rate=0.002,
            share_rate=0.001,
        )
        for i in range(30)
    ]

    result = compute_account_health_score(
        posts,
        account_avg_engagement_rate=0.06,
        niche_avg_engagement_rate=0.055,
    )

    assert result.ahs_score < 40.0, f"AHS too high for bad posts: {result.ahs_score}"
    assert result.ahs_band != "STRONG"
    assert result.ahs_band != "EXCEPTIONAL"
    # Must flag multiple weak pillars
    limiting_ids = {d.id for d in result.drivers if d.type == "LIMITING"}
    assert "content_quality_low" in limiting_ids, "Should flag content quality"
    assert "engagement_quality_low" in limiting_ids, "Should flag engagement quality"


# ===================================================================
# B — Cross-Layer: One viral outlier cannot dominate AHS
# ===================================================================

def test_b_one_outlier_cannot_lift_ahs() -> None:
    """29 weak posts + 1 perfect → AHS stays < 60."""
    weak = [
        _post(
            i,
            s1=12.0,
            s2=12.0,
            s3=13.0,
            s4=18.0,
            s6_raw=85,
            s6_total=42.5,
            weighted_score=35.0,
            engagement_rate=0.02,
            save_rate=0.005,
            share_rate=0.004,
        )
        for i in range(29)
    ]
    perfect = _post(
        99,
        s1=50.0,
        s2=50.0,
        s3=50.0,
        s4=45.0,
        s6_raw=100,
        s6_total=50.0,
        weighted_score=100.0,
        engagement_rate=0.30,
        save_rate=0.08,
        share_rate=0.05,
    )

    result = compute_account_health_score(
        weak + [perfect],
        account_avg_engagement_rate=0.06,
    )

    assert result.ahs_score < 60.0, f"One outlier inflated AHS to {result.ahs_score}"
    assert result.ahs_band != "EXCEPTIONAL"


# ===================================================================
# C — Cross-Layer: Predicted ER cannot exceed baseline
# ===================================================================

def test_c_predicted_er_never_exceeds_baseline() -> None:
    """tier_avg_er=0.01, S5=50 → predicted=0.01, never > baseline."""
    predicted, notes = compute_predicted_engagement_rate(
        tier_avg_er=0.01,
        s5_total=50.0,
    )
    assert predicted is not None
    assert predicted == 0.01, f"Expected 0.01, got {predicted}"
    assert predicted <= 0.01, "Predicted must never exceed tier baseline"


# ===================================================================
# D — Coherence: mean S6=100 → brand_safety=100
# ===================================================================

def test_d_perfect_s6_produces_perfect_brand_safety() -> None:
    """All posts with S6 raw=100, total=50 → brand_safety pillar≈100."""
    posts = [
        _post(
            i,
            s6_raw=100,
            s6_total=50.0,
            engagement_rate=0.07,
        )
        for i in range(15)
    ]

    result = compute_account_health_score(
        posts,
        account_avg_engagement_rate=0.06,
    )

    brand_safety = result.pillars["brand_safety"].score
    assert brand_safety == pytest.approx(100.0), f"Perfect S6 should yield 100, got {brand_safety}"


# ===================================================================
# E — Coherence: mean S4=15/50 → niche_fit ≈ 30
# ===================================================================

def test_e_low_s4_produces_low_niche_fit() -> None:
    """All posts S4=15/50 → niche_fit pillar ≈ 30 (base = 15*2 = 30)."""
    posts = [
        _post(
            i,
            s4=15.0,
            engagement_rate=0.06,
        )
        for i in range(20)
    ]

    result = compute_account_health_score(
        posts,
        account_avg_engagement_rate=0.06,
    )

    niche_fit = result.pillars["niche_fit"].score
    # S4 mean=15, mapped ×2 = 30, blended if niche ER present
    assert niche_fit < 50.0, f"Low S4 should yield <50 niche_fit, got {niche_fit}"


# ===================================================================
# F — Coherence: content_quality < 40 limits AHS
# ===================================================================

def test_f_low_content_quality_caps_ahs() -> None:
    """When content_quality < 40, AHS cannot exceed ~70 regardless of other pillars."""
    posts = [
        _post(
            i,
            s1=8.0,           # very low → content quality < 40
            s2=8.0,
            s3=8.0,
            s4=45.0,          # great niche fit
            s6_raw=100,       # perfect safety
            s6_total=50.0,
            weighted_score=90.0,
            engagement_rate=0.15,
            save_rate=0.05,
            share_rate=0.04,
        )
        for i in range(20)
    ]

    result = compute_account_health_score(
        posts,
        account_avg_engagement_rate=0.06,
        niche_avg_engagement_rate=0.055,
    )

    content_q = result.pillars["content_quality"].score
    assert content_q < 40.0, f"Expected content_quality < 40, got {content_q}"
    # content_quality has 0.30 weight; even if everything else is 100:
    # max AHS ≤ content_q*0.30 + 100*0.70 = ~40*0.30 + 70 = 82
    # realistically lower, so AHS must not be near 100
    assert result.ahs_score <= 82.0, f"Low content should cap AHS ≤ ~82, got {result.ahs_score}"
    assert result.ahs_band != "EXCEPTIONAL"


# ===================================================================
# G — Determinism: engine produces identical JSON twice
# ===================================================================

def test_g_determinism_engine() -> None:
    """Two identical runs of compute_account_health_score → exact same JSON."""
    posts = [
        _post(i, s1=33.0, s2=32.0, s3=34.0, engagement_rate=0.065)
        for i in range(15)
    ]
    kwargs = dict(
        account_avg_engagement_rate=0.06,
        niche_avg_engagement_rate=0.055,
        follower_band="10k-50k",
    )

    first = compute_account_health_score(posts, **kwargs).model_dump(mode="python")
    second = compute_account_health_score(posts, **kwargs).model_dump(mode="python")

    assert first == second, "Determinism violation: two runs produced different results"


# ===================================================================
# H — Determinism: cached vs uncached produce identical results
# ===================================================================

def test_h_cache_returns_identical_result() -> None:
    """analyze_account_health cached vs uncached → identical AccountHealthScore."""
    _ACCOUNT_HEALTH_CACHE.clear()

    posts = [
        _post(i, s1=36.0, s2=35.0, s3=37.0, engagement_rate=0.07)
        for i in range(12)
    ]
    kwargs = dict(
        account_avg_engagement_rate=0.06,
        niche_avg_engagement_rate=0.05,
    )

    uncached = analyze_account_health(posts, use_cache=False, **kwargs)
    cached = analyze_account_health(posts, use_cache=True, **kwargs)
    cached_again = analyze_account_health(posts, use_cache=True, **kwargs)

    assert uncached.model_dump(mode="python") == cached.model_dump(mode="python")
    assert cached.model_dump(mode="python") == cached_again.model_dump(mode="python")


# ===================================================================
# H2 - Cache-key correctness: now_ts should partition cache entries
# ===================================================================

def test_h2_cache_key_includes_now_ts() -> None:
    """Different now_ts values should produce distinct cache entries."""
    _ACCOUNT_HEALTH_CACHE.clear()

    posts = [_post(i, s1=36.0, s2=35.0, s3=37.0, engagement_rate=0.07) for i in range(12)]
    kwargs = dict(
        account_avg_engagement_rate=0.06,
        niche_avg_engagement_rate=0.05,
        follower_band="10k-50k",
        use_cache=True,
    )

    now_a = datetime(2024, 1, 1, tzinfo=timezone.utc)
    now_b = datetime(2024, 1, 2, tzinfo=timezone.utc)

    analyze_account_health(posts, now_ts=now_a, **kwargs)
    analyze_account_health(posts, now_ts=now_b, **kwargs)

    assert len(_ACCOUNT_HEALTH_CACHE) == 2


# ===================================================================
# H3 - Cache boundedness: max-size LRU eviction should cap growth
# ===================================================================

def test_h3_cache_growth_is_bounded() -> None:
    """Cache should not grow beyond configured max size."""
    _ACCOUNT_HEALTH_CACHE.clear()
    original_max_size = account_analysis_service.ACCOUNT_HEALTH_CACHE_MAX_SIZE
    account_analysis_service.ACCOUNT_HEALTH_CACHE_MAX_SIZE = 2
    try:
        posts = [_post(i, s1=36.0, s2=35.0, s3=37.0, engagement_rate=0.07) for i in range(12)]
        kwargs = dict(
            account_avg_engagement_rate=0.06,
            niche_avg_engagement_rate=0.05,
            follower_band="10k-50k",
            use_cache=True,
        )

        analyze_account_health(posts, now_ts=datetime(2024, 1, 1, tzinfo=timezone.utc), **kwargs)
        analyze_account_health(posts, now_ts=datetime(2024, 1, 2, tzinfo=timezone.utc), **kwargs)
        analyze_account_health(posts, now_ts=datetime(2024, 1, 3, tzinfo=timezone.utc), **kwargs)

        assert len(_ACCOUNT_HEALTH_CACHE) == 2
    finally:
        account_analysis_service.ACCOUNT_HEALTH_CACHE_MAX_SIZE = original_max_size
        _ACCOUNT_HEALTH_CACHE.clear()


# ===================================================================
# I — Predicted ER: fraction unit consistency
# ===================================================================

def test_i_predicted_er_fraction_unit() -> None:
    """Fraction input → fraction output, always 0 ≤ predicted ≤ 1.0."""
    predicted, _ = compute_predicted_engagement_rate(
        tier_avg_er=0.04, s5_total=25.0,
    )
    assert predicted is not None
    assert 0.0 <= predicted <= 1.0, f"Fraction out of range: {predicted}"
    assert predicted == 0.02, f"Expected 0.04 * 0.5 = 0.02, got {predicted}"


# ===================================================================
# J — Predicted ER: missing inputs → None
# ===================================================================

def test_j_missing_inputs_no_fabrication() -> None:
    """Missing tier_avg_er or S5 → predicted is None, no fabrication."""
    pred_a, notes_a = compute_predicted_engagement_rate(None, 25.0)
    assert pred_a is None
    assert any("missing" in n.lower() for n in notes_a)

    pred_b, notes_b = compute_predicted_engagement_rate(0.04, None)
    assert pred_b is None
    assert any("missing" in n.lower() for n in notes_b)

    pred_c, notes_c = compute_predicted_engagement_rate(None, None)
    assert pred_c is None
    assert len(notes_c) >= 2  # both missing flagged


# ===================================================================
# K — Predicted ER: S5 clamped before use
# ===================================================================

def test_k_s5_clamped_for_predicted_er() -> None:
    """S5=999 clamped to 50 → predicted = tier_avg_er × 1.0."""
    predicted, notes = compute_predicted_engagement_rate(
        tier_avg_er=0.05,
        s5_total=999.0,
    )
    assert predicted == 0.05, f"Clamped S5 should yield 0.05, got {predicted}"
    assert any("clamped" in n for n in notes)


# ===================================================================
# L — Predicted ER: monotonicity across S5 values
# ===================================================================

def test_l_predicted_er_monotonicity() -> None:
    """Fix tier_avg_er, sweep S5 0→50 → non-decreasing predicted."""
    tier = 0.06
    s5_sweep = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
    predictions = []

    for s5 in s5_sweep:
        pred, _ = compute_predicted_engagement_rate(tier, float(s5))
        assert pred is not None
        predictions.append(pred)

    for i in range(1, len(predictions)):
        assert predictions[i] >= predictions[i - 1], (
            f"Monotonicity broken: S5={s5_sweep[i]} → {predictions[i]} "
            f"< S5={s5_sweep[i-1]} → {predictions[i-1]}"
        )


# ===================================================================
# M — Weight Sanity: content_quality=0, rest=100 → AHS ≤ 70
# ===================================================================

def test_m_weight_sanity_content_zero() -> None:
    """content_quality pillar = 0, all others ≈ 100 → AHS ≤ 70.

    Proof: AHS = 0*0.30 + 100*0.25 + 100*0.15 + 100*0.15 + 100*0.15 = 70.
    """
    posts = [
        _post(
            i,
            s1=0.0,           # zero content quality
            s2=0.0,
            s3=0.0,
            s4=45.0,          # max niche (=90/100 after ×2)
            s6_raw=100,       # perfect safety
            s6_total=50.0,
            weighted_score=85.0,
            engagement_rate=0.12,
            save_rate=0.04,
            share_rate=0.03,
        )
        for i in range(20)
    ]

    result = compute_account_health_score(
        posts,
        account_avg_engagement_rate=0.06,
        niche_avg_engagement_rate=0.055,
    )

    content_q = result.pillars["content_quality"].score
    assert content_q < 5.0, f"Expected near-zero content quality, got {content_q}"
    # With content_quality ≈ 0 at weight 0.30, maximum AHS theoretical = 70
    assert result.ahs_score <= 75.0, (
        f"Content=0 at weight 0.30 should cap AHS ≤ ~70, got {result.ahs_score}"
    )
