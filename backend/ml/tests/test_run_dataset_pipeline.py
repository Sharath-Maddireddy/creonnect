from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from backend.ml import run_dataset_pipeline


def _valid_training_row() -> dict:
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
            "post_insights": [],
        },
        "quality": "high",
    }


def _write_jsonl_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_main_skips_malformed_and_invalid_lines_and_streams_valid_rows(
    monkeypatch,
    capsys,
) -> None:
    tmp_path = Path.cwd() / "backend" / "ml" / "tests" / f".tmp_run_dataset_pipeline_{uuid4().hex}"
    tmp_path.mkdir(parents=True, exist_ok=True)

    input_path = tmp_path / "input.jsonl"
    enriched_path = tmp_path / "training_data_with_actions.jsonl"
    chat_train_path = tmp_path / "chat_train.jsonl"
    chat_val_path = tmp_path / "chat_val.jsonl"

    invalid_row = _valid_training_row()
    invalid_row.pop("output")
    valid_row = _valid_training_row()

    _write_jsonl_lines(
        input_path,
        [
            '{"example_id": "broken"',
            json.dumps(invalid_row),
            json.dumps(valid_row),
        ],
    )

    monkeypatch.setattr(run_dataset_pipeline, "INPUT_PATH", input_path)
    monkeypatch.setattr(run_dataset_pipeline, "ENRICHED_PATH", enriched_path)
    monkeypatch.setattr(run_dataset_pipeline, "CHAT_TRAIN_PATH", chat_train_path)
    monkeypatch.setattr(run_dataset_pipeline, "CHAT_VAL_PATH", chat_val_path)
    monkeypatch.setattr(
        run_dataset_pipeline,
        "generate_action_plan",
        lambda **kwargs: {"diagnosis": "ok", "weekly_plan": [], "content_suggestions": [], "posting_schedule": [], "cta_tips": []},
    )

    run_dataset_pipeline.main()

    stdout = capsys.readouterr().out
    assert "[warn] skipping malformed JSONL line 1:" in stdout
    assert "[warn] skipping line 2:" in stdout

    enriched_lines = enriched_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(enriched_lines) == 1
    enriched_row = json.loads(enriched_lines[0])
    assert enriched_row["example_id"] == "ex-1"
    assert enriched_row["output"]["action_plan"]["diagnosis"] == "ok"

    chat_train_lines = chat_train_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(chat_train_lines) == 1
    assert chat_val_path.read_text(encoding="utf-8") == ""
