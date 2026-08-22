"""Tests for TOON parser/encoder round-tripping."""

from __future__ import annotations

from backend.app.ai.toon import dumps, loads, loads_object


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


def test_toon_round_trip_preserves_quote_like_strings() -> None:
    payload = {
        "double_quoted_like": '"hello"',
        "single_quoted_like": "'hello'",
    }

    assert loads(dumps(payload)) == payload


def test_toon_round_trip_preserves_control_characters() -> None:
    payload = {
        "multiline": "line one\nline two",
        "carriage_return": "line one\rline two",
        "tabbed": "col1\tcol2",
    }

    assert loads(dumps(payload)) == payload


def test_toon_loads_parses_bracket_inline_lists() -> None:
    """Some providers (observed from Gemini reel output) emit list fields as
    JSON-like inline brackets instead of multi-line ``- item`` entries."""
    text = "\n".join(
        [
            "objects [ice cream, chocolate syrup, waffle bowl]",
            'cringe_signals [repetitive text overlay]',
            "cringe_fixes []",
            "hook_frame_score 0.7",
        ]
    )

    assert loads(text) == {
        "objects": ["ice cream", "chocolate syrup", "waffle bowl"],
        "cringe_signals": ["repetitive text overlay"],
        "cringe_fixes": [],
        "hook_frame_score": 0.7,
    }


def test_toon_loads_bracket_inline_list_respects_quoted_commas() -> None:
    text = 'detected_text ["hello, world", plain]'

    assert loads(text) == {"detected_text": ["hello, world", "plain"]}


def test_toon_round_trip_preserves_bracket_like_strings() -> None:
    payload = {"weird": "[abc]", "empty_brackets": "[]"}

    assert loads(dumps(payload)) == payload


def test_toon_loads_real_gemini_reel_payload_recovers_lists() -> None:
    """Regression for the bracket-inline objects/cringe_signals/cringe_fixes bug."""
    text = "\n".join(
        [
            "hook_frame_score 0.7",
            "pacing_label fast",
            "retention_signal 0.6",
            "objects [ice cream, chocolate syrup, waffle bowl, spoon, table, tray]",
            'scene_description "Close-up shots of chocolate ice cream."',
            "hook_strength_score 0.65",
            "cringe_score 15",
            "cringe_signals [repetitive text overlay]",
            "cringe_fixes [simplify caption text]",
            "production_level medium",
            "adult_content_detected false",
        ]
    )

    parsed = loads(text)
    assert parsed["objects"] == ["ice cream", "chocolate syrup", "waffle bowl", "spoon", "table", "tray"]
    assert parsed["cringe_signals"] == ["repetitive text overlay"]
    assert parsed["cringe_fixes"] == ["simplify caption text"]


def test_loads_object_prefers_plain_json_when_model_ignores_toon_instruction() -> None:
    """Regression: Gemini sometimes returns strict JSON despite being asked
    for TOON, which the indentation-based `loads` cannot parse at all
    (braces, quoted keys, trailing commas)."""
    text = """
    {
      "hook_frame_score": 0.5,
      "objects": [
        "ice cream",
        "spoon"
      ],
      "detected_text": null,
      "cringe_signals": [],
      "adult_content_detected": false
    }
    """

    assert loads_object(text) == {
        "hook_frame_score": 0.5,
        "objects": ["ice cream", "spoon"],
        "detected_text": None,
        "cringe_signals": [],
        "adult_content_detected": False,
    }


def test_loads_object_falls_back_to_toon_when_not_json() -> None:
    text = "hook_frame_score 0.7\nobjects [ice cream, spoon]"

    assert loads_object(text) == {"hook_frame_score": 0.7, "objects": ["ice cream", "spoon"]}


def test_loads_strips_leading_toon_label_line() -> None:
    """Regression: Gemini sometimes prepends a bare "TOON:" label despite
    being told to return no prose/labels, which nests the entire payload
    one level deeper and silently drops every downstream field."""
    text = "\n".join(
        [
            "TOON:",
            "  hook_frame_score 0.75",
            "  cringe_score 0",
            "  objects",
            "    - ice cream",
            "    - spoon",
            "  visual_quality_score",
            "    composition 7.0",
            "    lighting 7.0",
        ]
    )

    assert loads(text) == {
        "hook_frame_score": 0.75,
        "cringe_score": 0,
        "objects": ["ice cream", "spoon"],
        "visual_quality_score": {"composition": 7.0, "lighting": 7.0},
    }


def test_loads_strips_leading_toon_label_with_colon_style_values() -> None:
    text = "TOON:\n  hook_frame_score: 0.75\n  cringe_score: 0"

    assert loads(text) == {"hook_frame_score": 0.75, "cringe_score": 0}


def test_loads_does_not_strip_a_real_field_named_similarly() -> None:
    """Only the exact bare labels "toon"/"json" are stripped -- a real field
    like "tooling:" or "json_notes:" must be parsed normally."""
    text = "tooling\n  x 1"

    assert loads(text) == {"tooling": {"x": 1}}


def test_loads_object_falls_back_to_toon_on_invalid_json() -> None:
    text = 'scene_description "A person holding {a} broken brace"'

    assert loads_object(text) == {"scene_description": "A person holding {a} broken brace"}
