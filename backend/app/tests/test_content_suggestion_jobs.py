from __future__ import annotations

from backend.app.services.content_suggestion_jobs import IDEA_GENERATION_STEPS, _parse_json_object


def test_idea_generation_progress_only_describes_real_work() -> None:
    assert IDEA_GENERATION_STEPS == [
        "Preparing generation context",
        "Generating high-potential ideas",
    ]


def test_parse_json_object_ignores_trailing_text() -> None:
    payload = _parse_json_object('Result: {"ideas": [{"title": "One"}]} trailing } text')

    assert payload == {"ideas": [{"title": "One"}]}
