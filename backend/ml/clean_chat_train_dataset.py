from __future__ import annotations

import argparse
import copy
import json
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("backend/data/chat_train.jsonl")

NICHES = ("fitness", "food", "tech", "style", "lifestyle")

NICKNAME_TO_NICHE = {
    "fit": "fitness",
    "fitness": "fitness",
    "chef": "food",
    "food": "food",
    "tech": "tech",
    "style": "style",
    "fashion": "style",
    "life": "lifestyle",
    "lifestyle": "lifestyle",
}

NICHE_ALIAS = {
    "fitness": "fitness",
    "food": "food",
    "technology": "tech",
    "tech": "tech",
    "style": "style",
    "fashion": "style",
    "lifestyle": "lifestyle",
}

NICHE_KEYWORDS = {
    "fitness": ("workout", "gym", "health", "training", "exercise", "protein", "routine"),
    "food": ("recipe", "restaurant", "cooking", "cook", "meal", "kitchen", "food"),
    "tech": ("tutorial", "coding", "code", "gadget", "software", "developer", "tech"),
    "style": ("fashion", "outfit", "styling", "style", "wardrobe", "lookbook"),
    "lifestyle": ("day in my life", "vlog", "room", "behind-the-scenes", "q&a", "self care", "mindset"),
}

CANONICAL_SUGGESTIONS = {
    "fitness": ["Workout transformation reel", "Quick exercise tutorial"],
    "food": ["Recipe tutorial reel", "Restaurant review"],
    "tech": ["Coding tips tutorial", "Gadget review reel"],
    "style": ["Outfit transition reel", "Styling tips"],
    "lifestyle": ["Day in my life vlog", "Room/space tour"],
}

TARGETED_NICHES = {"fitness", "food", "tech", "style", "lifestyle"}


@dataclass
class ProcessedRow:
    line_no: int
    obj: dict[str, Any]
    system_prompt: str
    content_suggestions: tuple[str, ...]
    similarity_text: str
    username_changed: bool
    suggestions_changed: bool


def _read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"Invalid row at {path}:{line_no}: top-level JSON must be object")
            rows.append((line_no, parsed))
    return rows


def _extract_message(row: dict[str, Any], role: str) -> dict[str, Any] | None:
    messages = row.get("messages")
    if not isinstance(messages, list):
        return None
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == role:
            return msg
    return None


def _parse_json_content(message: dict[str, Any] | None) -> dict[str, Any] | None:
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


def _encode_json_content(message: dict[str, Any], payload: dict[str, Any]) -> None:
    message["content"] = json.dumps(payload, ensure_ascii=False)


def _normalize_space(text: str) -> str:
    return " ".join(text.lower().split())


