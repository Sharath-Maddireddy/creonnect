"""Deterministic weighted post score P engine for SinglePostInsights."""

from __future__ import annotations

from typing import Any

from backend.app.domain.post_models import WeightedPostScore


IMAGE_WEIGHTS: dict[str, float] = {
    "S1": 0.23,
    "S2": 0.22,
    "S3": 0.15,
    "S4": 0.15,
    "S5": 0.15,
    "S6": 0.10,
}

REEL_WEIGHTS: dict[str, float] = {
    "S1": 0.20,
    "S2": 0.20,
    "S3": 0.15,
    "S4": 0.15,
    "S5": 0.15,
    "S6": 0.10,
    "S7": 0.05,
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _clamp_component(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return round(_clamp(numeric, 0.0, 50.0), 2)


def _resolve_weights(post_type: str) -> tuple[str, dict[str, float], list[str]]:
    notes: list[str] = []
    normalized_post_type = post_type.upper().strip() if isinstance(post_type, str) else ""
    if normalized_post_type == "REEL":
        return "REEL", REEL_WEIGHTS, notes
    if normalized_post_type == "IMAGE":
        return "IMAGE", IMAGE_WEIGHTS, notes
    notes.append("Unknown post_type; defaulted to IMAGE weighting.")
    return "IMAGE", IMAGE_WEIGHTS, notes


def compute_weighted_post_score(
    post_type: str,
    s1: float | None,
    s2: float | None,
    s3: float | None,
    s4: float | None,
    s5: float | None,
    s6: float | None,
    s7: float | None,
) -> WeightedPostScore:
    """Compute spec-aligned weighted post score P.

    Output scale choice:
    - `normalized_score_0_50` stores the direct weighted score in 0..50.
    - `score` stores a user-facing 0..100 value (`normalized_score_0_50 * 2`).
    """

    resolved_post_type, weights, notes = _resolve_weights(post_type)
    components: dict[str, float | None] = {
        "S1": _clamp_component(s1),
        "S2": _clamp_component(s2),
        "S3": _clamp_component(s3),
        "S4": _clamp_component(s4),
        "S5": _clamp_component(s5),
        "S6": _clamp_component(s6),
        "S7": _clamp_component(s7),
    }

    used_weights: dict[str, float] = {}
    raw_weighted_sum = 0.0
    used_weight_sum = 0.0

    missing_components = [key for key in weights if components.get(key) is None]
    for key, weight in weights.items():
        value = components.get(key)
        if value is None:
            continue
        raw_weighted_sum += value * weight
        used_weight_sum += weight

    if used_weight_sum == 0.0:
        notes.append("Fallback applied: no available component scores for weighted computation.")
        return WeightedPostScore(
            post_type=resolved_post_type,
            normalized_score_0_50=25.0,
            score=50.0,
            components=components,
            weights_used={},
            notes=notes,
        )

    for key, weight in weights.items():
        if components.get(key) is None:
            continue
        used_weights[key] = round(weight / used_weight_sum, 6)

    if missing_components:
        notes.append(
            "Normalized over available components; missing: " + ", ".join(sorted(missing_components))
        )

    normalized_score_0_50 = round(_clamp(raw_weighted_sum / used_weight_sum, 0.0, 50.0), 2)
    score = _clamp(normalized_score_0_50 * 2.0, 0.0, 100.0)

    return WeightedPostScore(
        post_type=resolved_post_type,
        normalized_score_0_50=normalized_score_0_50,
        score=score,
        components=components,
        weights_used=used_weights,
        notes=notes,
    )
