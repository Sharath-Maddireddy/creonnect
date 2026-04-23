from __future__ import annotations

from backend.core.momentum import calculate_momentum


def test_calculate_momentum_parses_z_suffixed_iso_timestamps() -> None:
    result = calculate_momentum(
        [
            {"date": "2026-04-20T00:00:00Z", "followers": 100},
            {"date": "2026-04-23T00:00:00Z", "followers": 160},
        ]
    )

    assert result == {
        "momentum_value": 20.0,
        "momentum_label": "accelerating",
    }
