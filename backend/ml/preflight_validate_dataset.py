from __future__ import annotations

import argparse
import json
import re
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


TRAINING_PATH = ROOT_DIR / "backend" / "data" / "training_data_scaled.jsonl"
CHAT_TRAIN_PATH = ROOT_DIR / "backend" / "data" / "chat_train.jsonl"
CHAT_VAL_PATH = ROOT_DIR / "backend" / "data" / "chat_val.jsonl"

ANONYMIZED_USERNAME_PATTERNS = (
    re.compile(r"^creator_[a-f0-9]{12}$"),
    re.compile(r"^user_\d{3}$"),
    re.compile(r"^(?:fit|chef|tech|style|lifestyle|life)_creator_\d+$"),
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://", re.IGNORECASE)
HANDLE_RE = re.compile(r"@[A-Za-z0-9._]{3,}")


def _read_jsonl(path: Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    if not path.exists():
        print(f"[warn] File not found: {path}")
        return []
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_num, json.loads(line)
            except json.JSONDecodeError as e:
                print(
                    f"[warn] Invalid JSON in {path} at line {line_num}: "
                    f"{e.msg} (char {e.pos})"
                )


def _pct(n: int, total: int) -> float:
    if total == 0:
        return 0.0
    return (n / total) * 100.0


def _iter_string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_string_values(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_string_values(item)


def _is_anonymized_username(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return any(pattern.fullmatch(value) for pattern in ANONYMIZED_USERNAME_PATTERNS)


def _summarize_training_privacy(path: Path) -> Dict[str, Any]:
    total = 0
    non_anonymized_usernames = 0
    email_like_rows = 0
    url_like_rows = 0
    handle_like_rows = 0

    for _, row in _read_jsonl(path):
        total += 1

        profile = row.get("input", {}).get("profile", {}) if isinstance(row, dict) else {}
        username = profile.get("username") if isinstance(profile, dict) else None
        if username is not None and not _is_anonymized_username(username):
            non_anonymized_usernames += 1

        row_has_email = False
        row_has_url = False
        row_has_handle = False
        for text in _iter_string_values(row):
            if not row_has_email and EMAIL_RE.search(text):
                row_has_email = True
            if not row_has_url and URL_RE.search(text):
                row_has_url = True
            if not row_has_handle and HANDLE_RE.search(text):
                row_has_handle = True
            if row_has_email and row_has_url and row_has_handle:
                break

        if row_has_email:
            email_like_rows += 1
        if row_has_url:
            url_like_rows += 1
        if row_has_handle:
            handle_like_rows += 1

    return {
        "total": total,
        "non_anonymized_usernames": non_anonymized_usernames,
        "email_like_rows": email_like_rows,
        "url_like_rows": url_like_rows,
        "handle_like_rows": handle_like_rows,
    }


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
            if msg.role == "assistant" and (not msg.content or not msg.content.strip()):
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
    privacy_stats = _summarize_training_privacy(args.training)
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
    print("  Privacy checks:")
    print(f"    Non-anonymized usernames: {privacy_stats['non_anonymized_usernames']}")
    print(f"    Rows with email-like strings: {privacy_stats['email_like_rows']}")
    print(f"    Rows with URL-like strings: {privacy_stats['url_like_rows']}")
    print(f"    Rows with @handle-like strings: {privacy_stats['handle_like_rows']}")
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
    if privacy_stats["non_anonymized_usernames"] > 0:
        failures.append("Non-anonymized usernames detected in training data.")
    if privacy_stats["email_like_rows"] > 0:
        failures.append("Email-like strings detected in training data.")
    if privacy_stats["url_like_rows"] > 0:
        failures.append("URL-like strings detected in training data.")
    if privacy_stats["handle_like_rows"] > 0:
        failures.append("@handle-like strings detected in training data.")
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
