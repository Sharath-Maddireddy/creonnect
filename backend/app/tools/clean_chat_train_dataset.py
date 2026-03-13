#!/usr/bin/env python3
"""Deterministic cleaner/validator for chat_train JSONL datasets."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("backend/data/chat_train.jsonl")
DEFAULT_OUTPUT = Path("backend/data/chat_train.cleaned.jsonl")
DEFAULT_DATA_DIR = Path("backend/data")

VALID_DEDUPE_STRATEGIES = ("snapshot", "username", "merge")

USERNAME_PREFIX_TO_NICHE: dict[str, str] = {
    "fit": "fitness",
    "fitness": "fitness",
    "chef": "food",
    "food": "food",
    "tech": "tech",
    "technology": "tech",
    "style": "style",
    "fashion": "style",
    "life": "lifestyle",
    "lifestyle": "lifestyle",
}

NICHE_ALIASES: dict[str, str] = {
    "technology": "tech",
    "fashion": "style",
}

NICHE_CONTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "fitness": ("workout", "gym", "health", "training", "exercise", "ab routine", "protein"),
    "food": ("recipe", "restaurant", "cooking", "cook", "meal", "kitchen", "food"),
    "tech": ("tutorial", "coding", "code", "gadget", "software", "developer", "tech", "apps"),
    "style": ("fashion", "outfit", "styling", "style", "wardrobe", "lookbook", "grwm"),
    "lifestyle": ("day in my life", "vlog", "routine", "mindset", "self care", "wellness", "life"),
}

CANONICAL_SUGGESTIONS: dict[str, list[str]] = {
    "fitness": ["Workout transformation reel", "Quick exercise tutorial"],
    "food": ["Recipe tutorial reel", "Restaurant review"],
    "tech": ["Coding tips tutorial", "Gadget review reel"],
    "style": ["Outfit transition reel", "Styling tips"],
    "lifestyle": ["Day in my life vlog", "Room/space tour"],
}

SUGGESTION_BUCKET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "fitness": ("workout", "exercise", "gym", "training", "fit"),
    "food": ("recipe", "restaurant", "cooking", "meal", "food"),
    "tech": ("coding", "code", "gadget", "software", "tech", "tutorial"),
    "style": ("fashion", "outfit", "styling", "lookbook"),
    "lifestyle": ("day in my life", "vlog", "behind-the-scenes", "q&a", "room/space"),
}

IGNORE_DATASET_PATTERNS = (".bak", "_before_", ".orig", ".tmp")


@dataclass
class Record:
    line_no: int
    row: dict[str, Any]
    username: str | None
    niche: str | None
    snapshot_date: str
    prompt_template_version: str
    changed: bool


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_no}: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected object at line {line_no}, got {type(parsed).__name__}")
            rows.append((line_no, parsed))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]], force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Output exists: {path}. Use --write-inplace or choose a different --out path.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp_path.replace(path)


def _extract_message(row: dict[str, Any], role: str) -> dict[str, Any] | None:
    messages = row.get("messages")
    if not isinstance(messages, list):
        return None
    for message in messages:
        if isinstance(message, dict) and message.get("role") == role:
            return message
    return None


def _parse_message_json(message: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str):
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _set_message_json(message: dict[str, Any], payload: dict[str, Any]) -> None:
    message["content"] = json.dumps(payload, ensure_ascii=False)


def _canonical_niche(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = _norm(value)
    if lowered in CANONICAL_SUGGESTIONS:
        return lowered
    return NICHE_ALIASES.get(lowered)


def _niche_from_profile(profile: dict[str, Any]) -> str | None:
    for field in ("niche", "primary_niche", "secondary_niche"):
        val = profile.get(field)
        canonical = _canonical_niche(val if isinstance(val, str) else None)
        if canonical is not None:
            return canonical
    return None


def _niche_from_username(username: str | None) -> str | None:
    if not isinstance(username, str):
        return None
    match = re.match(r"^([a-z]+)_creator_\d+$", username.strip().lower())
    if not match:
        return None
    return USERNAME_PREFIX_TO_NICHE.get(match.group(1))


def _niche_from_weekly_plan(action_plan: dict[str, Any]) -> str | None:
    weekly_plan = action_plan.get("weekly_plan")
    if not isinstance(weekly_plan, list):
        return None
    joined = " ".join(item for item in weekly_plan if isinstance(item, str))
    match = re.search(r"focus content on your ([a-zA-Z ]+) niche", joined, re.IGNORECASE)
    if not match:
        return None
    return _canonical_niche(match.group(1))


def _niche_from_posts(posts: list[dict[str, Any]]) -> str | None:
    captions = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        caption = post.get("caption")
        if isinstance(caption, str):
            captions.append(caption)
    if not captions:
        return None
    blob = _norm(" ".join(captions))
    scores: Counter[str] = Counter()
    for niche, keywords in NICHE_CONTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in blob:
                scores[niche] += 1
    if not scores:
        return None
    ranked = scores.most_common()
    top_niche, top_score = ranked[0]
    if top_score <= 0:
        return None
    if len(ranked) > 1 and ranked[1][1] == top_score:
        return None
    return top_niche


def _detect_niche(profile: dict[str, Any], posts: list[dict[str, Any]], action_plan: dict[str, Any]) -> str | None:
    return (
        _niche_from_profile(profile)
        or _niche_from_username(profile.get("username") if isinstance(profile.get("username"), str) else None)
        or _niche_from_weekly_plan(action_plan)
        or _niche_from_posts(posts)
    )


def _bucket_suggestion(text: str) -> str | None:
    normalized = _norm(text)
    bucket_scores: Counter[str] = Counter()
    for niche, keywords in SUGGESTION_BUCKET_KEYWORDS.items():
        for keyword in keywords:
            if keyword in normalized:
                bucket_scores[niche] += 1
    if not bucket_scores:
        return None
    ranked = bucket_scores.most_common()
    top_niche, top_score = ranked[0]
    if top_score <= 0:
        return None
    if len(ranked) > 1 and ranked[1][1] == top_score:
        return None
    return top_niche


def _suggestions_clearly_mismatched(suggestions: list[str], niche: str) -> bool:
    buckets = [_bucket_suggestion(item) for item in suggestions]
    known_buckets = [bucket for bucket in buckets if bucket is not None]
    if not known_buckets:
        return False
    return all(bucket != niche for bucket in known_buckets)


def _normalize_prompt_template_version(system_content: str) -> str:
    digest = hashlib.sha1(system_content.encode("utf-8")).hexdigest()[:8]
    return f"template_{digest}"


def _ensure_weekly_niche_alignment(action_plan: dict[str, Any], niche: str) -> bool:
    weekly_plan = action_plan.get("weekly_plan")
    if not isinstance(weekly_plan, list):
        return False

    changed = False
    aligned_line = f"Focus content on your {niche} niche for audience alignment"
    replaced = False
    updated: list[Any] = []
    for item in weekly_plan:
        if isinstance(item, str) and re.search(r"focus content on your [a-zA-Z ]+ niche", item, re.IGNORECASE):
            updated.append(aligned_line)
            replaced = True
            if item != aligned_line:
                changed = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(aligned_line)
        changed = True

    if changed:
        action_plan["weekly_plan"] = updated
    return changed


def _append_cleanup_note(assistant_payload: dict[str, Any], note: str) -> None:
    notes_raw = assistant_payload.get("cleanup_notes")
    notes = notes_raw if isinstance(notes_raw, list) else []
    if note not in notes:
        notes.append(note)
    assistant_payload["cleanup_notes"] = notes


def _prepare_record(line_no: int, row: dict[str, Any], snapshot_default: str) -> Record:
    cloned = copy.deepcopy(row)
    user_msg = _extract_message(cloned, "user")
    assistant_msg = _extract_message(cloned, "assistant")
    system_msg = _extract_message(cloned, "system")

    if user_msg is None or assistant_msg is None:
        return Record(
            line_no=line_no,
            row=cloned,
            username=None,
            niche=None,
            snapshot_date=snapshot_default,
            prompt_template_version="template_unknown",
            changed=False,
        )

    user_payload = _parse_message_json(user_msg)
    assistant_payload = _parse_message_json(assistant_msg)
    if user_payload is None or assistant_payload is None:
        return Record(
            line_no=line_no,
            row=cloned,
            username=None,
            niche=None,
            snapshot_date=snapshot_default,
            prompt_template_version="template_unknown",
            changed=False,
        )

    system_content = ""
    if isinstance(system_msg, dict):
        raw_system = system_msg.get("content")
        if isinstance(raw_system, str):
            system_content = raw_system

    input_payload = user_payload.get("input")
    input_payload = input_payload if isinstance(input_payload, dict) else {}
    profile = input_payload.get("profile")
    profile = profile if isinstance(profile, dict) else {}
    posts = input_payload.get("posts")
    posts = posts if isinstance(posts, list) else []

    action_plan = assistant_payload.get("action_plan")
    action_plan = action_plan if isinstance(action_plan, dict) else {}

    changed = False
    username = profile.get("username") if isinstance(profile.get("username"), str) else None
    snapshot_date = profile.get("snapshot_date") if isinstance(profile.get("snapshot_date"), str) else snapshot_default
    prompt_template_version = (
        assistant_payload.get("prompt_template_version")
        if isinstance(assistant_payload.get("prompt_template_version"), str)
        else _normalize_prompt_template_version(system_content)
    )

    if profile.get("snapshot_date") != snapshot_date:
        profile["snapshot_date"] = snapshot_date
        changed = True
        _append_cleanup_note(assistant_payload, "added_snapshot_date")

    if assistant_payload.get("prompt_template_version") != prompt_template_version:
        assistant_payload["prompt_template_version"] = prompt_template_version
        changed = True
        _append_cleanup_note(assistant_payload, "added_prompt_template_version")

    niche = _detect_niche(profile, [item for item in posts if isinstance(item, dict)], action_plan)
    if niche is not None:
        if profile.get("niche") != niche:
            profile["niche"] = niche
            changed = True
            _append_cleanup_note(assistant_payload, "normalized_profile_niche")

        if _ensure_weekly_niche_alignment(action_plan, niche):
            changed = True
            _append_cleanup_note(assistant_payload, "normalized_weekly_niche_alignment")

        raw_suggestions = action_plan.get("content_suggestions")
        if isinstance(raw_suggestions, list):
            suggestions = [str(item) for item in raw_suggestions]
            if _suggestions_clearly_mismatched(suggestions, niche):
                canonical = CANONICAL_SUGGESTIONS[niche]
                if suggestions != canonical:
                    action_plan["content_suggestions"] = list(canonical)
                    changed = True
                    _append_cleanup_note(assistant_payload, "replaced_cross_niche_content_suggestions")

    input_payload["profile"] = profile
    user_payload["input"] = input_payload
    assistant_payload["action_plan"] = action_plan

    _set_message_json(user_msg, user_payload)
    _set_message_json(assistant_msg, assistant_payload)

    return Record(
        line_no=line_no,
        row=cloned,
        username=username,
        niche=niche,
        snapshot_date=snapshot_date,
        prompt_template_version=prompt_template_version,
        changed=changed,
    )


def _dedupe_records(records: list[Record], strategy: str) -> tuple[list[Record], int]:
    if strategy not in VALID_DEDUPE_STRATEGIES:
        raise ValueError(f"Unknown dedupe strategy: {strategy}")

    removed = 0
    if strategy in {"snapshot", "username"}:
        by_key: dict[tuple[str, ...], Record] = {}
        passthrough: list[Record] = []
        for record in records:
            if not record.username:
                passthrough.append(record)
                continue
            if strategy == "snapshot":
                key = (record.username, record.snapshot_date, record.prompt_template_version)
            else:
                key = (record.username,)
            if key in by_key:
                removed += 1
            by_key[key] = record
        merged = list(by_key.values()) + passthrough
        merged.sort(key=lambda item: item.line_no)
        return merged, removed

    grouped: dict[str, list[Record]] = defaultdict(list)
    no_username: list[Record] = []
    for record in records:
        if record.username:
            grouped[record.username].append(record)
        else:
            no_username.append(record)

    merged_records: list[Record] = []
    for username, group in grouped.items():
        if len(group) == 1:
            merged_records.append(group[0])
            continue

        removed += len(group) - 1
        sorted_group = sorted(group, key=lambda item: item.line_no)
        base = copy.deepcopy(sorted_group[-1])

        niche_votes = [item.niche for item in sorted_group if isinstance(item.niche, str)]
        canonical_niche: str | None = None
        if niche_votes:
            canonical_niche = Counter(niche_votes).most_common(1)[0][0]

        user_msg = _extract_message(base.row, "user")
        assistant_msg = _extract_message(base.row, "assistant")
        user_payload = _parse_message_json(user_msg) if user_msg else None
        assistant_payload = _parse_message_json(assistant_msg) if assistant_msg else None
        if user_payload and assistant_payload:
            input_payload = user_payload.get("input")
            input_payload = input_payload if isinstance(input_payload, dict) else {}
            profile = input_payload.get("profile")
            profile = profile if isinstance(profile, dict) else {}
            action_plan = assistant_payload.get("action_plan")
            action_plan = action_plan if isinstance(action_plan, dict) else {}

            if canonical_niche:
                profile["niche"] = canonical_niche
                _ensure_weekly_niche_alignment(action_plan, canonical_niche)
                action_plan["content_suggestions"] = list(CANONICAL_SUGGESTIONS[canonical_niche])

            profile["snapshot_date"] = "unknown"
            input_payload["profile"] = profile
            user_payload["input"] = input_payload
            assistant_payload["action_plan"] = action_plan
            _append_cleanup_note(assistant_payload, "merged_duplicate_username_records")

            if user_msg:
                _set_message_json(user_msg, user_payload)
            if assistant_msg:
                _set_message_json(assistant_msg, assistant_payload)
            base.niche = canonical_niche

        merged_records.append(base)

    merged_records.extend(no_username)
    merged_records.sort(key=lambda item: item.line_no)
    return merged_records, removed


def list_dataset_files(data_dir: Path) -> list[Path]:
    listed: list[Path] = []
    for path in data_dir.rglob("*.jsonl"):
        relative = path.relative_to(data_dir)
        if "_archive" in relative.parts:
            continue
        name_lower = path.name.lower()
        if any(pattern in name_lower for pattern in IGNORE_DATASET_PATTERNS):
            continue
        listed.append(path)
    return sorted(listed)


def _validate_niche_alignment(rows: list[dict[str, Any]]) -> tuple[set[int], dict[str, set[str]], set[str]]:
    mismatched_lines: set[int] = set()
    username_to_niches: dict[str, set[str]] = defaultdict(set)
    duplicate_usernames: set[str] = set()
    seen_usernames: set[str] = set()

    for line_no, row in enumerate(rows, 1):
        user_msg = _extract_message(row, "user")
        assistant_msg = _extract_message(row, "assistant")
        user_payload = _parse_message_json(user_msg)
        assistant_payload = _parse_message_json(assistant_msg)
        if user_payload is None or assistant_payload is None:
            continue

        input_payload = user_payload.get("input")
        input_payload = input_payload if isinstance(input_payload, dict) else {}
        profile = input_payload.get("profile")
        profile = profile if isinstance(profile, dict) else {}
        posts = input_payload.get("posts")
        posts = posts if isinstance(posts, list) else []
        action_plan = assistant_payload.get("action_plan")
        action_plan = action_plan if isinstance(action_plan, dict) else {}

        username = profile.get("username")
        if isinstance(username, str):
            if username in seen_usernames:
                duplicate_usernames.add(username)
            seen_usernames.add(username)

        niche = _detect_niche(profile, [item for item in posts if isinstance(item, dict)], action_plan)
        if isinstance(username, str) and niche:
            username_to_niches[username].add(niche)

        raw_suggestions = action_plan.get("content_suggestions")
        if niche and isinstance(raw_suggestions, list):
            suggestions = [str(item) for item in raw_suggestions]
            if _suggestions_clearly_mismatched(suggestions, niche):
                mismatched_lines.add(line_no)

    return mismatched_lines, username_to_niches, duplicate_usernames


def validate_clean_dataset(path: Path, dedupe_strategy: str, data_dir: Path) -> int:
    raw_rows = _read_jsonl(path)
    rows = [row for _, row in raw_rows]
    mismatched_lines, username_to_niches, duplicate_usernames = _validate_niche_alignment(rows)
    conflict_usernames = sorted(
        username
        for username, niches in username_to_niches.items()
        if len(niches) > 1
    )
    listed_datasets = list_dataset_files(data_dir)
    listed_names = [dataset.name for dataset in listed_datasets]
    all_jsonl_files = sorted(data_dir.rglob("*.jsonl"))
    backup_in_dir = [
        path.name
        for path in all_jsonl_files
        if ".bak" in path.name.lower() or "_before_" in path.name.lower()
    ]

    has_issues = False
    print(f"validate_path={path}")
    print(f"records={len(rows)}")
    print(f"mismatched_niche_lines={len(mismatched_lines)}")
    if mismatched_lines:
        print(f"sample_mismatched_niche_lines={sorted(mismatched_lines)[:10]}")
        has_issues = True

    if dedupe_strategy == "snapshot":
        print(f"duplicate_usernames_allowed_for_snapshot={len(duplicate_usernames)}")
    else:
        print(f"duplicate_usernames={len(duplicate_usernames)}")
        if duplicate_usernames:
            print(f"sample_duplicate_usernames={sorted(duplicate_usernames)[:10]}")
            has_issues = True

    print(f"usernames_with_conflicting_niches={len(conflict_usernames)}")
    if conflict_usernames:
        print(f"sample_usernames_with_conflicting_niches={conflict_usernames[:10]}")
        has_issues = True

    print(f"listed_datasets={listed_names}")
    print(f"backup_files_in_dir={backup_in_dir}")
    if backup_in_dir:
        has_issues = True

    return 1 if has_issues else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministically clean and validate chat_train JSONL.")
    parser.add_argument("--in", dest="input_path", type=Path, default=DEFAULT_INPUT, help="Input JSONL path.")
    parser.add_argument("--out", dest="output_path", type=Path, default=DEFAULT_OUTPUT, help="Output JSONL path.")
    parser.add_argument("--write-inplace", action="store_true", help="Overwrite input file with cleaned rows.")
    parser.add_argument(
        "--dedupe-strategy",
        choices=VALID_DEDUPE_STRATEGIES,
        default="merge",
        help="Dedupe strategy for repeated profile.username values.",
    )
    parser.add_argument(
        "--snapshot-default",
        default="unknown",
        help="Fallback snapshot_date assigned when missing.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate dataset invariants and return non-zero on violations.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Dataset directory used for dataset-listing backup exclusion checks.",
    )
    parser.add_argument("--force", action="store_true", help="Allow overwriting existing output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input_path
    output_path = input_path if args.write_inplace else args.output_path

    if args.validate:
        return validate_clean_dataset(input_path, args.dedupe_strategy, args.data_dir)

    raw_rows = _read_jsonl(input_path)
    prepared = [_prepare_record(line_no, row, args.snapshot_default) for line_no, row in raw_rows]
    deduped, removed_duplicates = _dedupe_records(prepared, args.dedupe_strategy)
    cleaned_rows = [record.row for record in deduped]

    force = bool(args.force or args.write_inplace)
    _write_jsonl(output_path, cleaned_rows, force=force)

    changed_count = sum(1 for record in prepared if record.changed)
    print(f"input_rows={len(raw_rows)}")
    print(f"output_rows={len(cleaned_rows)}")
    print(f"rows_with_cleanup_changes={changed_count}")
    print(f"duplicates_removed={removed_duplicates}")
    print(f"dedupe_strategy={args.dedupe_strategy}")
    print(f"output_path={output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
