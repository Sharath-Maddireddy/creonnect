from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.ai.rag import generate_action_plan
from backend.ml.clean_action_dataset import (
    ChatExample,
    EnrichedTrainingExample,
    TrainingExample,
    validate_jsonl_entry,
)


INPUT_PATH = ROOT_DIR / "backend" / "app" / "tests" / "training_data.jsonl"
ENRICHED_PATH = ROOT_DIR / "backend" / "data" / "training_data_with_actions.jsonl"
CHAT_TRAIN_PATH = ROOT_DIR / "backend" / "data" / "chat_train.jsonl"
CHAT_VAL_PATH = ROOT_DIR / "backend" / "data" / "chat_val.jsonl"

SPLIT_SEED = 1337
TRAIN_FRACTION = 0.9


def _read_jsonl(path: Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_num, json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_num}: {exc}") from exc


def _write_jsonl(rows: Iterable[Dict[str, Any]], path: Path) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")
            count += 1
    return count


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def _build_action_plan(entry: Dict[str, Any]) -> Dict[str, Any]:
    input_data = entry["input"]
    profile = input_data["profile"]
    posts = input_data["posts"]
    output = entry.get("output") if isinstance(entry.get("output"), dict) else {}
    growth = output.get("growth", {})
    niche = output.get("niche", {})

    avg_views = _safe_float(profile.get("avg_views", 0))
    avg_likes = _safe_float(profile.get("avg_likes", 0))
    avg_comments = _safe_float(profile.get("avg_comments", 0))
    avg_engagement = (avg_likes + avg_comments) / avg_views if avg_views > 0 else 0.0

    creator_metrics = {
        "followers": profile.get("followers", 0),
        "growth_score": growth.get("growth_score", 0),
        "avg_views": avg_views,
        "avg_engagement_rate_by_views": avg_engagement,
        "posts_per_week": profile.get("posts_per_week", 0),
    }

    recent_posts = posts[-3:] if isinstance(posts, list) else []

    return generate_action_plan(
        creator_metrics=creator_metrics,
        niche_data=niche,
        momentum={},
        best_time={},
        recent_posts=recent_posts,
        knowledge_chunks=None,
    )


def _enrich_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(entry)
    output = dict(enriched.get("output", {}))
    output["action_plan"] = _build_action_plan(enriched)
    enriched["output"] = output
    return enriched


def _to_chat_example(entry: Dict[str, Any]) -> Dict[str, Any]:
    system_msg = "You are an AI assistant that provides creator growth action plans."
    user_msg = json.dumps({"input": entry["input"]}, ensure_ascii=False)
    assistant_msg = json.dumps({"action_plan": entry["output"]["action_plan"]}, ensure_ascii=False)
    chat = {
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }
    validate_jsonl_entry(chat, ChatExample)
    return chat


def main() -> None:
    if not INPUT_PATH.exists():
        print(f"[error] Input dataset not found: {INPUT_PATH}")
        raise SystemExit(1)

    ENRICHED_PATH.parent.mkdir(parents=True, exist_ok=True)

    enriched_rows: List[Dict[str, Any]] = []
    for line_num, row in _read_jsonl(INPUT_PATH):
        validate_jsonl_entry(row, TrainingExample, row_index=line_num)
        enriched = _enrich_entry(row)
        validate_jsonl_entry(enriched, EnrichedTrainingExample, row_index=line_num)
        enriched_rows.append(enriched)

    enriched_count = _write_jsonl(enriched_rows, ENRICHED_PATH)

    chat_rows = [_to_chat_example(row) for row in enriched_rows]
    rng = random.Random(SPLIT_SEED)
    rng.shuffle(chat_rows)
    split_idx = int(len(chat_rows) * TRAIN_FRACTION)
    if len(chat_rows) > 0 and split_idx == 0:
        split_idx = 1  # Ensure at least one training example for tiny datasets
    chat_train = chat_rows[:split_idx]
    chat_val = chat_rows[split_idx:]

    chat_train_count = _write_jsonl(chat_train, CHAT_TRAIN_PATH)
    chat_val_count = _write_jsonl(chat_val, CHAT_VAL_PATH)

    print(f"Enriched examples written: {enriched_count} -> {ENRICHED_PATH}")
    print(f"Chat train examples: {chat_train_count} -> {CHAT_TRAIN_PATH}")
    print(f"Chat val examples: {chat_val_count} -> {CHAT_VAL_PATH}")


if __name__ == "__main__":
    main()
