import pytest

from backend.ml.clean_action_dataset import (
    ChatExample,
    EnrichedTrainingExample,
    TrainingExample,
    validate_jsonl_entry,
)


def _base_training_entry():
    return {
        "example_id": "ex-1",
        "created_at": "2026-02-16T12:34:56Z",
        "input": {
            "profile": {
                "username": "alice",
                "followers": 1200,
                "avg_likes": 100,
                "avg_comments": 5,
                "avg_views": 1000,
                "posts_per_week": 3.5,
            },
            "posts": [
                {
                    "caption": "hello",
                    "likes": 10,
                    "comments": 1,
                    "views": 200,
                }
            ],
        },
        "output": {
            "niche": {"primary_niche": "tech"},
            "growth": {"growth_score": 55},
            "post_insights": {"summary": "ok"},
        },
        "quality": "high",
    }


def test_training_example_valid_passes():
    entry = _base_training_entry()
    validate_jsonl_entry(entry, TrainingExample)


def test_training_example_invalid_created_at_raises():
    entry = _base_training_entry()
    entry["created_at"] = "not-a-date"
    with pytest.raises(ValueError):
        validate_jsonl_entry(entry, TrainingExample)


def test_training_example_invalid_quality_raises():
    entry = _base_training_entry()
    entry["quality"] = "great"
    with pytest.raises(ValueError):
        validate_jsonl_entry(entry, TrainingExample)


def test_training_example_extra_field_raises():
    entry = _base_training_entry()
    entry["unexpected"] = 123
    with pytest.raises(ValueError):
        validate_jsonl_entry(entry, TrainingExample)


def test_training_example_missing_required_field_raises():
    entry = _base_training_entry()
    entry.pop("output")
    with pytest.raises(ValueError):
        validate_jsonl_entry(entry, TrainingExample)


def test_enriched_training_example_missing_action_plan_raises():
    entry = _base_training_entry()
    with pytest.raises(ValueError):
        validate_jsonl_entry(entry, EnrichedTrainingExample)


def test_chat_example_invalid_role_raises():
    entry = {
        "messages": [
            {"role": "system", "content": "s"},
            {"role": "tool", "content": "x"},
        ]
    }
    with pytest.raises(ValueError):
        validate_jsonl_entry(entry, ChatExample)
