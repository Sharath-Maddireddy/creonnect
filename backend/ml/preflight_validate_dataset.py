from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.ml.clean_action_dataset import (
    ChatExample,
    EnrichedTrainingExample,
    TrainingExample,
    validate_jsonl_entry,
)


TRAINING_PATH = Path("backend/data/training_data_scaled.jsonl")
CHAT_TRAIN_PATH = Path("backend/data/chat_train.jsonl")
CHAT_VAL_PATH = Path("backend/data/chat_val.jsonl")


def _read_jsonl(path: Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    if not path.exists():
        print(f"[warn] File not found: {path}")
        return []
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            yield line_num, json.loads(line)


def _pct(n: int, total: int) -> float:
    if total == 0:
        return 0.0
    return (n / total) * 100.0


def _summarize_training(path: Path) -> Dict[str, Any]:
    total = 0
    quality_counts = Counter()
    missing_action_plan = 0
    empty_action_plan = 0
    for line_num, row in _read_jsonl(path):
        total += 1
        validated = validate_jsonl_entry(row, EnrichedTrainingExample, row_index=line_num)
        quality_counts[validated.quality] += 1
        action_plan = validated.output.action_plan
        if action_plan is None:
            missing_action_plan += 1
        elif isinstance(action_plan, dict) and len(action_plan) == 0:
            empty_action_plan += 1
    return {
        "total": total,
        "quality_counts": dict(quality_counts),
        "missing_action_plan": missing_action_plan,
        "empty_action_plan": empty_action_plan,
    }


def _summarize_chat(path: Path) -> Dict[str, Any]:
    total = 0
    total_messages = 0
    empty_messages_list = 0
    empty_assistant_content = 0
    for line_num, row in _read_jsonl(path):
        total += 1
        validated = validate_jsonl_entry(row, ChatExample, row_index=line_num)
        messages = validated.messages
        if not messages:
            empty_messages_list += 1
        total_messages += len(messages)
        for msg in messages:
            if msg.role == "assistant" and not msg.content.strip():
                empty_assistant_content += 1
    avg_messages = (total_messages / total) if total else 0.0
    return {
        "total": total,
        "avg_messages": avg_messages,
        "empty_messages_list": empty_messages_list,
        "empty_assistant_content": empty_assistant_content,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-flight validation for fine-tuning datasets.")
    parser.add_argument("--training", type=Path, default=TRAINING_PATH)
    parser.add_argument("--chat-train", type=Path, default=CHAT_TRAIN_PATH)
    parser.add_argument("--chat-val", type=Path, default=CHAT_VAL_PATH)
    args = parser.parse_args()

    training_stats = _summarize_training(args.training)
    chat_train_stats = _summarize_chat(args.chat_train)
    chat_val_stats = _summarize_chat(args.chat_val)

    print("")
    print("Dataset Pre-flight Report")
    print("=" * 30)
    print(f"Training data: {args.training}")
    print(f"  Total examples: {training_stats['total']}")
    print("  Quality distribution:")
    for label, count in sorted(training_stats["quality_counts"].items()):
        print(f"    {label}: {count} ({_pct(count, training_stats['total']):.2f}%)")
    print("")

    print(f"Chat train: {args.chat_train}")
    print(f"  Total examples: {chat_train_stats['total']}")
    print(f"  Average messages per example: {chat_train_stats['avg_messages']:.2f}")
    print(f"  Empty messages list: {chat_train_stats['empty_messages_list']}")
    print(f"  Empty assistant content: {chat_train_stats['empty_assistant_content']}")
    print("")

    print(f"Chat val: {args.chat_val}")
    print(f"  Total examples: {chat_val_stats['total']}")
    print(f"  Average messages per example: {chat_val_stats['avg_messages']:.2f}")
    print(f"  Empty messages list: {chat_val_stats['empty_messages_list']}")
    print(f"  Empty assistant content: {chat_val_stats['empty_assistant_content']}")
    print("")

    failures = []
    if training_stats["total"] == 0:
        failures.append("Zero training examples.")
    if training_stats["missing_action_plan"] > 0:
        failures.append("Missing action_plan detected.")
    if training_stats["empty_action_plan"] > 0:
        failures.append("Empty action_plan detected.")
    if chat_train_stats["empty_messages_list"] > 0 or chat_val_stats["empty_messages_list"] > 0:
        failures.append("Empty messages list detected.")
    if (
        chat_train_stats["empty_assistant_content"] > 0
        or chat_val_stats["empty_assistant_content"] > 0
    ):
        failures.append("Empty assistant message content detected.")

    if failures:
        print("Pre-flight status: FAILED")
        for item in failures:
            print(f"  - {item}")
        raise SystemExit(1)

    print("Pre-flight status: PASSED")


if __name__ == "__main__":
    main()