def _first_profile_username(rows: list[tuple[int, dict[str, Any]]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    next_id = 1
    for _, row in rows:
        user_msg = _extract_message(row, "user")
        user_payload = _parse_json_content(user_msg)
        profile = (((user_payload or {}).get("input") or {}).get("profile") or {})
        username = profile.get("username")
        if not isinstance(username, str) or not username.strip():
            continue
        key = username.strip()
        if key not in mapping:
            mapping[key] = f"user_{next_id:03d}"
            next_id += 1
    return mapping


def _flatten_text(value: Any, sink: list[str]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _flatten_text(item, sink)
        return
    if isinstance(value, list):
        for item in value:
            _flatten_text(item, sink)
        return
    if isinstance(value, str):
        sink.append(value)


def _parse_weekly_plan_niche(action_plan: dict[str, Any]) -> str | None:
    weekly_plan = action_plan.get("weekly_plan")
    if not isinstance(weekly_plan, list):
        return None
    combined = " ".join(item for item in weekly_plan if isinstance(item, str))
    match = re.search(r"focus content on your ([a-zA-Z ]+) niche", combined, flags=re.IGNORECASE)
    if not match:
        return None
    raw = _normalize_space(match.group(1))
    return NICHE_ALIAS.get(raw)


def _detect_niche(profile: dict[str, Any], posts: list[dict[str, Any]], action_plan: dict[str, Any]) -> str | None:
    scores: Counter[str] = Counter()

    username = profile.get("username")
    if isinstance(username, str):
        prefix_match = re.match(r"([a-zA-Z]+)_creator_", username.strip())
        if prefix_match:
            mapped = NICKNAME_TO_NICHE.get(prefix_match.group(1).lower())
            if mapped:
                scores[mapped] += 6

    weekly_niche = _parse_weekly_plan_niche(action_plan)
    if weekly_niche:
        scores[weekly_niche] += 6

    for key in ("niche", "primary_niche", "secondary_niche"):
        value = profile.get(key)
        if isinstance(value, str):
            mapped = NICHE_ALIAS.get(_normalize_space(value))
            if mapped:
                scores[mapped] += 5

    text_chunks: list[str] = []
    captions: list[str] = []
    for post in posts:
        if isinstance(post, dict):
            caption = post.get("caption")
            if isinstance(caption, str):
                captions.append(caption)
    text_chunks.extend(captions)
    diagnosis = action_plan.get("diagnosis")
    if isinstance(diagnosis, str):
        text_chunks.append(diagnosis)
    weekly = action_plan.get("weekly_plan")
    if isinstance(weekly, list):
        text_chunks.extend(item for item in weekly if isinstance(item, str))

    blob = _normalize_space(" ".join(text_chunks))
    for niche, keywords in NICHE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in blob:
                scores[niche] += 1

    if not scores:
        return None

    ordered = scores.most_common()
    top_niche, top_score = ordered[0]
    if top_score <= 0:
        return None
    if len(ordered) > 1 and ordered[1][1] == top_score:
        return None
    return top_niche


def _suggestions_aligned(suggestions: list[str], niche: str) -> bool:
    keywords = NICHE_KEYWORDS.get(niche, ())
    if not keywords:
        return True
    blob = _normalize_space(" ".join(suggestions))
    return any(keyword in blob for keyword in keywords)


def _normalized_similarity_text(user_payload: dict[str, Any], assistant_payload: dict[str, Any], system_prompt: str) -> str:
    user_copy = copy.deepcopy(user_payload)
    profile = (((user_copy.get("input") or {}).get("profile") or {}))
    if isinstance(profile, dict):
        profile.pop("username", None)
    user_text = json.dumps(user_copy, sort_keys=True, ensure_ascii=False)
    assistant_text = json.dumps(assistant_payload, sort_keys=True, ensure_ascii=False)
    return _normalize_space(system_prompt + "\n" + user_text + "\n" + assistant_text)


def _process_row(
    line_no: int,
    row: dict[str, Any],
    username_map: dict[str, str],
) -> ProcessedRow:
    obj = copy.deepcopy(row)
    user_msg = _extract_message(obj, "user")
    assistant_msg = _extract_message(obj, "assistant")
    system_msg = _extract_message(obj, "system")

    system_prompt = ""
    if isinstance(system_msg, dict) and isinstance(system_msg.get("content"), str):
        system_prompt = system_msg["content"]

    user_payload = _parse_json_content(user_msg)
    assistant_payload = _parse_json_content(assistant_msg)
    if user_payload is None or assistant_payload is None or user_msg is None or assistant_msg is None:
        return ProcessedRow(
            line_no=line_no,
            obj=obj,
            system_prompt=system_prompt,
            content_suggestions=tuple(),
            similarity_text=_normalize_space(system_prompt),
            username_changed=False,
            suggestions_changed=False,
        )

    input_payload = user_payload.get("input")
    profile = (input_payload or {}).get("profile") if isinstance(input_payload, dict) else None
    posts = (input_payload or {}).get("posts") if isinstance(input_payload, dict) else None
    profile = profile if isinstance(profile, dict) else {}
    posts = posts if isinstance(posts, list) else []

    action_plan = assistant_payload.get("action_plan")
    action_plan = action_plan if isinstance(action_plan, dict) else {}

    suggestions_changed = False
    username_changed = False

    detected_niche = _detect_niche(profile, [p for p in posts if isinstance(p, dict)], action_plan)
    raw_suggestions = action_plan.get("content_suggestions")
    suggestions = [str(item) for item in raw_suggestions] if isinstance(raw_suggestions, list) else []

    if detected_niche in TARGETED_NICHES and isinstance(raw_suggestions, list):
        if not _suggestions_aligned(suggestions, detected_niche):
            replacement = CANONICAL_SUGGESTIONS.get(detected_niche)
            if replacement is not None and suggestions != replacement:
                action_plan["content_suggestions"] = list(replacement)
                assistant_payload["action_plan"] = action_plan
                suggestions = list(replacement)
                suggestions_changed = True

    username = profile.get("username")
    if isinstance(username, str) and username.strip():
        mapped = username_map.get(username.strip())
        if mapped and mapped != username:
            profile["username"] = mapped
            if isinstance(input_payload, dict):
                input_payload["profile"] = profile
                user_payload["input"] = input_payload
            username_changed = True

    _encode_json_content(user_msg, user_payload)
    _encode_json_content(assistant_msg, assistant_payload)

    suggestions_tuple = tuple(item for item in suggestions if isinstance(item, str))
    similarity_text = _normalized_similarity_text(user_payload, assistant_payload, system_prompt)

    return ProcessedRow(
        line_no=line_no,
        obj=obj,
        system_prompt=system_prompt,
        content_suggestions=suggestions_tuple,
        similarity_text=similarity_text,
        username_changed=username_changed,
        suggestions_changed=suggestions_changed,
    )


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _dedupe_rows(rows: list[ProcessedRow], threshold: float) -> tuple[list[ProcessedRow], int]:
    grouped: dict[tuple[str, tuple[str, ...]], list[ProcessedRow]] = {}
    for row in rows:
        key = (row.system_prompt, row.content_suggestions)
        grouped.setdefault(key, []).append(row)

    kept: list[ProcessedRow] = []
    removed = 0
    for _, group in grouped.items():
        representatives: list[ProcessedRow] = []
        for row in group:
            is_dup = False
            for kept_row in representatives:
                if _similarity(row.similarity_text, kept_row.similarity_text) > threshold:
                    is_dup = True
                    break
            if is_dup:
                removed += 1
            else:
                representatives.append(row)
        kept.extend(representatives)

    kept.sort(key=lambda item: item.line_no)
    return kept, removed


def _validate_rows(rows: list[ProcessedRow]) -> None:
    for row in rows:
        encoded = json.dumps(row.obj, ensure_ascii=False)
        json.loads(encoded)


def _write_rows(path: Path, rows: list[ProcessedRow], force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Output exists: {path}. Re-run with --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    if temp_path.exists():
        temp_path.unlink()

    with temp_path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row.obj, ensure_ascii=False) + "\n")

    temp_path.replace(path)


def _default_output(input_path: Path) -> Path:
    return input_path.with_name(input_path.stem + ".cleaned.jsonl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean chat_train JSONL (niche alignment, username anonymization, dedupe).")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input JSONL path.")
    parser.add_argument("--output", type=Path, default=None, help="Output JSONL path (default: <input>.cleaned.jsonl).")
    parser.add_argument("--force", action="store_true", help="Allow overwriting an existing output path.")
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.90,
        help="Near-duplicate threshold for similarity ratio (strictly greater than this value is duplicate).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path: Path = args.input
    output_path: Path = args.output or _default_output(input_path)
    threshold = float(args.similarity_threshold)

    if threshold < 0.0 or threshold > 1.0:
        raise ValueError("--similarity-threshold must be between 0.0 and 1.0")
    if input_path.resolve() == output_path.resolve() and not args.force:
        raise FileExistsError("Refusing to overwrite input file without --force.")

    raw_rows = _read_jsonl(input_path)
    username_map = _first_profile_username(raw_rows)

    processed = [_process_row(line_no, row, username_map) for line_no, row in raw_rows]
    deduped, removed_count = _dedupe_rows(processed, threshold)
    _validate_rows(deduped)
    _write_rows(output_path, deduped, force=args.force)

    print(f"input_rows={len(raw_rows)}")
    print(f"output_rows={len(deduped)}")
    print(f"usernames_mapped={len(username_map)}")
    print(f"rows_with_username_changes={sum(1 for row in processed if row.username_changed)}")
    print(f"rows_with_suggestion_fixes={sum(1 for row in processed if row.suggestions_changed)}")
    print(f"near_duplicates_removed={removed_count}")
    print(f"output_path={output_path}")


if __name__ == "__main__":
    main()
