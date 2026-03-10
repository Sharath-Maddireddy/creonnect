#!/usr/bin/env python3
"""One-time cleaner for fine-tuning JSONL datasets."""

from __future__ import annotations

import argparse
import copy
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PREFIX_TO_NICHE: dict[str, str] = {
    "fit_creator_": "fitness",
    "chef_creator_": "food",
    "tech_creator_": "technology",
    "style_creator_": "style",
    "lifestyle_creator_": "lifestyle",
}

NICHE_ALIASES: dict[str, str] = {
    "fashion": "style",
}

KNOWN_NICHE_PATTERN = re.compile(r"\b(fitness|food|technology|style|lifestyle|fashion)\b", re.IGNORECASE)
CREATOR_ID_PATTERN = re.compile(r"\b([a-z]+_creator_\d+)\b")
SYNTHETIC_HANDLE_PATTERN = re.compile(r"^(?:fit|chef|tech|style|lifestyle|life)_creator_\d+$")

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
URL_PATTERN = re.compile(r"\b(?:https?://|www\.)[^\s\"'>]+", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d().\-\s]{8,}\d)(?!\w)")
HANDLE_PATTERN = re.compile(r"(?<![\w@])@([A-Za-z0-9_.]{2,30})")

EMAIL_REPLACEMENT = "creator@example.com"
URL_REPLACEMENT = "https://example.com/creator"
PHONE_REPLACEMENT = "+10000000000"
HANDLE_REPLACEMENT = "@creator_handle"


def infer_niche(creator_id: str | None) -> str:
    if not creator_id:
        return "unknown"
    for prefix, niche in PREFIX_TO_NICHE.items():
        if creator_id.startswith(prefix):
            return niche
    return "unknown"


def canonicalize_niche(label: str) -> str:
    lowered = label.lower()
    return NICHE_ALIASES.get(lowered, lowered)


def extract_niche_mentions(text: str) -> set[str]:
    mentions: set[str] = set()
    for match in KNOWN_NICHE_PATTERN.findall(text):
        mentions.add(canonicalize_niche(match))
    return mentions


