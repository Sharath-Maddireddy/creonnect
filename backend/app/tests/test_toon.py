"""Tests for TOON parser/encoder round-tripping."""

from __future__ import annotations

from backend.app.ai.toon import dumps, loads


def test_toon_round_trip_preserves_ambiguous_string_scalars() -> None:
    payload = {
        "truthy": "true",
        "falsy": "false",
        "nullish": "null",
        "none_word": "none",
        "integer_like": "123",
        "negative_int_like": "-7",
        "float_like": "3.14",
        "scientific_like": "1e5",
        "nested": {
            "list": ["true", "123", "null", "3.14"],
        },
    }

    assert loads(dumps(payload)) == payload


def test_toon_loads_preserves_explicitly_quoted_strings() -> None:
    text = "\n".join(
        [
            'truthy "true"',
            'integer_like "123"',
            'nullish "null"',
            'float_like "3.14"',
        ]
    )

    assert loads(text) == {
        "truthy": "true",
        "integer_like": "123",
        "nullish": "null",
        "float_like": "3.14",
    }
