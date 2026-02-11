from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI


INPUT_PATH = Path("backend/ml/chat_val.jsonl")
REQUIRED_KEYS = {
    "diagnosis",
    "weekly_plan",
    "content_suggestions",
    "posting_schedule",
    "cta_tips",
}


def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_num, json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_num}: {exc}") from exc


def _tokenize(text: str) -> set:
    return set(text.lower().split()) if text else set()


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _safe_parse_json(content: str) -> Dict[str, Any] | None:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _strip_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def _extract_assistant_content(row: Dict[str, Any]) -> str:
    messages = row.get("messages") or []
    for msg in messages:
        if msg.get("role") == "assistant":
            return msg.get("content", "")
    return ""

def _extract_user_content(row: Dict[str, Any]) -> str:
    messages = row.get("messages") or []
    for msg in messages:
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def _call_model(client: OpenAI, model: str, user_content: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": user_content}],
        temperature=0,
    )
    return response.choices[0].message.content or ""


def evaluate(path: Path, mode: str, limit: int) -> Dict[str, Any]:
    total = 0
    json_valid_count = 0
    has_all_keys_count = 0
    weekly_plan_overlap_sum = 0.0
    output_length_sum = 0
    client: Optional[OpenAI] = None
    model_name: Optional[str] = None

    if mode in {"base_gpt", "ft_gpt"}:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY is not set")
        client = OpenAI(api_key=api_key)
        if mode == "base_gpt":
            model_name = "gpt-4o-mini"
        else:
            model_name = os.getenv("ACTION_MODEL")
            if not model_name:
                raise EnvironmentError("ACTION_MODEL is not set for ft_gpt mode")

    for _, row in _read_jsonl(path):
        if total >= limit:
            break
        total += 1
        assistant_content = _extract_assistant_content(row)
        output_length_sum += len(assistant_content)

        if mode == "baseline":
            # Baseline pass-through: prediction == ground truth
            prediction = assistant_content
        else:
            user_content = _extract_user_content(row)
            prediction = _call_model(client, model_name, user_content)
        ground_truth = assistant_content

        pred_json = _safe_parse_json(prediction)
        gt_json = _safe_parse_json(ground_truth)

        json_valid = pred_json is not None
        if json_valid:
            json_valid_count += 1

        pred_clean = _strip_metadata(pred_json) if pred_json else {}
        gt_clean = _strip_metadata(gt_json) if gt_json else {}

        has_all_keys = json_valid and REQUIRED_KEYS.issubset(set(pred_clean.keys()))
        if has_all_keys:
            has_all_keys_count += 1

        pred_weekly = pred_clean.get("weekly_plan", [])
        gt_weekly = gt_clean.get("weekly_plan", [])

        pred_tokens = _tokenize(" ".join(pred_weekly))
        gt_tokens = _tokenize(" ".join(gt_weekly))
        weekly_plan_overlap_sum += _jaccard(pred_tokens, gt_tokens)

    if total == 0:
        return {
            "avg_weekly_plan_overlap": 0.0,
            "json_valid_pct": 0.0,
            "has_all_keys_pct": 0.0,
            "avg_output_length": 0.0,
            "total": 0,
        }

    return {
        "avg_weekly_plan_overlap": weekly_plan_overlap_sum / total,
        "json_valid_pct": (json_valid_count / total) * 100,
        "has_all_keys_pct": (has_all_keys_count / total) * 100,
        "avg_output_length": output_length_sum / total,
        "total": total,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate action plan quality")
    parser.add_argument(
        "--mode",
        choices=["baseline", "base_gpt", "ft_gpt"],
        default="baseline",
        help="Evaluation mode (baseline, base_gpt, ft_gpt)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Limit to first N examples",
    )
    parser.add_argument(
        "--input",
        default=str(INPUT_PATH),
        help="Path to chat validation JSONL",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    results = evaluate(input_path, args.mode, args.limit)

    print(f"Action Plan Evaluation ({args.mode})")
    print(f"Total examples: {results['total']}")
    print(f"% json_valid: {results['json_valid_pct']:.2f}")
    print(f"% has_all_keys: {results['has_all_keys_pct']:.2f}")
    print(f"avg_weekly_plan_overlap: {results['avg_weekly_plan_overlap']:.4f}")
    print(f"avg_output_length: {results['avg_output_length']:.2f}")


if __name__ == "__main__":
    main()