def _try_parse_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def extract_creator_id(messages: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    user_contents = [
        message.get("content", "")
        for message in messages
        if isinstance(message, dict)
        and message.get("role") == "user"
        and isinstance(message.get("content"), str)
    ]

    for content in user_contents:
        parsed = _try_parse_json(content)
        if isinstance(parsed, dict):
            username = (
                parsed.get("input", {})
                .get("profile", {})
                .get("username")
            )
            if isinstance(username, str):
                return username, None

        creator_ids = sorted(set(CREATOR_ID_PATTERN.findall(content)))
        if len(creator_ids) == 1:
            return creator_ids[0], None
        if len(creator_ids) > 1:
            return None, f"ambiguous creator ids in user content: {creator_ids}"

    all_contents = " ".join(
        message.get("content", "")
        for message in messages
        if isinstance(message, dict) and isinstance(message.get("content"), str)
    )
    creator_ids = sorted(set(CREATOR_ID_PATTERN.findall(all_contents)))
    if len(creator_ids) == 1:
        return creator_ids[0], None
    if len(creator_ids) > 1:
        return None, f"ambiguous creator ids across row: {creator_ids}"
    return None, "creator id not found"


def replace_niche_mentions(text: str, target_niche: str) -> tuple[str, list[dict[str, str]]]:
    replacements: list[dict[str, str]] = []

    def _repl(match: re.Match[str]) -> str:
        original = match.group(0)
        canonical = canonicalize_niche(original)
        if canonical == target_niche:
            return original
        replacements.append({"from": original, "to": target_niche})
        return target_niche

    updated = KNOWN_NICHE_PATTERN.sub(_repl, text)
    return updated, replacements


def _looks_like_phone(token: str) -> bool:
    digits_only = re.sub(r"\D", "", token)
    if not 10 <= len(digits_only) <= 15:
        return False
    return bool(re.search(r"[().\-\s+]", token))


def _is_safe_handle(handle_without_at: str) -> bool:
    if handle_without_at == "creator_handle":
        return True
    return bool(SYNTHETIC_HANDLE_PATTERN.fullmatch(handle_without_at))


def anonymize_content(text: str) -> tuple[str, list[dict[str, str]]]:
    replacements: list[dict[str, str]] = []
    updated = text

    def _replace_email(match: re.Match[str]) -> str:
        original = match.group(0)
        if original == EMAIL_REPLACEMENT:
            return original
        replacements.append({"type": "email", "from": original, "to": EMAIL_REPLACEMENT})
        return EMAIL_REPLACEMENT

    def _replace_url(match: re.Match[str]) -> str:
        original = match.group(0)
        if original == URL_REPLACEMENT:
            return original
        replacements.append({"type": "url", "from": original, "to": URL_REPLACEMENT})
        return URL_REPLACEMENT

    def _replace_phone(match: re.Match[str]) -> str:
        original = match.group(0)
        if original == PHONE_REPLACEMENT or not _looks_like_phone(original):
            return original
        replacements.append({"type": "phone", "from": original, "to": PHONE_REPLACEMENT})
        return PHONE_REPLACEMENT

    def _replace_handle(match: re.Match[str]) -> str:
        handle_without_at = match.group(1)
        original = match.group(0)
        if _is_safe_handle(handle_without_at):
            return original
        if original == HANDLE_REPLACEMENT:
            return original
        replacements.append({"type": "handle", "from": original, "to": HANDLE_REPLACEMENT})
        return HANDLE_REPLACEMENT

    updated = EMAIL_PATTERN.sub(_replace_email, updated)
    updated = URL_PATTERN.sub(_replace_url, updated)
    updated = PHONE_PATTERN.sub(_replace_phone, updated)
    updated = HANDLE_PATTERN.sub(_replace_handle, updated)
    return updated, replacements


def determine_drops(rows: list[dict[str, Any]]) -> tuple[set[int], list[dict[str, Any]], set[str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dropped_line_numbers: set[int] = set()
    drop_details: list[dict[str, Any]] = []
    creators_with_conflicts: set[str] = set()

    for row in rows:
        creator_id = row["creator_id"]
        key = creator_id if creator_id is not None else f"__missing__:{row['line_number']}"
        grouped[key].append(row)

    for key, group_rows in grouped.items():
        if key.startswith("__missing__:"):
            for row in group_rows:
                dropped_line_numbers.add(row["line_number"])
                drop_details.append(
                    {
                        "line_number": row["line_number"],
                        "creator_id": None,
                        "reason": "creator_id_missing_or_ambiguous",
                        "note": row["creator_note"],
                    }
                )
            continue

        creator_id = key
        expected_niche = infer_niche(creator_id)
        inferred_niches = {row["inferred_niche"] for row in group_rows}

        if len(inferred_niches) > 1:
            creators_with_conflicts.add(creator_id)
            if expected_niche == "unknown":
                for row in group_rows:
                    dropped_line_numbers.add(row["line_number"])
                    drop_details.append(
                        {
                            "line_number": row["line_number"],
                            "creator_id": creator_id,
                            "reason": "creator_inferred_niche_conflict_unknown_prefix",
                        }
                    )
            else:
                for row in group_rows:
                    if row["inferred_niche"] == expected_niche:
                        continue
                    dropped_line_numbers.add(row["line_number"])
                    drop_details.append(
                        {
                            "line_number": row["line_number"],
                            "creator_id": creator_id,
                            "reason": "creator_inferred_niche_conflict_dropped_nonprefix_rows",
                        }
                    )
            continue

        if expected_niche == "unknown":
            observed_niches: set[str] = set()
            for row in group_rows:
                observed_niches.update(row["observed_niches"])
            if len(observed_niches) > 1:
                creators_with_conflicts.add(creator_id)
                for row in group_rows:
                    dropped_line_numbers.add(row["line_number"])
                    drop_details.append(
                        {
                            "line_number": row["line_number"],
                            "creator_id": creator_id,
                            "reason": "unknown_prefix_conflicting_niche_supervision",
                            "observed_niches": sorted(observed_niches),
                        }
                    )

    return dropped_line_numbers, drop_details, creators_with_conflicts


def _default_paths() -> tuple[Path, Path, Path]:
    backend_dir = Path(__file__).resolve().parents[2]
    input_path = backend_dir / "data" / "fine_tune_upload.jsonl"
    output_path = backend_dir / "data" / "fine_tune_upload.cleaned.jsonl"
    report_path = backend_dir / "data" / "fine_tune_upload.report.json"
    return input_path, output_path, report_path


def parse_args() -> argparse.Namespace:
    default_input, default_output, default_report = _default_paths()

    parser = argparse.ArgumentParser(description="Fix niche-label and PII issues in fine-tune JSONL data.")
    parser.add_argument("input_jsonl", nargs="?", default=str(default_input), help="Input JSONL dataset path.")
    parser.add_argument("--output", default=str(default_output), help="Output cleaned JSONL path.")
    parser.add_argument("--report", default=str(default_report), help="Output report JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_jsonl).resolve()
    output_path = Path(args.output).resolve()
    report_path = Path(args.report).resolve()

    rows: list[dict[str, Any]] = []
    total_lines = 0

    with input_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue

            total_lines += 1
            obj = json.loads(stripped)
            messages = obj.get("messages")
            if not isinstance(messages, list):
                rows.append(
                    {
                        "line_number": line_number,
                        "obj": obj,
                        "creator_id": None,
                        "creator_note": "messages field is not a list",
                        "inferred_niche": "unknown",
                        "observed_niches": set(),
                    }
                )
                continue

            creator_id, creator_note = extract_creator_id(messages)
            inferred_niche = infer_niche(creator_id)
            observed_niches: set[str] = set()
            for message in messages:
                if not isinstance(message, dict):
                    continue
                if message.get("role") not in {"assistant", "system"}:
                    continue
                content = message.get("content")
                if isinstance(content, str):
                    observed_niches.update(extract_niche_mentions(content))

            rows.append(
                {
                    "line_number": line_number,
                    "obj": obj,
                    "creator_id": creator_id,
                    "creator_note": creator_note,
                    "inferred_niche": inferred_niche,
                    "observed_niches": observed_niches,
                }
            )

    dropped_lines, drop_details, creators_with_conflicts = determine_drops(rows)

    cleaned_rows: list[dict[str, Any]] = []
    lines_fixed = 0
    niche_replacements: list[dict[str, Any]] = []
    pii_replacements: list[dict[str, Any]] = []

    for row in rows:
        if row["line_number"] in dropped_lines:
            continue

        obj = copy.deepcopy(row["obj"])
        messages = obj.get("messages", [])
        line_changed = False

        for message_index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue

            content = message.get("content")
            if not isinstance(content, str):
                continue

            role = message.get("role")
            if row["inferred_niche"] != "unknown" and role in {"assistant", "system"}:
                content, replacements = replace_niche_mentions(content, row["inferred_niche"])
                if replacements:
                    line_changed = True
                    niche_replacements.append(
                        {
                            "line_number": row["line_number"],
                            "creator_id": row["creator_id"],
                            "role": role,
                            "message_index": message_index,
                            "count": len(replacements),
                            "from_labels": sorted({entry["from"].lower() for entry in replacements}),
                            "to_label": row["inferred_niche"],
                        }
                    )

            content, replacements = anonymize_content(content)
            if replacements:
                line_changed = True
                for replacement in replacements:
                    pii_replacements.append(
                        {
                            "line_number": row["line_number"],
                            "creator_id": row["creator_id"],
                            "role": role,
                            "message_index": message_index,
                            **replacement,
                        }
                    )

            message["content"] = content

        if line_changed:
            lines_fixed += 1
        cleaned_rows.append(obj)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for obj in cleaned_rows:
            handle.write(json.dumps(obj, ensure_ascii=False) + "\n")

    unknown_creators = sorted(
        {
            row["creator_id"]
            for row in rows
            if row["creator_id"] is not None and row["inferred_niche"] == "unknown"
        }
    )

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_file": str(input_path),
        "output_file": str(output_path),
        "total_lines": total_lines,
        "lines_written": len(cleaned_rows),
        "lines_fixed": lines_fixed,
        "lines_dropped": len(dropped_lines),
        "creators_total": len({row["creator_id"] for row in rows if row["creator_id"] is not None}),
        "creators_with_conflicts": sorted(creators_with_conflicts),
        "unknown_creators": unknown_creators,
        "drop_details": drop_details,
        "niche_replacements_count": len(niche_replacements),
        "niche_replacements": niche_replacements[:200],
        "pii_replacements_count": len(pii_replacements),
        "pii_replacements": pii_replacements[:200],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(f"Input lines: {total_lines}")
    print(f"Lines fixed: {lines_fixed}")
    print(f"Lines dropped: {len(dropped_lines)}")
    print(f"Output lines: {len(cleaned_rows)}")
    print(f"Creators with conflicts: {len(creators_with_conflicts)}")
    print(f"PII replacements: {len(pii_replacements)}")
    print(f"Cleaned JSONL: {output_path}")
    print(f"Report JSON: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
