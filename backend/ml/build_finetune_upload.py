from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.ml.clean_action_dataset import ChatExample, validate_jsonl_entry


OUTPUT_PATH = ROOT_DIR / "backend" / "data" / "fine_tune_upload.jsonl"
EXPECTED_DATASETS = [
    "training_data.jsonl",
    "training_data_with_actions.jsonl",
    "chat_train.jsonl",
    "chat_val.jsonl",
]


def _read_jsonl(path: Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            yield line_num, json.loads(line)


def _clean_messages(messages):
    cleaned = []
    for msg in messages:
        if msg.role == "assistant" and not msg.content.strip():
            continue
        cleaned.append({"role": msg.role, "content": msg.content})
    return cleaned


def _resolve_dataset_paths(root: Path) -> Dict[str, Path]:
    found: Dict[str, Path] = {}
    for path in root.rglob("*.jsonl"):
        name = path.name
        if name in EXPECTED_DATASETS and name not in found:
            found[name] = path
    return found


def main() -> None:
    dataset_paths = _resolve_dataset_paths(ROOT_DIR)
    missing = [name for name in EXPECTED_DATASETS if name not in dataset_paths]
    if missing:
        print("Missing expected dataset files:")
        for name in missing:
            print(f"  - {name}")
        if "chat_train.jsonl" not in dataset_paths:
            print("Cannot proceed without chat_train.jsonl.")
            raise SystemExit(1)

    input_path = dataset_paths["chat_train.jsonl"]

    written = 0
    with OUTPUT_PATH.open("w", encoding="utf-8") as out_file:
        for line_num, row in _read_jsonl(input_path):
            validated = validate_jsonl_entry(row, ChatExample, row_index=line_num)
            cleaned_messages = _clean_messages(validated.messages)
            if len(cleaned_messages) < 2:
                continue
            out_file.write(json.dumps({"messages": cleaned_messages}, ensure_ascii=False))
            out_file.write("\n")
            written += 1

    print(f"Wrote {written} examples to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
