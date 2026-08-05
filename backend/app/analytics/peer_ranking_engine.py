"""Peer ranking engine that generates AI-powered percentile rankings for a creator.

Uses a single LLM call to produce competitive rankings against the Indian
Instagram creator market, with a deterministic fallback when the LLM is
unavailable or returns invalid output.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

from backend.app.ai.llm_client import LLMClient
from backend.app.domain.account_models import (
    AudienceScorePercentile,
    PeerRankingMetric,
    TierThreshold,
)
from backend.app.domain.post_models import SinglePostInsights
from backend.app.utils.logger import logger
from backend.app.utils.number_utils import safe_float_or as _safe_float

# ── Prompt template ──────────────────────────────────────────────────────────

_RANKING_SYSTEM_PROMPT = """
You are an Instagram growth expert specializing in the Indian creator market.
Given a creator's real metrics, estimate their percentile rank compared to
Indian Instagram creators in the SAME follower tier.

Return ONLY valid TOON (Token-Oriented Object Notation).  No JSON, no braces,
no commentary.  Use 2-space indentation for nesting.  List items start with "- ".

Required structure:
rankings
  - metric_key
    metric_label
    creator_value
    percentile
    tier_label
    cohort_average
    thresholds
      - label
        range_label
        upper_bound
        lower_bound
        is_creator_tier
audience_score
  score
  percentile
  tier_label
  cohort_average
  thresholds
    - label
      range_label
      upper_bound
      lower_bound
      is_creator_tier
best_stat_key
comparison_context

Rules:
- percentile MUST be 0-100 (higher = better).
- thresholds MUST be exactly 4 buckets: Top 5%, Top 10%, Top 20%, Bottom 80%. Each threshold MUST include an is_creator_tier boolean.
- upper_bound can be null for the top bucket; lower_bound can be null for the bottom.
- tier_label is a human-readable string like "Top 10%" or "Above Average".
- cohort_average is the typical value for this follower tier in the Indian market.
- Do NOT invent unrealistic numbers.  Base estimates on realistic Indian Instagram
  benchmarks for the given tier.
- best_stat_key: which metric_key (reach, engagement_rate, impressions, save_rate,
  audience_relevance) ranks highest for this creator.
