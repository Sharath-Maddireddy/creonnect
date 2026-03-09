from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.ml.clean_action_dataset import (
    ChatExample,
    EnrichedTrainingExample,
    validate_jsonl_entry,
)


INPUT_PATH = ROOT_DIR / "backend" / "data" / "training_data_scaled.jsonl"
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
            yield line_num, json.loads(line)


def _write_jsonl(rows: Iterable[Dict[str, Any]], path: Path) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")
            count += 1
    return count


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

    CHAT_TRAIN_PATH.parent.mkdir(parents=True, exist_ok=True)

    enriched_rows: List[Dict[str, Any]] = []
    for line_num, row in _read_jsonl(INPUT_PATH):
        validated = validate_jsonl_entry(row, EnrichedTrainingExample, row_index=line_num)
        enriched_rows.append(validated.model_dump(mode="json"))

    chat_rows = [_to_chat_example(row) for row in enriched_rows]
    rng = random.Random(SPLIT_SEED)
    rng.shuffle(chat_rows)
    split_idx = int(len(chat_rows) * TRAIN_FRACTION)
    chat_train = chat_rows[:split_idx]
    chat_val = chat_rows[split_idx:]

    chat_train_count = _write_jsonl(chat_train, CHAT_TRAIN_PATH)
    chat_val_count = _write_jsonl(chat_val, CHAT_VAL_PATH)

    print(f"Chat train examples: {chat_train_count} -> {CHAT_TRAIN_PATH}")
    print(f"Chat val examples: {chat_val_count} -> {CHAT_VAL_PATH}")


if __name__ == "__main__":
    main()
