from __future__ import annotations

from types import SimpleNamespace

from backend.app.services.post_score_history_store import baseline_projection


def _snapshot(post_id: str, score: float) -> SimpleNamespace:
    return SimpleNamespace(post_id=post_id, score=score)


def test_baseline_uses_latest_distinct_other_posts() -> None:
    projection = baseline_projection(
        [
            _snapshot("current", 80),
            _snapshot("post_a", 70),
            _snapshot("post_a", 30),  # older rerun; list is newest first
            _snapshot("post_b", 60),
            _snapshot("post_c", 90),
        ],
        current_score=80,
        exclude_post_id="current",
    )

    assert projection == {
        "status": "available",
        "sample_size": 3,
        "minimum_sample_size": 3,
        "average_score": 73.33,
        "delta_from_average": 6.67,
        "reason": "Rolling average of each post's latest analysis, up to the 12 most recent distinct posts.",
    }


def test_baseline_reports_insufficient_history_without_inventing_a_delta() -> None:
    projection = baseline_projection([_snapshot("post_a", 70)], current_score=80)

    assert projection["status"] == "insufficient_history"
    assert projection["sample_size"] == 1
    assert projection["average_score"] is None
    assert projection["delta_from_average"] is None
