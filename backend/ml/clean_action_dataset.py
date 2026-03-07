from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Literal, Type

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, StrictStr, ValidationError


INPUT_PATH = Path("backend/data/training_data_with_actions.jsonl")
OUTPUT_PATH = Path("backend/data/training_data_clean.jsonl")

KEYWORD_MAP = {
    "fitness": [
        "fitness", "workout", "gym", "leg day", "abs", "ab routine", "protein",
        "exercise", "training", "cardio", "strength", "lift", "lifting", "reps",
        "squat", "deadlift",
    ],
    "food": [
        "recipe", "cook", "cooking", "meal", "dinner", "brunch", "dessert",
        "restaurant", "chef", "bake", "baking", "kitchen", "food",
    ],
    "travel": [
        "travel", "trip", "vacation", "wanderlust", "flight", "hotel", "beach",
        "airport", "passport", "explore", "adventure",
    ],
    "tech": [
        "tech", "software", "app", "ai", "automation", "gadget", "coding",
        "programming", "developer", "dev", "unboxing", "setup",
    ],
    "fashion": [
        "fashion", "outfit", "style", "styling", "haul", "lookbook", "ootd",
        "wardrobe", "dress", "shoes",
    ],
    "lifestyle": [
        "morning routine", "day in my life", "routine", "vlog", "self care",
        "wellness", "habits", "home",
    ],
    "nutrition": [
        "nutrition", "macros", "calories", "diet", "healthy", "meal prep",
    ],
    "career": [
        "career", "job", "interview", "resume", "promotion", "office", "linkedin",
        "salary", "workplace",
    ],
    "beauty": [
        "makeup", "skincare", "beauty", "hair", "glow", "grwm",
    ],
    "gaming": [
        "gaming", "gameplay", "stream", "twitch", "esports", "ps5", "xbox",
    ],
    "finance": [
        "finance", "invest", "stocks", "budget", "saving", "crypto", "money",
    ],
    "education": [
        "study", "exam", "homework", "lesson", "teacher", "learn", "course",
    ],
    "music": [
        "music", "song", "cover", "guitar", "piano", "album", "beat",
    ],
    "art": [
        "art", "drawing", "painting", "illustration", "design", "sketch",
    ],
    "sports": [
        "match", "game day", "team", "athlete", "score", "tournament",
    ],
    "business": [
        "startup", "business", "entrepreneur", "marketing", "sales", "founder",
        "strategy",
    ],
}


class TrainingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: StrictStr
    followers: StrictInt
    avg_likes: StrictInt | StrictFloat
    avg_comments: StrictInt | StrictFloat
    avg_views: StrictInt | StrictFloat
    posts_per_week: StrictInt | StrictFloat


class TrainingPost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caption: StrictStr
    likes: StrictInt
    comments: StrictInt
    views: StrictInt


class TrainingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: TrainingProfile
    posts: List[TrainingPost]


class TrainingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    niche: Dict[str, Any]
    growth: Dict[str, Any]
    post_insights: List[Dict[str, Any]]


class EnrichedTrainingOutput(TrainingOutput):
    model_config = ConfigDict(extra="forbid")

    action_plan: Dict[str, Any]


class TrainingExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    example_id: StrictStr
    created_at: datetime
    input: TrainingInput
    output: TrainingOutput
    quality: Literal["high", "medium", "low"]


class EnrichedTrainingExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    example_id: StrictStr
    created_at: datetime
    input: TrainingInput
    output: EnrichedTrainingOutput
    quality: Literal["high", "medium", "low"]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: StrictStr


class ChatExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: List[ChatMessage]


def validate_jsonl_entry(entry: Dict[str, Any], model: Type[BaseModel], row_index: Optional[int] = None) -> BaseModel:
    try:
        return model.model_validate(entry)
    except ValidationError as exc:
        prefix = f"Row {row_index}: " if row_index is not None else ""
        raise ValueError(f"{prefix}{exc.errors()}") from exc


