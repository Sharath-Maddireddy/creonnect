#!/usr/bin/env python3
"""Validator for fine-tuning JSONL dataset quality and governance."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PREFIX_TO_NICHE: dict[str, str] = {
    "fit_creator_": "fitness",
    "chef_creator_": "food",
    "tech_creator_": "technology",
    "style_creator_": "style",
    "lifestyle_creator_": "lifestyle",
    "life_creator_": "lifestyle",
}

NICHE_ALIASES: dict[str, str] = {
    "fashion": "style",
}

KNOWN_NICHE_PATTERN = re.compile(r"\b(fitness|food|technology|style|lifestyle|fashion)\b", re.IGNORECASE)
CREATOR_ID_PATTERN = re.compile(r"\b([a-z]+_creator_\d+)\b")
SYNTHETIC_HANDLE_PREFIXES: tuple[str, ...] = tuple(
    sorted(
        {
            prefix[: -len("_creator_")]
            for prefix in PREFIX_TO_NICHE
            if prefix.endswith("_creator_")
        }
    )
)
SYNTHETIC_HANDLE_PATTERN = re.compile(
    rf"^(?:{'|'.join(re.escape(prefix) for prefix in SYNTHETIC_HANDLE_PREFIXES)})_creator_\d+$"
)

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
URL_PATTERN = re.compile(r"\b(?:https?://|www\.)[^\s\"'>]+", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d().\-\s]{8,}\d)(?!\w)")
HANDLE_PATTERN = re.compile(r"(?<![\w@])@([A-Za-z0-9_.]{2,30})")


def assert_synthetic_prefix_consistency() -> None:
    mapped_prefixes = {
        prefix[: -len("_creator_")]
        for prefix in PREFIX_TO_NICHE
        if prefix.endswith("_creator_")
    }
    missing = set(SYNTHETIC_HANDLE_PREFIXES) - mapped_prefixes
    if missing:
        raise ValueError(f"Regex prefixes missing from PREFIX_TO_NICHE: {sorted(missing)}")


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


def _looks_like_phone(token: str) -> bool:
    digits_only = re.sub(r"\D", "", token)
    if not 10 <= len(digits_only) <= 15:
        return False
    return bool(re.search(r"[().\-\s+]", token))


def _is_safe_handle(handle_without_at: str) -> bool:
    if handle_without_at == "creator_handle":
        return True
    return bool(SYNTHETIC_HANDLE_PATTERN.fullmatch(handle_without_at))


def detect_pii(text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    for match in EMAIL_PATTERN.finditer(text):
        findings.append({"type": "email", "value": match.group(0)})

    for match in URL_PATTERN.finditer(text):
        findings.append({"type": "url", "value": match.group(0)})

    for match in PHONE_PATTERN.finditer(text):
        value = match.group(0)
        if _looks_like_phone(value):
            findings.append({"type": "phone", "value": value})

    for match in HANDLE_PATTERN.finditer(text):
        handle_without_at = match.group(1)
        if _is_safe_handle(handle_without_at):
            continue
        findings.append({"type": "handle", "value": match.group(0)})

    return findings


def determine_drop_candidates(rows: list[dict[str, Any]]) -> tuple[set[int], set[str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dropped_line_numbers: set[int] = set()
    creators_with_conflicts: set[str] = set()

    for row in rows:
        creator_id = row["creator_id"]
        key = creator_id if creator_id is not None else f"__missing__:{row['line_number']}"
        grouped[key].append(row)

    for key, group_rows in grouped.items():
        if key.startswith("__missing__:"):
            for row in group_rows:
                dropped_line_numbers.add(row["line_number"])
            continue

        creator_id = key
        expected_niche = infer_niche(creator_id)
        inferred_niches = {row["inferred_niche"] for row in group_rows}

        if len(inferred_niches) > 1:
            creators_with_conflicts.add(creator_id)
            if expected_niche == "unknown":
                for row in group_rows:
                    dropped_line_numbers.add(row["line_number"])
            else:
                for row in group_rows:
                    if row["inferred_niche"] != expected_niche:
                        dropped_line_numbers.add(row["line_number"])
            continue

        if expected_niche == "unknown":
            observed_niches: set[str] = set()
            for row in group_rows:
                observed_niches.update(row["observed_niches"])
            if len(observed_niches) > 1:
                creators_with_conflicts.add(creator_id)
                for row in group_rows:
                    dropped_line_numbers.add(row["line_number"])

    return dropped_line_numbers, creators_with_conflicts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate fine-tune JSONL for niche consistency and PII.")
    parser.add_argument("input_jsonl", help="Input JSONL dataset path.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show additional redacted diagnostics (never prints raw PII values).",
    )
    return parser.parse_args()


def _redact_pii_value(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:2]}***"


def main() -> int:
    assert_synthetic_prefix_consistency()
    args = parse_args()
    input_path = Path(args.input_jsonl).resolve()

    rows: list[dict[str, Any]] = []
    total_lines = 0

    mismatch_lines: set[int] = set()
    missing_creator_lines: set[int] = set()
    pii_lines: set[int] = set()
    bad_json_lines: set[int] = set()
    pii_findings: list[dict[str, Any]] = []

    with input_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue

            total_lines += 1
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                bad_json_lines.add(line_number)
                continue
            messages = obj.get("messages")
            if not isinstance(messages, list):
                missing_creator_lines.add(line_number)
                rows.append(
                    {
                        "line_number": line_number,
                        "creator_id": None,
                        "inferred_niche": "unknown",
                        "observed_niches": set(),
                    }
                )
                continue

            creator_id, creator_note = extract_creator_id(messages)
            if creator_id is None:
                missing_creator_lines.add(line_number)

            inferred_niche = infer_niche(creator_id)
            observed_niches: set[str] = set()

            for message in messages:
                if not isinstance(message, dict):
                    continue

                content = message.get("content")
                if not isinstance(content, str):
                    continue

                role = message.get("role")
                if role in {"assistant", "system"}:
                    observed_niches.update(extract_niche_mentions(content))
                for finding in detect_pii(content):
                    pii_lines.add(line_number)
                    pii_findings.append(
                        {
                            "line_number": line_number,
                            "creator_id": creator_id,
                            **finding,
                        }
                    )

            if inferred_niche != "unknown":
                if any(label != inferred_niche for label in observed_niches):
                    mismatch_lines.add(line_number)

            rows.append(
                {
                    "line_number": line_number,
                    "creator_id": creator_id,
                    "creator_note": creator_note,
                    "inferred_niche": inferred_niche,
                    "observed_niches": observed_niches,
                }
            )

    drop_candidates, creators_with_conflicts = determine_drop_candidates(rows)
    lines_fixed = len(mismatch_lines | pii_lines)
    lines_dropped = len(drop_candidates)

    has_issues = any(
        [
            mismatch_lines,
            creators_with_conflicts,
            missing_creator_lines,
            bad_json_lines,
            pii_findings,
            drop_candidates,
        ]
    )

    print(f"Total lines: {total_lines}")
    print(f"Lines fixed: {lines_fixed}")
    print(f"Lines dropped: {lines_dropped}")
    print(f"Creators with conflicts: {len(creators_with_conflicts)}")
    print(f"PII replacements: {len(pii_findings)}")
    print(f"Bad JSON lines: {len(bad_json_lines)}")

    if mismatch_lines:
        print(f"Niche mismatch lines: {len(mismatch_lines)}")
        print(f"Sample mismatch lines: {sorted(mismatch_lines)[:10]}")
    if missing_creator_lines:
        print(f"Missing/ambiguous creator lines: {len(missing_creator_lines)}")
        print(f"Sample missing lines: {sorted(missing_creator_lines)[:10]}")
    if creators_with_conflicts:
        print(f"Creators with conflicts (sample): {sorted(creators_with_conflicts)[:10]}")
    if bad_json_lines:
        print(f"Sample bad JSON lines: {sorted(bad_json_lines)[:10]}")
    if pii_findings:
        pii_line_numbers = sorted(pii_lines)
        print(f"PII-affected lines: {len(pii_line_numbers)}")
        print(f"Sample PII lines: {pii_line_numbers[:10]}")

        pii_by_type: dict[str, int] = defaultdict(int)
        for finding in pii_findings:
            finding_type = finding.get("type")
            if isinstance(finding_type, str):
                pii_by_type[finding_type] += 1
        if pii_by_type:
            print(f"PII findings by type: {dict(sorted(pii_by_type.items()))}")

        if args.verbose:
            redacted_samples = []
            for finding in pii_findings[:5]:
                raw_value = finding.get("value")
                redacted_samples.append(
                    {
                        "line_number": finding.get("line_number"),
                        "type": finding.get("type"),
                        "value": _redact_pii_value(str(raw_value)) if isinstance(raw_value, str) else "***",
                    }
                )
            print(f"Sample redacted PII findings: {redacted_samples}")

    return 1 if has_issues else 0


if __name__ == "__main__":
    sys.exit(main())
