from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set


SYSTEM_PROMPT = (
    "You are a creator growth expert. Given creator analytics, produce actionable recommendations."
)


def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_num}: {exc}") from exc


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def _extract_niches(output: Dict[str, Any]) -> str:
    niche = output.get("niche") or {}
    primary = niche.get("primary_niche") or "unknown"
    secondary = niche.get("secondary_niche") or "unknown"
    return f"primary={primary}, secondary={secondary}"


def _extract_metrics(output: Dict[str, Any]) -> Dict[str, Any]:
    growth = output.get("growth") or {}
    metrics = growth.get("metrics") or {}
    return {
        "growth_score": growth.get("growth_score"),
        "engagement_rate_by_views": metrics.get("avg_engagement_rate_by_views"),
        "momentum": output.get("momentum"),
        "best_time_to_post": output.get("best_time_to_post"),
    }


def _format_recent_posts(input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    posts = (input_data.get("posts") or [])[-3:]
    formatted = []
    for post in posts:
        formatted.append(
            {
                "caption": post.get("caption"),
                "views": post.get("views"),
                "likes": post.get("likes"),
                "comments": post.get("comments"),
            }
        )
    return formatted


def _build_user_content(row: Dict[str, Any]) -> str:
    input_data = row.get("input") or {}
    output_data = row.get("output") or {}
    profile = input_data.get("profile") or {}

    creator_profile = {
        "username": profile.get("username"),
        "followers": profile.get("followers"),
        "niches": _extract_niches(output_data),
    }

    metrics = _extract_metrics(output_data)
    recent_posts = _format_recent_posts(input_data)

    return (
        "<creator_profile>\n"
        f"{json.dumps(creator_profile, ensure_ascii=False)}\n"
        "</creator_profile>\n\n"
        "<metrics>\n"
        f"{json.dumps(metrics, ensure_ascii=False)}\n"
        "</metrics>\n\n"
        "<recent_posts>\n"
        f"{json.dumps(recent_posts, ensure_ascii=False)}\n"
        "</recent_posts>"
    )


def _build_assistant_content(row: Dict[str, Any]) -> str:
    output_data = row.get("output") or {}
    action_plan = output_data.get("action_plan")
    if action_plan is None:
        example_id = row.get("example_id", "unknown")
        raise ValueError(f"Missing action_plan for example_id={example_id}")
    return json.dumps(action_plan, ensure_ascii=False)


def _row_to_chat(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_content(row)},
            {"role": "assistant", "content": _build_assistant_content(row)},
        ]
    }


def _split_from_metadata(row: Dict[str, Any]) -> Optional[str]:
    split = row.get("split") or row.get("dataset") or row.get("set")
    if isinstance(split, str):
        split_lower = split.lower()
        if split_lower in {"train", "val", "validation"}:
            return "val" if split_lower.startswith("val") else "train"
    if row.get("is_val") is True:
        return "val"
    if row.get("is_train") is True:
        return "train"
    return None


def _build_val_id_set(val_path: Path) -> Set[str]:
    val_ids: Set[str] = set()
    if not val_path.exists():
        return val_ids
    for row in _read_jsonl(val_path):
        example_id = row.get("example_id")
        if example_id:
            val_ids.add(example_id)
    return val_ids


def convert_dataset(
    input_path: Path,
    train_out: Path,
    val_out: Path,
    val_input: Path | None = None,
) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    val_ids: Set[str] = set()
    if val_input is not None:
        val_ids = _build_val_id_set(val_input)
    else:
        sibling_val = input_path.parent / "val.jsonl"
        if sibling_val.exists():
            val_ids = _build_val_id_set(sibling_val)
        else:
            # Fallback to app/tests val split if present
            fallback_val = Path("backend/app/tests/val.jsonl")
            if fallback_val.exists():
                val_ids = _build_val_id_set(fallback_val)

    train_rows: List[Dict[str, Any]] = []
    val_rows: List[Dict[str, Any]] = []

    for row in _read_jsonl(input_path):
        split = _split_from_metadata(row)
        if split is None and val_ids:
            example_id = row.get("example_id")
            if example_id in val_ids:
                split = "val"
        if split == "val":
            val_rows.append(_row_to_chat(row))
        else:
            train_rows.append(_row_to_chat(row))

    _write_jsonl(train_out, train_rows)
    _write_jsonl(val_out, val_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert training_data.jsonl to chat-style JSONL")
    parser.add_argument(
        "--input",
        default="backend/data/training_data.jsonl",
        help="Path to training_data.jsonl",
    )
    parser.add_argument(
        "--train_output",
        default="backend/ml/chat_train.jsonl",
        help="Output path for chat train JSONL",
    )
    parser.add_argument(
        "--val_output",
        default="backend/ml/chat_val.jsonl",
        help="Output path for chat val JSONL",
    )
    parser.add_argument(
        "--val_input",
        default=None,
        help="Optional path to validation JSONL for split selection",
    )
    args = parser.parse_args()

    val_input = Path(args.val_input) if args.val_input else None
    convert_dataset(
        Path(args.input),
        Path(args.train_output),
        Path(args.val_output),
        val_input=val_input,
    )


if __name__ == "__main__":
    main()