def _read_jsonl(path: Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_num, json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[warn] invalid json at {path}:{line_num}: {exc}")


def _collect_niches(path: Path) -> List[str]:
    niches = set()
    for _, row in _read_jsonl(path):
        output = row.get("output") if isinstance(row, dict) else None
        niche = output.get("niche") if isinstance(output, dict) else None
        primary = niche.get("primary_niche") if isinstance(niche, dict) else None
        if isinstance(primary, str) and primary.strip():
            niches.add(primary.strip().lower())
    return sorted(niches)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg_engagement_rate_by_views(posts: List[Dict[str, Any]]) -> Optional[float]:
    rates = []
    for post in posts:
        views = _safe_float(post.get("views"))
        likes = _safe_float(post.get("likes"))
        comments = _safe_float(post.get("comments"))
        if views and views > 0 and likes is not None and comments is not None:
            rates.append((likes + comments) / views)
    if not rates:
        return None
    return sum(rates) / len(rates)


def _engagement_phrase(rate: Optional[float]) -> str:
    if rate is None:
        return "Engagement rate by views is unavailable."
    if rate >= 0.10:
        return "Engagement rate by views is high."
    if rate >= 0.05:
        return "Engagement rate by views is solid."
    if rate >= 0.02:
        return "Engagement rate by views is moderate."
    return "Engagement rate by views is low."


def _growth_score_phrase(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    if score >= 70:
        return "Overall growth score is strong."
    if score >= 50:
        return "Growth score is moderate - room for improvement."
    return "Growth score needs attention - prioritize consistency."


def _extract_follower_delta(input_data: Dict[str, Any]) -> Optional[float]:
    profile = input_data.get("profile") if isinstance(input_data, dict) else {}
    candidates = [
        "follower_delta",
        "followers_delta",
        "daily_follower_delta",
        "daily_followers_delta",
        "daily_follower_growth",
        "followers_per_day",
        "follower_growth_per_day",
        "daily_followers",
        "daily_follower_change",
        "daily_followers_change",
    ]

    for container in (profile, input_data):
        if not isinstance(container, dict):
            continue
        for key in candidates:
            value = _safe_float(container.get(key))
            if value is not None:
                return value
    return None


def _format_follower_delta(delta: float) -> str:
    if abs(delta) >= 1:
        return f"{delta:.0f}"
    return f"{delta:.2f}"


def _build_diagnosis(
    input_data: Dict[str, Any],
    profile: Dict[str, Any],
    posts: List[Dict[str, Any]],
    growth: Dict[str, Any],
) -> str:
    parts = []
    avg_rate = _avg_engagement_rate_by_views(posts)
    if avg_rate is not None:
        parts.append(
            f"Average engagement rate by views is {avg_rate * 100:.2f}% based on recent posts."
        )
    else:
        parts.append("Engagement rate by views cannot be computed from recent posts.")

    parts.append(_engagement_phrase(avg_rate))

    follower_delta = _extract_follower_delta(input_data)
    if follower_delta is not None:
        parts.append(
            f"Daily follower growth is {_format_follower_delta(follower_delta)} followers per day."
        )

    posts_per_week = _safe_float(profile.get("posts_per_week"))
    if posts_per_week is not None and posts_per_week > 0:
        parts.append(f"Posting cadence is about {posts_per_week:.1f} posts per week.")

    growth_score = _safe_float(growth.get("growth_score"))
    growth_phrase = _growth_score_phrase(growth_score)
    if growth_phrase:
        parts.append(growth_phrase)

    return " ".join(parts).strip()


def _strong_niche_from_caption(
    caption: str,
    keyword_map: Dict[str, List[re.Pattern[str]]],
) -> Optional[str]:
    text = re.sub(r"\s+", " ", (caption or "").lower()).strip()
    if not text:
        return None

    scores: Dict[str, int] = {}
    for niche, keyword_patterns in keyword_map.items():
        count = 0
        for keyword_pattern in keyword_patterns:
            if keyword_pattern.search(text):
                count += 1
        if count > 0:
            scores[niche] = count

    if not scores:
        return None

    max_score = max(scores.values())
    top = [n for n, score in scores.items() if score == max_score]
    if len(top) != 1:
        return None
    return top[0]


def _maybe_adjust_niche(
    niche: Dict[str, Any],
    posts: List[Dict[str, Any]],
    keyword_map: Dict[str, List[re.Pattern[str]]],
) -> Tuple[Dict[str, Any], bool]:
    current = niche.get("primary_niche")
    if not isinstance(current, str) or not current.strip():
        return niche, False

    if len(posts) < 3:
        return niche, False

    recent_posts = posts[-3:]
    detected = []
    for post in recent_posts:
        caption = post.get("caption") or ""
        matched = _strong_niche_from_caption(caption, keyword_map)
        if not matched:
            return niche, False
        detected.append(matched)

    if any(match == current for match in detected):
        return niche, False

    counts = Counter(detected)
    most_common = counts.most_common()
    if len(most_common) < 1:
        return niche, False

    top_count = most_common[0][1]
    if sum(1 for _, count in most_common if count == top_count) > 1:
        return niche, False

    new_primary = most_common[0][0]
    if new_primary == current:
        return niche, False

    updated = dict(niche)
    updated["primary_niche"] = new_primary
    return updated, True


def _clean_row(
    row: Dict[str, Any],
    keyword_map: Dict[str, List[re.Pattern[str]]],
) -> Dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("row is not a dict")

    # Create a shallow copy to avoid mutating the input.
    row = dict(row)

    input_data = row.get("input")
    output_data = row.get("output")
    if not isinstance(input_data, dict) or not isinstance(output_data, dict):
        raise ValueError("row missing input/output dict")

    profile = input_data.get("profile")
    posts = input_data.get("posts")
    if not isinstance(profile, dict) or not isinstance(posts, list):
        raise ValueError("row missing input.profile or input.posts")

    action_plan = output_data.get("action_plan")
    if not isinstance(action_plan, dict):
        raise ValueError("row missing output.action_plan")

    # NOTE:
    # The 'quality' field is retained because EnrichedTrainingExample
    # requires quality: Literal["high", "medium", "low"].
    # Removing it would break validation.

    # Refresh diagnosis with input-tied metrics.
    growth = output_data.get("growth") if isinstance(output_data.get("growth"), dict) else {}
    updated_action_plan = dict(action_plan)
    updated_action_plan["diagnosis"] = _build_diagnosis(input_data, profile, posts, growth)

    updated_output = dict(output_data)
    updated_output["action_plan"] = updated_action_plan

    niche = updated_output.get("niche")
    if isinstance(niche, dict) and keyword_map:
        updated_niche, changed = _maybe_adjust_niche(niche, posts, keyword_map)
        if changed:
            updated_output["niche"] = updated_niche

    row["output"] = updated_output
    return row


def _print_dry_run(
    line_num: int,
    original_diag: Optional[str],
    cleaned_diag: Optional[str],
    original_niche: Optional[str],
    cleaned_niche: Optional[str],
    modified: bool,
) -> None:
    print(f"Row {line_num}")
    print(f"Original diagnosis: {original_diag}")
    print(f"Cleaned diagnosis: {cleaned_diag}")
    print(f"Original niche.primary_niche: {original_niche}")
    print(f"Cleaned niche.primary_niche: {cleaned_niche}")
    print(f"Modified: {modified}")
    print("-" * 40)


def _normalize_quality(value: Any) -> Any:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "good":
            return "high"
        if lowered == "ok":
            return "medium"
        if lowered == "bad":
            return "low"
    return value


def _normalize_row_quality(row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return row
    updated = dict(row)
    if "quality" in updated:
        updated["quality"] = _normalize_quality(updated.get("quality"))
    return updated


def _compile_keyword_patterns(
    keyword_map: Dict[str, List[str]],
) -> Dict[str, List[re.Pattern[str]]]:
    compiled: Dict[str, List[re.Pattern[str]]] = {}
    for niche, keywords in keyword_map.items():
        compiled_patterns: List[re.Pattern[str]] = []
        for keyword in keywords:
            normalized_keyword = re.sub(r"\s+", " ", keyword.strip().lower())
            if not normalized_keyword:
                continue
            escaped_parts = [re.escape(part) for part in normalized_keyword.split(" ") if part]
            if not escaped_parts:
                continue
            pattern = re.compile(r"\b" + r"\s+".join(escaped_parts) + r"\b")
            compiled_patterns.append(pattern)
        if compiled_patterns:
            compiled[niche] = compiled_patterns
    return compiled


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean action plan dataset.")
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Process only first 5 rows and print changes without writing output.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output file if it already exists.",
    )
    args = parser.parse_args()

    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    existing_niches = _collect_niches(INPUT_PATH)
    keyword_map = {
        niche: KEYWORD_MAP[niche]
        for niche in existing_niches
        if niche in KEYWORD_MAP
    }
    keyword_patterns = _compile_keyword_patterns(keyword_map)

    processed = 0
    cleaned = 0

    if args.dry_run:
        for line_num, row in _read_jsonl(INPUT_PATH):
            processed += 1
            try:
                row = _normalize_row_quality(row)
                validate_jsonl_entry(row, EnrichedTrainingExample, row_index=line_num)
                original_output = row.get("output") if isinstance(row, dict) else {}
                original_action_plan = (
                    original_output.get("action_plan") if isinstance(original_output, dict) else {}
                )
                original_diag = original_action_plan.get("diagnosis")
                original_niche = None
                if isinstance(original_output, dict):
                    niche = original_output.get("niche")
                    if isinstance(niche, dict):
                        original_niche = niche.get("primary_niche")

                cleaned_row = _clean_row(row, keyword_patterns)
                cleaned_row = _normalize_row_quality(cleaned_row)
                validate_jsonl_entry(cleaned_row, EnrichedTrainingExample, row_index=line_num)
                cleaned_output = cleaned_row.get("output") if isinstance(cleaned_row, dict) else {}
                cleaned_action_plan = (
                    cleaned_output.get("action_plan") if isinstance(cleaned_output, dict) else {}
                )
                cleaned_diag = cleaned_action_plan.get("diagnosis")
                cleaned_niche = None
                if isinstance(cleaned_output, dict):
                    niche = cleaned_output.get("niche")
                    if isinstance(niche, dict):
                        cleaned_niche = niche.get("primary_niche")

                modified = (original_diag != cleaned_diag) or (original_niche != cleaned_niche)
                _print_dry_run(
                    line_num,
                    original_diag,
                    cleaned_diag,
                    original_niche,
                    cleaned_niche,
                    modified,
                )
                cleaned += 1
            except Exception as exc:
                print(f"[warn] skipped line {line_num}: {exc}")

            if processed >= 5:
                break
    else:
        if OUTPUT_PATH.exists() and not args.force:
            raise RuntimeError(
                f"Output file already exists: {OUTPUT_PATH}. "
                "Pass --force to overwrite."
            )
        with OUTPUT_PATH.open("w", encoding="utf-8") as out_file:
            for line_num, row in _read_jsonl(INPUT_PATH):
                processed += 1
                try:
                    row = _normalize_row_quality(row)
                    validate_jsonl_entry(row, EnrichedTrainingExample, row_index=line_num)
                    cleaned_row = _clean_row(row, keyword_patterns)
                    cleaned_row = _normalize_row_quality(cleaned_row)
                    validate_jsonl_entry(cleaned_row, EnrichedTrainingExample, row_index=line_num)
                except Exception as exc:
                    print(f"[warn] skipped line {line_num}: {exc}")
                    continue

                out_file.write(json.dumps(cleaned_row, ensure_ascii=False))
                out_file.write("\n")
                cleaned += 1

                if processed % 10 == 0:
                    print(f"Processed {processed} rows, cleaned {cleaned} rows")


if __name__ == "__main__":
    main()
