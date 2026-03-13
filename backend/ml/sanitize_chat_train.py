"""Sanitize chat training data.

Run:
  python -m backend.ml.sanitize_chat_train
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


INPUT_PATH = Path("backend/data/chat_train.jsonl")
OUTPUT_PATH = Path("backend/data/chat_train.sanitized.jsonl")
DROPPED_PATH = Path("backend/data/chat_train.dropped.jsonl")

IDENTIFIER_KEYS = {"username", "handle", "full_name", "id", "account_id", "user_id"}
INSTAGRAM_URL_RE = re.compile(
    r"(https?://(?:www\.)?instagram\.com/)([A-Za-z0-9._-]+)",
    re.IGNORECASE,
)

FOOD_NICHE_TERMS = ("food", "cooking")
TECH_NICHE_TERMS = ("technology",)
FITNESS_SUGGESTION_TERMS = ("workout", "fitness")
TECH_MISMATCH_SUGGESTION_TERMS = ("workout", "fitness", "style")


def _hash10(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:10]


def _anonymize_identifier(value: Any, key: str) -> str:
    return f"{key}_{_hash10(value)}"


def _rewrite_instagram_urls(text: str) -> tuple[str, bool]:
    changed = False

    def _replace(match: re.Match[str]) -> str:
        nonlocal changed
        prefix = match.group(1)
        name = match.group(2)
        changed = True
        return f"{prefix}user_{_hash10(name)}"

    return INSTAGRAM_URL_RE.sub(_replace, text), changed


def _sanitize_obj(obj: Any) -> tuple[Any, bool]:
    changed = False

    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if key in IDENTIFIER_KEYS:
                new_value = _anonymize_identifier(value, key)
                out[key] = new_value
                if new_value != value:
                    changed = True
                continue
            sanitized_value, inner_changed = _sanitize_obj(value)
            out[key] = sanitized_value
            changed = changed or inner_changed
        return out, changed

    if isinstance(obj, list):
        out_list: list[Any] = []
        for item in obj:
            sanitized_item, inner_changed = _sanitize_obj(item)
            out_list.append(sanitized_item)
            changed = changed or inner_changed
        return out_list, changed

    if isinstance(obj, str):
        rewritten, url_changed = _rewrite_instagram_urls(obj)
        changed = changed or url_changed

        # If a string is embedded JSON, sanitize it structurally and re-encode.
        stripped = rewritten.strip()
        if stripped and stripped[0] in "{[":
            try:
                parsed = json.loads(rewritten)
            except json.JSONDecodeError:
                return rewritten, changed
            sanitized_parsed, parsed_changed = _sanitize_obj(parsed)
            encoded = json.dumps(sanitized_parsed, ensure_ascii=False)
            return encoded, changed or parsed_changed or (encoded != rewritten)

        return rewritten, changed

    return obj, changed


def _collect_text_from_key(obj: Any, target_keys: set[str], sink: list[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in target_keys:
                _collect_free_text(value, sink)
            _collect_text_from_key(value, target_keys, sink)
        return
    if isinstance(obj, list):
        for item in obj:
            _collect_text_from_key(item, target_keys, sink)


def _collect_free_text(obj: Any, sink: list[str]) -> None:
    if isinstance(obj, dict):
        for value in obj.values():
            _collect_free_text(value, sink)
        return
    if isinstance(obj, list):
        for item in obj:
            _collect_free_text(item, sink)
        return
    if isinstance(obj, str):
        sink.append(obj.lower())


def _iter_message_payloads(row: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    payloads: list[tuple[str, dict[str, Any]]] = []
    messages = row.get("messages")
    if not isinstance(messages, list):
        return payloads
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            continue
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append((role.lower(), parsed))
    return payloads


def _detect_drop_reason(row: dict[str, Any]) -> str | None:
    niche_texts: list[str] = []
    suggestion_texts: list[str] = []

    for role, payload in _iter_message_payloads(row):
        _collect_text_from_key(payload, {"niche", "primary_niche", "secondary_niche"}, niche_texts)
        if role == "assistant":
            _collect_text_from_key(payload, {"content_suggestions", "suggestions", "recommendations"}, suggestion_texts)

            payload_texts: list[str] = []
            _collect_free_text(payload, payload_texts)
            for txt in payload_texts:
                niche_match = re.search(r"focus content on your ([a-z ]+) niche", txt)
                if niche_match:
                    niche_texts.append(niche_match.group(1).strip())

    _collect_text_from_key(row, {"niche", "primary_niche", "secondary_niche"}, niche_texts)

    free_texts: list[str] = []
    _collect_free_text(row, free_texts)

    if not suggestion_texts:
        _collect_text_from_key(row, {"content_suggestions", "suggestions", "recommendations"}, suggestion_texts)
    if not suggestion_texts:
        suggestion_texts = free_texts

    niche_blob = " ".join(niche_texts)
    suggestion_blob = " ".join(suggestion_texts)

    has_food_or_cooking_niche = any(term in niche_blob for term in FOOD_NICHE_TERMS)
    has_technology_niche = any(term in niche_blob for term in TECH_NICHE_TERMS)
    has_workout_or_fitness_suggestion = any(term in suggestion_blob for term in FITNESS_SUGGESTION_TERMS)
    has_tech_mismatch_suggestion = any(term in suggestion_blob for term in TECH_MISMATCH_SUGGESTION_TERMS)

    if has_food_or_cooking_niche and has_workout_or_fitness_suggestion:
        return "food/cooking niche with workout/fitness suggestions"
    if has_technology_niche and has_tech_mismatch_suggestion:
        return "technology niche with workout/fitness/style suggestions"
    return None


def main() -> None:
    total = 0
    anonymized_rows = 0
    dropped_rows = 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with (
        INPUT_PATH.open("r", encoding="utf-8") as src,
        OUTPUT_PATH.open("w", encoding="utf-8") as dst,
        DROPPED_PATH.open("w", encoding="utf-8") as dropped_dst,
    ):
        for line in src:
            raw = line.strip()
            if not raw:
                continue

            total += 1
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                # Keep malformed rows out of the sanitized file.
                dropped_rows += 1
                continue

            sanitized_row, changed = _sanitize_obj(row)
            if changed:
                anonymized_rows += 1

            if not isinstance(sanitized_row, dict):
                dropped_rows += 1
                continue

            drop_reason = _detect_drop_reason(sanitized_row)
            if drop_reason:
                sanitized_row["_dropped_reason"] = drop_reason
                dropped_rows += 1
                dropped_dst.write(json.dumps(sanitized_row, ensure_ascii=False) + "\n")
                continue

            dst.write(json.dumps(sanitized_row, ensure_ascii=False) + "\n")

    print(f"total={total}")
    print(f"anonymized_rows={anonymized_rows}")
    print(f"dropped_rows={dropped_rows}")
    print(f"dropped_path={DROPPED_PATH}")


if __name__ == "__main__":
    main()
