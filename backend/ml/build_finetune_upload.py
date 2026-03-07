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
IGNORED_DATASET_NAME_PATTERNS = (".bak", "_before_", ".orig", ".tmp")


def _read_jsonl(path: Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            raw = line.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                excerpt = raw[:200]
                raise ValueError(
                    f"Invalid JSON in {path} at line {line_num}: "
                    f"excerpt={excerpt!r}; error={exc.msg}"
                ) from exc

            if not isinstance(obj, dict):
                raise ValueError(
                    f"Expected JSON object in {path} at line {line_num}, "
                    f"got {type(obj).__name__}"
                )

            yield line_num, obj


def _clean_messages(messages: Iterable[Any]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for msg in messages:
        normalized_content = msg.content if isinstance(msg.content, str) else ""
        if msg.role == "assistant" and not normalized_content.strip():
            continue
        cleaned.append({"role": msg.role, "content": normalized_content})
    return cleaned


def _resolve_dataset_paths(root: Path) -> Dict[str, Path]:
    found: Dict[str, Path] = {}
    for path in sorted(root.rglob("*.jsonl")):
        lower_name = path.name.lower()
        if any(pattern in lower_name for pattern in IGNORED_DATASET_NAME_PATTERNS):
            continue
        if "_archive" in path.parts:
            continue
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
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
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