- comparison_context: one sentence about who we're comparing against.
""".strip()


def _follower_band_label(follower_count: int | None) -> str:
    """Map a raw follower count to a human-readable tier label.

    Uses the same bands as dashboard_service._resolve_follower_band for consistency.
    """
    if follower_count is None or follower_count < 0:
        return "Unknown tier"
    if follower_count < 10_000:
        return "0-10k"
    if follower_count < 100_000:
        return "10k-100k"
    if follower_count < 1_000_000:
        return "100k-1M"
    return "1M+"


# ── Helpers for extracting metrics from processed posts ──────────────────────

def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _extract_post_metrics(
    posts: list[SinglePostInsights],
) -> dict[str, float]:
    """Extract average numeric metrics from a list of processed posts."""
    reach_vals: list[float] = []
    er_vals: list[float] = []
    imp_vals: list[float] = []
    save_rate_vals: list[float] = []
    s4_vals: list[float] = []

    for post in posts:
        core = post.core_metrics
        reach = _safe_float(getattr(core, "reach", None))
        impressions = _safe_float(getattr(core, "impressions", None))
        likes = _safe_float(getattr(core, "likes", None))
        comments = _safe_float(getattr(core, "comments", None))
        shares = _safe_float(getattr(core, "shares", None))
        saves = _safe_float(getattr(core, "saves", None))

        if reach and reach > 0:
            reach_vals.append(reach)
            save_rate_vals.append((saves / reach) * 100.0 if saves else 0.0)
            # Prefer the already-computed derived_metrics.engagement_rate
            derived_er = getattr(post, "derived_metrics", None)
            if derived_er is not None and getattr(derived_er, "engagement_rate", None) is not None:
                er_val = float(derived_er.engagement_rate)
                # Stored rates are decimal ratios; values >= 0.5 are already
                # percentage-like outliers and should not be scaled again.
                er_vals.append(er_val * 100.0 if er_val < 0.5 else er_val)
            else:
                engagement = likes + comments + shares + saves
                er_vals.append((engagement / reach) * 100.0 if engagement else 0.0)

        if impressions and impressions > 0:
            imp_vals.append(impressions)

        s4 = getattr(post.audience_relevance_score, "s4_raw_0_100", None)
        if s4 is not None:
            s4_vals.append(float(s4))

    return {
        "avg_reach": _mean(reach_vals),
        "avg_er": _mean(er_vals),
        "avg_impressions": _mean(imp_vals),
        "avg_save_rate": _mean(save_rate_vals),
        "avg_s4": _mean(s4_vals),
    }


# ── Deterministic fallback ───────────────────────────────────────────────────

def _build_deterministic_rankings(
    metrics: dict[str, float],
    follower_count: int | None,
) -> dict[str, Any]:
    """Produce a fallback rankings payload using simple heuristics.

    Uses a log-transformed percentile approach to handle skewed distributions
    better than a naive linear formula.
    """
    # Approximate tier averages for Indian Instagram. Reach and impressions
    # scale with audience size; engagement and quality metrics remain comparable.
    band = _follower_band_label(follower_count)
    tier_averages_by_band: dict[str, dict[str, float]] = {
        "0-10k": {"avg_reach": 2_500.0, "avg_impressions": 3_200.0},
        "10k-100k": {"avg_reach": 8_000.0, "avg_impressions": 10_000.0},
        "100k-1M": {"avg_reach": 35_000.0, "avg_impressions": 45_000.0},
        "1M+": {"avg_reach": 100_000.0, "avg_impressions": 130_000.0},
    }
    tier_averages: dict[str, float] = {
        "avg_er": 3.5,
        "avg_save_rate": 1.2,
        "avg_s4": 50.0,
        **tier_averages_by_band.get(band, tier_averages_by_band["0-10k"]),
    }
    tier_labels: dict[str, str] = {
        "avg_reach": "Reach",
        "avg_er": "Engagement Rate",
        "avg_impressions": "Impressions",
        "avg_save_rate": "Save Rate",
        "avg_s4": "Audience Relevance",
    }
    metric_keys = ["avg_reach", "avg_er", "avg_impressions", "avg_save_rate", "avg_s4"]

    rankings: list[dict[str, Any]] = []
    for key in metric_keys:
        actual = metrics.get(key, 0.0)
        tier_avg = tier_averages.get(key, 1.0)
        # Log-transform for better percentile estimation under skewed distributions
        log_actual = math.log(max(0.01, actual) + 1)
        log_tier = math.log(tier_avg + 1)
        raw_pct = 50.0 + ((log_actual - log_tier) / max(0.01, log_tier)) * 20.0
        percentile = max(5.0, min(99.0, raw_pct))

        tier_label = (
            "Top 5%" if percentile >= 95 else "Top 10%" if percentile >= 90 else "Top 20%" if percentile >= 80 else "Bottom 80%"
        )

        thresholds: list[dict[str, Any]] = [
            {
                "label": "Top 5%",
                "range_label": f">{tier_avg * 2.0:.0f}",
                "upper_bound": None,
                "lower_bound": round(tier_avg * 2.0, 1),
                "is_creator_tier": actual >= tier_avg * 2.0,
            },
            {
                "label": "Top 10%",
                "range_label": f"{tier_avg * 1.5:.0f}-{tier_avg * 2.0:.0f}",
                "upper_bound": round(tier_avg * 2.0, 1),
                "lower_bound": round(tier_avg * 1.5, 1),
                "is_creator_tier": tier_avg * 1.5 <= actual < tier_avg * 2.0,
            },
            {
                "label": "Top 20%",
                "range_label": f"{tier_avg * 1.2:.0f}-{tier_avg * 1.5:.0f}",
                "upper_bound": round(tier_avg * 1.5, 1),
                "lower_bound": round(tier_avg * 1.2, 1),
                "is_creator_tier": tier_avg * 1.2 <= actual < tier_avg * 1.5,
            },
            {
                "label": "Bottom 80%",
                "range_label": f"<{tier_avg * 1.2:.0f}",
                "upper_bound": round(tier_avg * 1.2, 1),
                "lower_bound": None,
                "is_creator_tier": actual < tier_avg * 1.2,
            },
        ]

        rankings.append({
            "metric_key": key.replace("avg_", ""),
            "metric_label": tier_labels.get(key, key),
            "creator_value": round(actual, 2),
            "percentile": round(percentile, 1),
            "tier_label": tier_label,
            "cohort_average": round(tier_avg, 1),
            "thresholds": thresholds,
        })

    # Audience score — s4 is on a 0-50 scale, normalize to 0-100 percentile.
    raw_s4 = metrics.get("avg_s4", 25.0)
    audience_score_pct = min((raw_s4 / 50.0) * 100.0, 99.9)
    audience_tier = (
        "Top 5%" if audience_score_pct >= 95 else "Top 10%" if audience_score_pct >= 90 else "Top 20%" if audience_score_pct >= 80 else "Bottom 80%"
    )

    best_stat_key = max(metric_keys, key=lambda k: metrics.get(k, 0.0)).replace("avg_", "")
    return {
        "rankings": rankings,
        "audience_score": {
            "score": round(audience_score_pct, 1),
            "percentile": round(audience_score_pct, 1),
            "tier_label": audience_tier,
            "cohort_average": 55.0,
            "thresholds": [
                {"label": "Top 5%", "range_label": ">90", "upper_bound": None, "lower_bound": 90, "is_creator_tier": audience_score_pct >= 90},
                {"label": "Top 10%", "range_label": "80-90", "upper_bound": 90, "lower_bound": 80, "is_creator_tier": 80 <= audience_score_pct < 90},
                {"label": "Top 20%", "range_label": "60-80", "upper_bound": 80, "lower_bound": 60, "is_creator_tier": 60 <= audience_score_pct < 80},
                {"label": "Bottom 80%", "range_label": "<60", "upper_bound": 60, "lower_bound": None, "is_creator_tier": audience_score_pct < 60},
            ],
        },
        "best_stat_key": best_stat_key,
        "comparison_context": (
            f"We compare your stats with Indian creators with similar audience size "
            f"({band}). Percentiles are estimated using AI-based benchmarks."
        ),
        "fallback_used": True,
    }


# ── Main public API ──────────────────────────────────────────────────────────


def _parse_ranking_response(raw: str) -> dict[str, Any] | None:
    """Attempt to parse the LLM response as JSON first, then TOON."""
    # Try JSON first (many models default to JSON even when told otherwise)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "rankings" in parsed:
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # Try TOON
    try:
        from backend.app.ai import toon
        parsed = toon.loads(raw)
        if isinstance(parsed, dict) and "rankings" in parsed:
            return parsed
    except Exception:
        pass

    return None


def _validate_ranking_response(parsed: dict[str, Any]) -> bool:
    """Return True when the LLM response passes basic sanity checks."""
    rankings = parsed.get("rankings")
    if not isinstance(rankings, list) or not rankings:
        return False
    for rank in rankings:
        if not isinstance(rank, dict):
            return False
        if "percentile" not in rank or "metric_key" not in rank:
            return False
        pct = rank.get("percentile")
        if not isinstance(pct, (int, float)) or pct < 0 or pct > 100:
            return False
    audience = parsed.get("audience_score")
    if not isinstance(audience, dict):
        return False
    audience_pct = audience.get("percentile")
    if not isinstance(audience_pct, (int, float)):
        return False
    return True


def _build_ranking_prompt_user(
    metrics: dict[str, float],
    follower_count: int | None,
    post_count: int,
) -> str:
    band = _follower_band_label(follower_count)
    return json.dumps({
        "creator_metrics": {
            "post_count": post_count,
            "follower_count": follower_count or 0,
            "follower_band": band,
            "average_reach": round(metrics["avg_reach"], 1),
            "average_engagement_rate_pct": round(metrics["avg_er"], 2),
            "average_impressions": round(metrics["avg_impressions"], 1),
            "average_save_rate_pct": round(metrics["avg_save_rate"], 2),
            "average_audience_relevance_score_0_50": round(metrics["avg_s4"], 1),
        },
        "instructions": (
            "Compare this creator against Indian Instagram creators in the "
            f"{band} tier.  Be realistic — use actual Indian market benchmarks."
        ),
    }, ensure_ascii=False)


def build_creator_rankings(
    *,
    posts: list[SinglePostInsights],
    follower_count: int | None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    """Generate peer rankings for a creator.

    Returns a dict with 'rankings' (list of dicts) and 'audience_score' (dict),
    plus a 'fallback_used' boolean.
    """
    metrics = _extract_post_metrics(posts)
    post_count = len(posts)
    fallback = _build_deterministic_rankings(metrics, follower_count)

    # Check if peer rankings are enabled via env
    enabled_raw = os.getenv("AI_PEER_RANKINGS_ENABLED", "1")
    if enabled_raw.strip().lower() in {"0", "false", "no", "off"}:
        logger.info("[PeerRankings] Disabled via AI_PEER_RANKINGS_ENABLED; using fallback.")
        return fallback

    if llm_client is None:
        try:
            llm_client = LLMClient(temperature=0.0, max_tokens=600)
        except Exception as exc:
            logger.warning("[PeerRankings] Could not create LLM client: %s", exc)
            return fallback

    try:
        prompt = {
            "system": _RANKING_SYSTEM_PROMPT,
            "user": _build_ranking_prompt_user(metrics, follower_count, post_count),
        }
        raw_response = llm_client.generate(prompt)
        if not isinstance(raw_response, str) or not raw_response.strip():
            raise ValueError("LLM returned empty response.")

        parsed = _parse_ranking_response(raw_response)
        if parsed is None or not _validate_ranking_response(parsed):
            raise ValueError("LLM response failed validation.")

        parsed["fallback_used"] = False
        logger.info(
            "[PeerRankings] Generated via LLM for %d posts, best_stat=%s",
            post_count,
            parsed.get("best_stat_key", "?"),
        )
        return parsed

    except Exception as exc:
        logger.warning("[PeerRankings] LLM call failed, using fallback: %s", exc)
        return fallback
